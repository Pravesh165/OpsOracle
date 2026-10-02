# OPS-Mind Project Baseline

**Source of truth:** inspected Python source, config, datasets, CI, and packaging files. README / DEPLOYMENT.md claims were **not** treated as implementation.

**Scope of this document:** current behavior only. No feature work was done.

**Package:** `opsmind` v0.1.0 (`pyproject.toml`) — “Autonomous Incident-to-Insight Assistant” built on **Google Agent Development Kit (ADK)**.

---

## 1. What the project does

OPS-Mind is a **multi-agent chat assistant** for SRE/DevOps:

- Answer operational questions using **local CSV “knowledge”** (incident log + Jira export).
- Search incidents and Jira CSVs with **substring / keyword matching**.
- Optionally fall back to **Google Search** via a dedicated search agent.
- Run a **sequential pipeline** (`listener` → `synthesizer` → `writer`) for incident-to-postmortem.
- Generate **markdown postmortems** from a template filled with keyword-matched context, then save to **GCP Cloud Storage** (signed URL) or **local `output/`**.
- Apply **MVP guardrails** (input length/XSS patterns, process-wide rate limit, HTML escaping) around most tools.
- Optionally poll a **live Jira REST API** (disabled unless `JIRA_ENABLED=TRUE`). Live data is **not** what the root agent’s search tools use today.

There is **no custom web app, REST API, database, vector store, or test suite** in this tree.

---

## 2. Complete application flow

```
User (ADK CLI or ADK web)
        │
        ▼
opsmind/agent.py  →  root_agent = core.agents.root.root
        │
        ├── Direct tool calls on Root Agent (default path for Q&A, search, postmortem)
        │     knowledge / incidents / Jira CSV search / postmortem / guardrail health
        │     + AgentTool(search) → google_search
        │
        └── Sub-agent: SequentialAgent "pipeline"
              1. listener    → process_incident_stream  (JSON into session state)
              2. synthesizer → get_incident_context + create_incident_summary
              3. writer      → generate_postmortem_content + save_postmortem
```

**Typical Q&A path (root, not pipeline):**

1. User asks a DevOps question.
2. Root LLM chooses tools (prompt-driven; not a hard-coded router).
3. `answer_devops_question` / `search_knowledge_base` load CSVs via `data.loader`, token-split the query, `str.contains` across columns, return records + a template “answer.”
4. If `confidence <= 0.2` or zero hits, tool returns `fallback_needed: true`. Root **may** then call `AgentTool(search)` (Google). This is **not automatic inside the knowledge tool**.
5. LLM writes the user-facing reply.

**Typical postmortem path (root tools, bypassing pipeline):**

1. User: “Generate postmortem for INC0000045.”
2. `generate_postmortem_content(incident_id)` calls `get_incident_context(query=incident_id)`.
3. Context is **keyword search over an in-memory cap of ~100 incidents + ~250 Jira rows**, not a keyed lookup.
4. Markdown is assembled with **fixed section text** plus interpolated fields.
5. `save_postmortem` uploads to GCS if `GCP_STORAGE_ENABLED`, else writes `output/postmortem_*.md`.

**Pipeline path:** only if the root agent **delegates** to the `pipeline` sub-agent. Listener expects JSON incident payloads; it does not itself read the CSV.

**Session state keys used:** `incident_stream`, `incident_summaries`, `incident_memory`, `last_incident_search`, `last_incident_correlation`, `last_jira_incident_search`, `last_incident_timeline`, `last_knowledge_search`.

---

## 3. Current architecture

```
opsmind/
  agent.py                 ADK entry: root_agent alias
  config/settings.py       env + paths + logging
  core/agents/             ADK Agent / SequentialAgent definitions
  core/safety/             Guardrail framework
  tools/                   ADK tool functions (knowledge, incidents, postmortem, guardrail)
  context/                 RAG retrieval + unused DataManager facade
  data/loader.py           CSV load + Jira CSV search
  data/manager.py          Plug-and-play DataManager (not used by agents)
  data/connectors/         Live Jira poller (optional, unused by agent tools)
  data/datasets/           Bundled CSV samples
  utils/                   helpers, GCP storage, logging
```

**Runtime model:** Google Gemini via ADK (`MODEL`, default `gemini-2.0-flash-001`). `GOOGLE_API_KEY` and optional Vertex (`GOOGLE_GENAI_USE_VERTEXAI`).

**Layers that exist but are disconnected from the live agent graph:**

| Layer | Used by agents? |
| --- | --- |
| `get_incident_context` (`context/retrieval.py`) | Yes (synthesizer, postmortem) |
| `search_*` on CSVs (`data/loader.py`, `tools/knowledge.py`, `tools/incidents.py`) | Yes (root tools) |
| `context.interface.get_context` / `configure` / `preset` | **No** |
| `data.manager.DataManager` | **No** (only via unused interface) |
| `JiraConnector` REST search / correlate | **No** (CSV loader used instead) |
| `PRESETS` (quick / full / live) | Defined in settings; **not wired to agents** |

---

## 4. All existing agents

| Agent | Type | File | Role | Tools |
| --- | --- | --- | --- | --- |
| `root` | `Agent` | `core/agents/root.py` | User-facing orchestrator | Knowledge, incident, Jira CSV, postmortem, guardrail, `AgentTool(search)` |
| `pipeline` | `SequentialAgent` | `core/agents/pipeline.py` | Fixed 3-step pipeline | (sub-agents only) |
| `listener` | `Agent` | `core/agents/listener.py` | Parse incidents into session stream | `process_incident_stream` |
| `synthesizer` | `Agent` | `core/agents/synthesizer.py` | Summarize with “RAG” context | `get_incident_context`, `create_incident_summary` |
| `writer` | `Agent` | `core/agents/writer.py` | Postmortem markdown + save | `generate_postmortem_content`, `save_postmortem` |
| `search` | `Agent` | `core/agents/search.py` | Web search specialist | ADK `google_search` |

**Not an agent:** safety is a **decorator + manager**, not an ADK agent (`core/agents/__init__.py` notes “Guardrail agent moved to safety module”).

**Import inconsistency:** `core/__init__.py` imports `pipeline` from `core.agents`, but `core/agents/__init__.py` exports `opsmind_pipeline` only. ADK entry uses `from .core.agents import root`, so `adk run opsmind` can still load. `from opsmind.core import pipeline` would fail.

---

## 5. All existing tools

### Attached to `root`

| Tool | Module | Notes |
| --- | --- | --- |
| `search_knowledge_base` | `tools/knowledge.py` | Multi-CSV keyword search |
| `answer_devops_question` | `tools/knowledge.py` | Search + heuristic confidence + template answer |
| `find_similar_issues` | `tools/knowledge.py` | Same search; prefers items with resolution text |
| `get_historical_patterns` | `tools/knowledge.py` | Pandas value_counts; `time_period_days` unused |
| `get_incident_context` | `context/retrieval.py` | Capped in-memory keyword “RAG” |
| `process_incident_stream` | `tools/incidents.py` | Append JSON incident to state |
| `create_incident_summary` | `tools/incidents.py` | Store summary text in state |
| `generate_postmortem_content` | `tools/postmortems.py` | Template markdown |
| `save_postmortem` | `tools/postmortems.py` | GCS or local |
| `list_postmortem_files` | `tools/postmortems.py` | List GCS/local |
| `search_incidents` | `tools/incidents.py` | Incident CSV substring |
| `correlate_incident_with_jira` | `tools/incidents.py` | Incident lookup + keyword Jira search |
| `search_jira_for_incidents` | `tools/incidents.py` | **Sync**, no `@with_guardrail` |
| `get_incident_jira_timeline` | `tools/incidents.py` | **Sync**, no `@with_guardrail`; Jira side is `head(5)` if no key |
| `search_jira_issues` | `data/loader.py` | CSV filters; **sync** |
| `search_jira_comments` | `data/loader.py` | CSV; **sync** |
| `search_jira_changelog` | `data/loader.py` | CSV; **sync** |
| `get_jira_issue_details` | `data/loader.py` | CSV join by `key`; **sync** |
| `check_guardrails_health` | `tools/guardrail.py` | **Sync** |
| `get_system_resources` | `tools/guardrail.py` | psutil; **sync** |
| `AgentTool(search)` | `core/agents/search.py` | Google Search |

### Defined but not on the root tool list

| Function | Location |
| --- | --- |
| `initialize_guardrails` | `tools/guardrail.py` (initialized on `core` import) |
| `monitor_safety_status`, `check_system_health` | string helpers, unused by agents |
| `get_context`, `configure`, `info`, `preset` | `context/interface.py` |
| `JiraConnector.search_issues`, `.search_comments`, `.get_issue_details`, `.correlate_with_incidents` | live API; unused by ADK tools |
| `delete_file_from_gcp` | `utils/gcp_storage.py` |

---

## 6. Current incident workflow

1. **Data:** `opsmind/data/datasets/incidents/incident_event_log.csv` (ServiceNow-style event log). Loader reads **first 1000 rows**; repo file has **99 data rows**.
2. **Columns present:** `number`, `incident_state`, `category`, `subcategory`, `u_symptom`, `priority`, `assignment_group`, `opened_at`, `closed_at`, `closed_code`, `resolved_by`, etc.
3. **Columns tools often expect but CSV does not have:** `description`, `short_description`, `resolution`. Symptom lives in `u_symptom`; close reason in `closed_code`.
4. **Search:** `search_incidents` ORs `str.contains` on `u_symptom`, `description`, `category`, `subcategory`, `priority`, `assignment_group` (missing columns simply skipped).
5. **Stream:** `process_incident_stream` parses JSON and appends to `tool_context.state["incident_stream"]`. Nothing in code **reads the CSV into this stream automatically**.
6. **Summary:** `create_incident_summary` stores LLM-provided text; **not** used by `generate_postmortem_content` (postmortem uses `get_incident_context` only).
7. **Correlation:** `correlate_incident_with_jira` finds the incident by `number`, then searches Jira CSVs with symptom/category/subcategory strings. Changelog search in that loop **does not pass the search term** (`search_jira_changelog(limit=10)` only).
8. **Timeline:** incident opened/closed events + either one Jira key or the **first 5 issues in the CSV**, not time-window correlation.

There is **no** incident state machine (ack / mitigate / resolve), no paging, no on-call, no SLO objects.

---

## 7. Current Jira integration

### A. Offline CSV (what agents actually use)

Paths in `config/settings.py`:

- `opsmind/data/datasets/jira/issues.csv`
- `comments.csv`, `changelog.csv`, `issuelinks.csv`

Repo sizes (including header): issues 86 lines, comments 86, changelog 89, issuelinks 100.

These look like **Apache Jira public-export style** (e.g. keys `WW-712`, `ROL-555`, `BEAM-10705`), **not** linked to incident IDs like `INC0000045`. Correlation is **keyword overlap only**.

Loader comment claims columns may be shifted so search uses `key` instead of `summary`. **Current `issues.csv` headers are `id,key,summary,...`**. `search_jira_issues` still searches `key` + `description`, **not `summary`**.

### B. Live REST connector (implemented, optional, unused by tools)

`data/connectors/jira.py` — `JiraConnector`:

- Basic auth (`username:api_token`)
- Poll loop via `BaseConnector` (`poll_interval` from env, default 300s)
- `/rest/api/2/search`, comments, worklogs, changelog expand
- Methods: `search_issues`, `get_issue_details`, `search_comments`, `correlate_with_incidents`

Created only if `JIRA_ENABLED=TRUE` and URL/user/token set. `context.interface.get_context` *would* attach it — **agents never call `get_context`**.

**Not implemented:** Jira **write** (create/update issue, comment, transition). Read-only.

---

## 8. Current knowledge retrieval / RAG approach

**This is not embedding RAG.** No vector DB, no chunking pipeline, no embeddings API.

### Path A — `get_incident_context` (used for postmortem + synthesizer)

1. On first call, load CSVs into `state["incident_memory"]`.
2. Caps: **100 incidents**, **100 issues**, **50 comments**, **50 changelog**, **50 links**.
3. Query: `query.lower().split()`; score = count of tokens found in `str(item)`.
4. Return top **15**.

Field mapping bugs vs actual CSVs:

- Comments: code uses `issue_key`, `author.displayName`, `body`; file has `key`, `comment.author`, `comment.body`.
- Changelog: code uses `issue_key`, `author.displayName`; file has `key`, `author`.
- Links: code uses `sourceIssueKey`, `targetIssueKey`, `linkType.name`; file has `inwardIssue.key` / `outwardIssue.key` / `type.name`.
- Incidents: `short_description` / `description` missing; `resolution` mapped from `closed_code`.

Postmortem looks up `item["type"]=="incident"` and `item["id"]==incident_id`. That only works if that ID was in the **first 100 CSV rows** and the query tokens matched.

### Path B — knowledge tools

Stopword-filtered word tokens; OR `str.contains` per term; `head(limit)`. Answer confidence: +0.3 per incident with `resolution`, +0.3 per Jira issue with `resolution.name`, +0.2 per long comment (max 1.0). Threshold 0.2.

### Path C — `DataManager.query` (unused)

Same keyword scoring, optional live buffer merge, priority boost. CSV context caps 200 incidents / 200 issues / 100 comments.

---

## 9. Current search implementation

| Mechanism | Algorithm |
| --- | --- |
| Incident / Jira / knowledge | Case-insensitive pandas `str.contains` (regex, unescaped user text) |
| `get_incident_context` | Token-in-`str(item)` count |
| Google | ADK `google_search` on `search` agent |
| Ranking | First N rows after filter, or match count; similar issues sorted by **resolution string length** |
| Dedup | Dict keyed by Jira `key` / comment id |

No BM25, no fuzzy edit-distance (despite comments saying “fuzzy”), no inverted index, no caching beyond session `incident_memory` and DataManager `csv_cache` (latter unused).

Every search **reloads CSVs** (`load_incident_data` / `load_jira_data`) except `get_incident_context` after first fill.

---

## 10. Current postmortem generation

`generate_postmortem_content` builds a **string template**, not an LLM-written RCA. Sections:

- Executive Summary, Incident Details, Root Cause Analysis  
- Related Jira Issues (max 5), Comments (max 3), Timeline (max 5), Links (max 3)  
- **Static** Lessons Learned / Action Items / Recommendations (data-quality boilerplate)

`save_postmortem`: filename `postmortem_{id}_{timestamp}.md`. GCS folder `GCP_POSTMORTEM_FOLDER` (default `postmortems`). Signed URL **hardcoded 24 hours** (`expiration_hours=24`), not `GCP_FILE_EXPIRATION_DAYS` (default 30). Fallback: `OUTPUT_DIR` (`<repo>/output`).

Writer prompt says to show full markdown + download link. Pipeline writer does **not** call `list_postmortem_files`.

---

## 11. Current safety / guardrail system

`core/safety/framework.py` + `tools/guardrail.py`.

Initialized on `opsmind.core` import via `initialize_default_guardrails()`.

| Guardrail | Strict? | Behavior |
| --- | --- | --- |
| `data_validation` | **Yes** | Fail if `context['data']` string fields > 50k chars or contain `<script>`, `javascript:`, etc. |
| `rate_limiter` | No | 100 checks / 60s **process-wide** (not per user) |
| `ui_content_escaper` | No | HTML-escape / strip patterns; **always PASSED** even when it mutates |

`@with_guardrail` builds `context['data']` from `kwargs.get('data', {})`. **Most tools do not pass `data=`**, so validation usually sees `{}` and always passes. Blocking XSS on incident JSON / query strings is largely **ineffective**.

Decorator is **async-only**. Sync tools (`search_jira_*` loader functions, timeline, health) skip it.

UI escaping mutates a local context dict, **not** tool return values.

`get_system_resources` reports CPU/memory; **does not gate** tool execution.

---

## 12. Current data sources

| Source | Location | In repo | Used by agent tools |
| --- | --- | --- | --- |
| Incident event log CSV | `opsmind/data/datasets/incidents/incident_event_log.csv` | ~99 rows | Yes |
| Jira issues CSV | `.../jira/issues.csv` | ~85 rows | Yes |
| Jira comments CSV | `comments.csv` | ~85 rows | Yes (column mismatch in RAG path) |
| Jira changelog CSV | `changelog.csv` | ~88 rows | Yes |
| Jira issuelinks CSV | `issuelinks.csv` | ~99 rows | RAG path only (wrong column names) |
| Live Jira Cloud/Server | REST | Config-gated | Connector only |
| Google Search | ADK built-in | — | Search agent |
| GCP bucket | postmortem blobs | — | Save/list if enabled |
| MQTT | commented in `requirements.txt` | — | Not implemented |

CSV load: up to 3 pandas strategies + line-by-line fallback; `nrows=1000`.

Incident and Jira historical datasets are **disjoint** (ServiceNow-like INC* vs Apache Jira keys).

---

## 13. Current configuration / environment variables

From `env.template` and `config/settings.py`:

| Variable | Default | Purpose |
| --- | --- | --- |
| `GOOGLE_API_KEY` | unset (warn) | Gemini |
| `GOOGLE_GENAI_USE_VERTEXAI` | `FALSE` | Vertex vs API key |
| `MODEL` | `gemini-2.0-flash-001` | All agents |
| `GCP_STORAGE_ENABLED` | `TRUE` | Postmortem GCS |
| `GCP_PROJECT_ID` | `""` | Storage client |
| `GCP_BUCKET_NAME` | `opsmind-postmortems` | Bucket |
| `GCP_POSTMORTEM_FOLDER` | `postmortems` | Prefix |
| `GCP_FILE_EXPIRATION_DAYS` | `30` | **Unused** by signed URL code |
| `JIRA_ENABLED` | `FALSE` | Live connector |
| `JIRA_BASE_URL` | `""` | REST base |
| `JIRA_USERNAME` | `""` | Auth |
| `JIRA_API_TOKEN` | `""` | Auth |
| `JIRA_PROJECT_KEYS` | `[]` | JQL project filter |
| `JIRA_POLL_INTERVAL` | `300` | Seconds |
| `JIRA_BATCH_SIZE` | `100` | Search maxResults |
| `JIRA_MAX_RETRIES` | `3` | Connector loop |
| `JIRA_RETRY_DELAY` | `5` | Seconds |

`validate_config()` logs warnings; it does **not** abort startup.

`OUTPUT_DIR.mkdir` runs at import.

---

## 14. How the project is run locally

No `__main__.py` and no FastAPI app. Intended ADK workflow (`DEPLOYMENT.md` / `deploy.sh`):

```bash
cp env.template .env
# set GOOGLE_API_KEY; typically GCP_STORAGE_ENABLED=FALSE for local
pip install -r requirements.txt
# or: pip install -e ".[dev]"   (pyproject deps differ — see limitations)

adk run opsmind      # CLI chat
adk web              # ADK web UI; package name opsmind, root_agent in opsmind/agent.py
```

`Makefile`: `install`, `test` → `python tests/test_opsmind.py` (**file missing**), `lint` flake8 on `opsmind/ tests/ examples/`, `format` black.

Deploy: `./deploy.sh -p PROJECT_ID` → `adk deploy cloud_run`.

---

## 15. Existing tests

**None.** No `tests/` directory, no `examples/`, no `test_*.py`.

`pyproject.toml` configures pytest `testpaths = ["tests"]`.  
`.github/workflows/ci.yml` (push/PR to `main`): install `.[dev]`, flake8 `opsmind/ tests/ examples/`, `python tests/test_opsmind.py` — **CI would fail** on this tree.

---

## 16. Important files by feature

| Feature | Files |
| --- | --- |
| ADK entry | `opsmind/agent.py`, `opsmind/__init__.py` |
| Root orchestration | `opsmind/core/agents/root.py` |
| Pipeline | `pipeline.py`, `listener.py`, `synthesizer.py`, `writer.py` |
| Web search | `core/agents/search.py` |
| Knowledge Q&A | `tools/knowledge.py` |
| Incidents | `tools/incidents.py` |
| Postmortem | `tools/postmortems.py`, `utils/gcp_storage.py` |
| Keyword RAG | `context/retrieval.py` |
| Unused unified context | `context/interface.py`, `context/manager.py`, `data/manager.py` |
| CSV I/O + Jira CSV search | `data/loader.py` |
| Live Jira | `data/connectors/jira.py`, `base.py`, `manager.py` |
| Guardrails | `core/safety/framework.py`, `tools/guardrail.py` |
| Config | `config/settings.py`, `env.template` |
| Helpers | `utils/helpers.py`, `utils/logging.py` |
| Sample data | `data/datasets/**` |
| Packaging | `pyproject.toml`, `requirements.txt` |
| Deploy | `deploy.sh`, `DEPLOYMENT.md` |

---

## 17. Current limitations

1. **No true RAG** — substring/token overlap, tiny in-memory caps.
2. **Incident and Jira datasets are unrelated**; “correlation” is coincidental keywords.
3. **Schema drift** — tools vs CSV columns (incident text fields; Jira comment/link names; issues search skips `summary`).
4. **Postmortems** are fill-in templates + generic action items, not model-authored RCA from summaries.
5. **Pipeline vs root duplication** — two ways to generate postmortems; pipeline summaries unused by writer tools.
6. **Live Jira unused** by the tool surface.
7. **Guardrails** barely see tool inputs; XSS escape does not sanitize outputs.
8. **Reload CSVs** on almost every tool call; no persistence of summaries beyond ADK session.
9. **Dependency mismatch:** `requirements.txt` has `google-adk`, pandas, numpy, dotenv, `google-cloud-storage`, aiohttp, psutil. `pyproject.toml` lists `google-adk-agents`, `google-genai`, pandas, dotenv — **missing** storage, aiohttp, psutil, numpy.
10. **No tests**, broken CI paths, Makefile lint on missing `tests/` and `examples/`.
11. **No product UI** of its own (ADK web only).
12. **`str.contains` + user query** = regex injection risk on search.
13. Sync vs async tools mixed; two tools lack guardrail decorator.
14. `search` agent comment: “Must be gemini-2.0-flash for google_search” but model is fully env-driven.
15. GCS default **on**; local use without a bucket fails upload then falls back.
16. Circular-ish imports: `data.manager` → `opsmind.context` → `data.manager` (works only because `RealTimeContextManager` is imported first).
17. Data volume: sample CSVs only (~100 rows each), not production Kaggle dumps.
18. No auth/tenancy, no audit log of agent actions (only `output/opsmind.log`).

---

## 18. Features that are already complete (for an MVP)

- ADK multi-agent package with `root_agent` export.
- Sequential listener → synthesizer → writer graph.
- CSV incident + Jira loaders with malformed-CSV fallbacks.
- Keyword knowledge search and heuristic Q&A with optional Google fallback **via agent**.
- Incident substring search and ID lookup for correlation.
- Template postmortem + GCS/local save + list files.
- Guardrail **framework** (validation / rate limit / UI escape) and health/psutil tools.
- Config via `.env`, Jira and GCP setting groups, `validate_config` warnings.
- Live Jira **connector implementation** (poll, search, comments, worklogs, changelog).
- `DataManager` + presets design for mixing CSV and streams (code complete, **not attached**).
- Cloud Run deploy script wrapping `adk deploy`.

---

## 19. Features that are partially implemented

| Feature | What’s there | What’s missing |
| --- | --- | --- |
| RAG / knowledge | Keyword retrieval, session memory | Embeddings, ranked semantic search, full-corpus index |
| Jira | CSV tools + live connector class | Tools calling live API; writes; incident↔issue keys |
| Incident pipeline | Three agents + state | Auto-ingest CSV; writer using summaries |
| Postmortem | Template + storage | LLM narrative, real timeline, actionable RCA |
| Guardrails | Decorator + three checks | Applied to real arguments; output filtering; per-user limits |
| Unified data manager | Query/start/stop/presets | Agent wiring |
| Web search fallback | Search agent + `fallback_needed` flag | Automatic tool chain inside knowledge tool |
| CI / quality | Workflow + Makefile + pytest config | Tests, examples, consistent deps |
| Observability | Logging to stdout + `output/opsmind.log` | Structured traces, metrics |

---

## 20. Features that are completely missing

- Vector / embedding RAG (Chroma, FAISS, Vertex Matching Engine, etc.)
- Custom frontend (dashboards, incident console)
- Application HTTP API (beyond whatever ADK Cloud Run exposes)
- Database / persistent incident store
- Automated tests
- Jira ticket **creation** / transitions
- Slack, PagerDuty, email, Prometheus, logs, Git, runbooks as sources
- MQTT (commented only)
- On-call / escalation / chatops commands
- Multi-tenant auth, RBAC
- Evaluation harness for retrieval or postmortem quality
- Deduplicated, time-aligned incident–Jira graph
- Streaming UI for pipeline steps

---

## Feature inventory (compact)

| Area | Status |
| --- | --- |
| ADK root + sub-agents | Complete |
| Pipeline SequentialAgent | Complete (delegation optional) |
| CSV knowledge search | Complete (lexical) |
| Semantic RAG | Missing |
| Google search agent | Complete |
| Incident CSV search | Complete (lexical) |
| Incident–Jira correlation | Partial (keywords, unrelated data) |
| Live Jira poll | Partial (code only) |
| Postmortem generate/save | Partial (template) |
| GCS postmortems | Complete with local fallback |
| Guardrails | Partial |
| DataManager / presets | Partial (unused) |
| Tests | Missing |
| Product UI | Missing |

---

## Reusable components for an enhanced hackathon version

**Reuse as-is (or with small wiring):**

- Agent **graph shape**: root + sequential pipeline + search `AgentTool`.
- Tool **signatures** and `ToolContext` state patterns.
- `data/loader.py` robust CSV ingest (raise `nrows`, fix column maps).
- `JiraConnector` + `BaseConnector` poll loop if live Jira is in scope.
- `DataManager` / `get_context` / `PRESETS` as a single retrieval façade once agents call it.
- GCP upload / signed URL / list helpers.
- Settings / `env.template` pattern.
- Guardrail **manager API** (`add_guardrail`, `check_all`) if checks are bound to real inputs.
- ADK deploy path (`agent.py` `root_agent`, `deploy.sh`).

**Reuse the idea, replace the mechanism:**

- `get_incident_context` / `search_knowledge_base` → keep the tool names, swap in embeddings + a real index.
- `generate_postmortem_content` → keep save/list tools; replace template with LLM generation grounded on retrieved chunks + timeline.
- `correlate_incident_with_jira` → keep the tool; add time windows, shared identifiers, live Jira.

**Do not treat as production-ready without fixes:**

- Column-name assumptions, `search_jira_issues` ignoring `summary`.
- Guardrail decorator as currently parameterized.
- `pyproject.toml` vs `requirements.txt`.
- Sample CSVs as a realistic joint knowledge base (need aligned incident+ticket data).
- CI until `tests/` exists.

---

## Suggested reuse map (hackathon)

If the next version adds semantic search, live ops context, and stronger postmortems:

1. Keep **ADK agents** and tool names for demo continuity.
2. Replace **retrieval.py + knowledge helpers** with a retriever module; leave `root.py` tool list stable.
3. Point incident/Jira tools at **one** `DataManager` (CSV + optional Jira stream).
4. Keep **postmortem save/list** and GCS; change only content generation.
5. Keep **JiraConnector** for live read; add write tools only if the hackathon needs ticket creation.
6. Add **tests/** against loader + retriever with the bundled CSVs as fixtures.
7. Align **incident schema** in tools with the actual event-log columns (or transform on load).

---

*Baseline generated from repository source. Application files were not modified except for adding this document.*
