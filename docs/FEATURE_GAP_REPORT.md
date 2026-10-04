# OPS-Mind — Feature Gap Report
**Generated:** 2026-10-03  
**Baseline inspected:** All Python source files, CSVs, config, requirements  
**Method:** Code-first. No claim is taken from README/DEPLOYMENT.md without source verification.

---

## Quick Summary

| Tier | Feature | Status |
|------|---------|--------|
| P0 | Semantic / hybrid RAG | ❌ Missing |
| P0 | Evidence citations | 🟡 Partial |
| P0 | Incident triage | 🟡 Partial |
| P0 | Multi-source correlation | 🟡 Partial |
| P0 | Explainable RCA | ❌ Missing |
| P0 | Similar incident intelligence | 🟡 Partial |
| P0 | Incident timeline | 🟡 Partial |
| P0 | Human approval for risky actions | ❌ Missing |
| P0 | Safe runbook-based remediation | ❌ Missing |
| P0 | Verification loop | ❌ Missing |
| P0 | Evidence-backed postmortem | 🟡 Partial |
| P0 | Improved dashboard | ❌ Missing |
| P1 | Change correlation | 🟡 Partial |
| P1 | Service topology | ❌ Missing |
| P1 | Alert deduplication | ❌ Missing |
| P1 | Incident clustering | ❌ Missing |
| P1 | Anomaly detection | ❌ Missing |
| P1 | Recurring problem detection | 🟡 Partial |
| P1 | Knowledge learning loop | ❌ Missing |
| P1 | Jira automation | ❌ Missing |
| P1 | ChatOps | ❌ Missing |
| P1 | Operational analytics | 🟡 Partial |
| P1 | Audit trail | ❌ Missing |
| P1 | RBAC | ❌ Missing |
| P1 | Advanced safety policies | 🟡 Partial |
| P1 | Incident replay / simulation | ❌ Missing |

**Legend:** ✅ Implemented · 🟡 Partial · ❌ Missing

---

## P0 Features — Detailed Analysis

---

### P0-1 · Semantic / Hybrid RAG

**Status:** ❌ **Missing**

#### What exists
- [`context/retrieval.py`](file:///c:/Users/prave/Downloads/OPS-Mind-main/opsmind/context/retrieval.py) — `get_incident_context()`: loads up to 100 incidents + 250 Jira rows into session state, then counts how many query tokens appear anywhere in `str(item)`. Returns top 15 by count.
- [`tools/knowledge.py`](file:///c:/Users/prave/Downloads/OPS-Mind-main/opsmind/tools/knowledge.py) — `search_knowledge_base()`, `answer_devops_question()`: stopword-filtered token extraction → pandas `str.contains` OR across columns.
- No vector store, no embeddings call, no chunking pipeline anywhere in the tree.

#### What is missing
- Embedding generation (Gemini `text-embedding-004`, or any other model).
- Vector index (FAISS, ChromaDB, Vertex Matching Engine / Vector Search).
- Chunking strategy for long incident descriptions and Jira bodies.
- Hybrid scoring: BM25 lexical + dense cosine.
- Re-ranking pass (MMR or cross-encoder).
- Persistent index that survives session restart.

#### Reusable
- Tool names and `ToolContext` signatures are stable — swap implementation, keep API.
- CSV loader (`data/loader.py`) can feed the indexing pipeline.
- `search_knowledge_base` → becomes the retriever wrapper.

#### Needs to be added
| Component | Notes |
|---|---|
| `opsmind/retrieval/embedder.py` | Calls `genai.embed_content(model="text-embedding-004")` |
| `opsmind/retrieval/index.py` | FAISS / ChromaDB vector store |
| `opsmind/retrieval/hybrid.py` | BM25 + dense merge + re-rank |
| Index build script | One-shot; re-run when data changes |

#### Complexity: **High**
Requires new dependency (FAISS / ChromaDB), embedding budget, and a build-time indexing step.

#### Dependencies
`google-genai`, `faiss-cpu` or `chromadb`, numpy already present.

#### Testing requirements
- Unit: embedding shape, index upsert/query.
- Integration: known incident → top-1 retrieved correctly.
- Regression: compare hit-rate vs current keyword baseline on sample queries.

#### Demo value: ⭐⭐⭐⭐⭐
Highest visible improvement. "Find incidents about Redis memory" returns semantically related results even without exact keyword matches.

#### Recommended priority: **Implement first (Sprint 1)**

---

### P0-2 · Evidence Citations

**Status:** 🟡 **Partially Implemented**

#### What exists
- `answer_devops_question()` in [`tools/knowledge.py`](file:///c:/Users/prave/Downloads/OPS-Mind-main/opsmind/tools/knowledge.py#L83-L150) returns `supporting_evidence` list with `id`, `title`, `resolution` fields (max 2 incidents + 2 issues + 1 comment).
- `find_similar_issues()` returns structured `similar_issues` list with type, id, resolution.
- Postmortem template in [`tools/postmortems.py`](file:///c:/Users/prave/Downloads/OPS-Mind-main/opsmind/tools/postmortems.py#L78-L130) lists Jira keys (max 5 issues, 3 comments, 5 changelog, 3 links).

#### Gaps
- No source URLs in evidence (Jira URLs exist in `JiraConnector` data records but not surfaced in CSV-path tools).
- Evidence is pulled from keyword match, not semantic relevance — citation quality is low.
- No citation IDs in the LLM's response text; the model decides whether to surface them.
- No confidence score displayed to the user for each individual citation.
- No deduplication of cited sources across multiple tool calls in one session.

#### Reusable
- `supporting_evidence` structure in `answer_devops_question` — extend rather than replace.
- `similar_issues` list format.

#### Needs to be added
| Component | Notes |
|---|---|
| Jira URL in evidence objects | Surface `jira_url` from connector metadata |
| Citation renderer | Format `[INC-001]`, `[JIRA-KEY]` inline in LLM prompt |
| Per-citation confidence | Attach semantic similarity score |

#### Complexity: **Low–Medium**
Schema and prompt change only; no new infra.

#### Dependencies
Semantic RAG (P0-1) improves citation quality but citations can be added independently.

#### Testing requirements
- Unit: evidence list non-empty for known queries.
- Integration: generated postmortem contains bracketed citation IDs.

#### Demo value: ⭐⭐⭐⭐
"Based on incident INC0000045 (2024-01-15, severity P1) …" is far more compelling than generic prose.

#### Recommended priority: **Sprint 2** (quick win once RAG is in)

---

### P0-3 · Incident Triage

**Status:** 🟡 **Partially Implemented**

#### What exists
- [`tools/incidents.py`](file:///c:/Users/prave/Downloads/OPS-Mind-main/opsmind/tools/incidents.py) `search_incidents()`: keyword filter across `u_symptom`, `category`, `subcategory`, `priority`, `assignment_group`.
- `correlate_incident_with_jira()`: finds incident by `number`, extracts symptom/category/subcategory as search terms, keyword-searches Jira CSVs.
- Root agent prompt lists triage capabilities ("Incident triage") but no dedicated triage tool or workflow exists.
- `listener` agent accepts JSON incident and appends to `incident_stream` state — a placeholder intake path.

#### Gaps
- No severity classification model or scoring function.
- No routing logic (which team/queue to assign).
- No SLA / SLO awareness.
- No paging or notification integration (PagerDuty, OpsGenie, Slack).
- No state machine (new → acknowledged → mitigated → resolved).
- `process_incident_stream` just appends to a list; the synthesizer is only called if the user explicitly delegates to the pipeline.
- CSV data has `priority` and `assignment_group` but no auto-triage happens.

#### Reusable
- `search_incidents()` — the lookup layer is correct.
- `listener` agent + `process_incident_stream` — the intake skeleton.
- ADK `SequentialAgent` pipeline — orchestration shape is right.

#### Needs to be added
| Component | Notes |
|---|---|
| `tools/triage.py` | `triage_incident(incident_data)` → severity score, recommended team, urgency |
| Severity scorer | Rules-based first (priority × category matrix); ML later |
| State machine | `transition_incident_state(id, new_state)` in session/DB |
| Triage agent | ADK `Agent` that calls `triage_incident` then routes |
| Notification stub | `notify_oncall(channel, message)` — even a log placeholder |

#### Complexity: **Medium**
Routing logic is well-defined; state machine needs a persistence layer.

#### Dependencies
Incident data schema fix (P0 cross-cutting), persistent store.

#### Testing requirements
- Unit: severity scorer returns expected tier for known priority/category combos.
- Integration: pipeline auto-triages injected incident and stores state.

#### Demo value: ⭐⭐⭐⭐
Live triage decision visible in the ADK chat is a strong hackathon moment.

#### Recommended priority: **Sprint 2**

---

### P0-4 · Multi-Source Correlation

**Status:** 🟡 **Partially Implemented**

#### What exists
- [`tools/incidents.py`](file:///c:/Users/prave/Downloads/OPS-Mind-main/opsmind/tools/incidents.py#L119-L206) `correlate_incident_with_jira()`: incident → symptom/category/subcategory tokens → keyword search across Jira issues, comments, changelog.
- `search_jira_for_incidents()`: same keyword search from the Jira side.
- `get_incident_jira_timeline()`: merges incident open/close events with Jira issue rows (not time-windowed; uses `head(5)` as fallback).

#### Gaps
- Incident and Jira datasets are **disjoint** (ServiceNow INC* vs Apache Jira keys). Correlation is coincidental keyword overlap.
- No time-window join: "find Jira changes within ±2 hours of incident open."
- No additional sources: metrics (Prometheus/Cloud Monitoring), logs, deployments, Git commits, alerts.
- Changelog search in `correlate_incident_with_jira` calls `search_jira_changelog(limit=10)` **without passing the search term**.
- No confidence score on correlation strength.

#### Reusable
- `correlate_incident_with_jira` tool — extend with time-window and semantic matching.
- `JiraConnector._extract_changelog_records()` extracts rich structured changes.

#### Needs to be added
| Component | Notes |
|---|---|
| Time-window correlation | `correlate_by_time(incident, window_minutes=120)` |
| Shared key resolver | Map `INC*` ↔ Jira keys via comment mention or custom field |
| Source adapters | Metrics, logs, deploy events (stub connectors) |
| Correlation confidence score | Overlap strength × time proximity |

#### Complexity: **High**
Requires aligned data (or a realistic synthetic dataset) and time-series joins.

#### Dependencies
Aligned incident+Jira dataset, optional: metrics/log connectors.

#### Testing requirements
- Unit: time-window join returns only events within window.
- Integration: injected correlated pair produces non-zero overlap score.

#### Demo value: ⭐⭐⭐⭐⭐
"Deployment at 14:32 → DB CPU spike at 14:35 → incident at 14:38" is the killer demo moment.

#### Recommended priority: **Sprint 3** (after data alignment)

---

### P0-5 · Explainable RCA

**Status:** ❌ **Missing**

#### What exists
- [`tools/postmortems.py`](file:///c:/Users/prave/Downloads/OPS-Mind-main/opsmind/tools/postmortems.py#L59-L72) `generate_postmortem_content()` has a "Root Cause Analysis" section — it is a **string template** that interpolates `symptom`, `resolution`, `description` fields. The text "Based on the incident data:" is hard-coded boilerplate.
- The LLM is **not** asked to reason about root cause; the section is assembled in Python, not by the model.

#### Gaps
- No causal chain analysis (5-Whys, fault tree, causal graph).
- No LLM-authored RCA narrative grounded on retrieved evidence.
- No contributing factor ranking.
- No human review / edit flow for the generated RCA.
- Static action items ("Improve incident data collection") regardless of actual root cause.

#### Reusable
- `generate_postmortem_content` tool skeleton — replace template content with LLM prompt.
- `get_incident_context` — can feed retrieved chunks to LLM for grounded RCA.
- `save_postmortem` / `list_postmortem_files` — storage layer is correct.

#### Needs to be added
| Component | Notes |
|---|---|
| LLM RCA prompt | System prompt: "Given these evidence chunks, identify root cause using 5-Whys" |
| Grounded generation | Pass top-K RAG chunks + timeline into `generate_content` |
| Contributing factors | Structured output: `{cause, evidence_ids, confidence}` |
| Review interface | Human can edit RCA before finalizing postmortem |

#### Complexity: **Medium**
Primarily prompt engineering + structured output schema; no new infra once RAG (P0-1) is ready.

#### Dependencies
Semantic RAG (P0-1), Evidence Citations (P0-2), Incident Timeline (P0-7).

#### Testing requirements
- Unit: LLM prompt structure test (system + user message shape).
- Integration: known incident → RCA mentions correct symptom and resolution.
- Quality: manual review rubric (not automated).

#### Demo value: ⭐⭐⭐⭐⭐
LLM-authored "The root cause was X because Y, evidenced by incident INC-045" is the core hackathon differentiator.

#### Recommended priority: **Sprint 3**

---

### P0-6 · Similar Incident Intelligence

**Status:** 🟡 **Partially Implemented**

#### What exists
- [`tools/knowledge.py`](file:///c:/Users/prave/Downloads/OPS-Mind-main/opsmind/tools/knowledge.py#L153-L225) `find_similar_issues()`: calls `search_knowledge_base()`, filters for items with resolution text, sorts by **resolution string length** (a proxy, not semantic similarity).
- Returns `type`, `id`, `title`, `description`, `resolution`, `category`, `priority`.

#### Gaps
- Similarity is keyword overlap + resolution-length heuristic — not cosine or BM25.
- No similarity score surfaced to the user.
- Only searches in-memory keyword-matched pool (top 20 from each source); misses semantically similar but keyword-different incidents.
- No "previously resolved by" path or resolution step-by-step extraction.
- No clustering of similar incidents for pattern identification.

#### Reusable
- `find_similar_issues` tool name and return schema.
- Resolution extraction logic (filter for `resolution.name` in `["Resolved","Closed","Done"]`).

#### Needs to be added
| Component | Notes |
|---|---|
| Semantic similarity search | Replace keyword pool with vector index query |
| Similarity score | Cosine distance surfaced per result |
| Resolution extractor | Parse resolution text into actionable steps |
| "Top N similar" ranking | Sorted by score, de-duped |

#### Complexity: **Low** (once RAG is in place)

#### Dependencies
Semantic RAG (P0-1).

#### Testing requirements
- Unit: known similar pair → score > 0.7.
- Integration: `find_similar_issues("redis memory")` returns Redis-related resolved incidents.

#### Demo value: ⭐⭐⭐⭐
"3 similar incidents found. Most similar: INC-0032 (resolved by increasing Redis maxmemory-policy)."

#### Recommended priority: **Sprint 2** (after RAG)

---

### P0-7 · Incident Timeline

**Status:** 🟡 **Partially Implemented**

#### What exists
- [`tools/incidents.py`](file:///c:/Users/prave/Downloads/OPS-Mind-main/opsmind/tools/incidents.py#L280-L387) `get_incident_jira_timeline()`:
  - Adds `incident_opened` event (from `opened_at`).
  - Adds `incident_closed` event if `closed_at` exists.
  - If `jira_issue_key` given: filters issues by that key. Otherwise: takes **first 5 rows from issues CSV** (not correlated).
  - Sorts by timestamp string.

#### Gaps
- Jira events are not time-correlated to the incident; they are just the first 5 CSV rows.
- No events from: deployments, alerts, metric anomalies, on-call pages, log entries.
- No interactive timeline rendering (text only).
- No automatic event deduplication.
- `closed_at` field present in CSV but `resolution` mapped from `closed_code` — schema mismatch affects event descriptions.

#### Reusable
- `get_incident_jira_timeline` tool structure.
- Timeline event schema `{timestamp, event_type, source, description, details}`.
- Sort-by-timestamp logic.

#### Needs to be added
| Component | Notes |
|---|---|
| Time-window Jira join | Filter Jira changelog/comments within incident window |
| Additional event sources | Deployment events, alert firings, metric anomalies |
| Rich event schema | `severity`, `actor`, `affected_service` |
| Timeline rendering | Mermaid sequence diagram or HTML timeline |

#### Complexity: **Medium**

#### Dependencies
Multi-source correlation (P0-4), aligned dataset.

#### Testing requirements
- Unit: timeline events sorted chronologically for known data.
- Integration: `opened_at` event always first, `closed_at` last when present.

#### Demo value: ⭐⭐⭐⭐
Visual Mermaid timeline in chat is highly demo-able.

#### Recommended priority: **Sprint 2**

---

### P0-8 · Human Approval for Risky Actions

**Status:** ❌ **Missing**

#### What exists
- [`core/safety/framework.py`](file:///c:/Users/prave/Downloads/OPS-Mind-main/opsmind/core/safety/framework.py) — guardrail framework with `VALIDATION`, `RATE_LIMITING`, `UI_CONTENT_ESCAPING`.
- `@with_guardrail` decorator blocks execution on strict failures (XSS patterns, field length). **Not** a human approval loop.
- No tool exists that pauses execution and waits for user confirmation.

#### Gaps
- No `approve_action(action_type, description, risk_level)` tool.
- No concept of "risky action" classification.
- No interrupt / resume flow in the ADK agent loop.
- No audit record of what was approved/rejected.
- ADK supports `interrupt` / `resume` patterns but they are not implemented.

#### Reusable
- `GuardrailManager` — extend with a `HUMAN_APPROVAL` guardrail type.
- `check_all` flow — add approval gate as a guardrail step.

#### Needs to be added
| Component | Notes |
|---|---|
| `GuardrailType.HUMAN_APPROVAL` | New guardrail class |
| `tools/approval.py` | `request_human_approval(action, risk, timeout_sec)` |
| ADK interrupt/resume | Use ADK `interrupt` callback to pause pipeline |
| Risk classifier | Tag each remediation tool with risk tier (LOW/MEDIUM/HIGH) |
| Approval log | Append `{action, approved_by, timestamp}` to audit trail |

#### Complexity: **High**
Requires ADK interrupt/resume integration, which is not trivially wired.

#### Dependencies
ADK `interrupt`/callback support, Audit trail (P1-23).

#### Testing requirements
- Unit: HIGH-risk action returns `pending_approval` status.
- Integration: agent pauses, user approves, execution continues.

#### Demo value: ⭐⭐⭐⭐⭐
"Before restarting the database, I need your approval. [Approve] [Reject]" is a standout safety demo.

#### Recommended priority: **Sprint 3**

---

### P0-9 · Safe Runbook-Based Remediation

**Status:** ❌ **Missing**

#### What exists
- Nothing. No runbook data, no runbook tool, no remediation execution.
- The root agent prompt mentions "Best practices for deployment rollbacks" but this is web-search fallback, not a curated runbook library.

#### Gaps
- No runbook store (YAML/Markdown files, database, or Confluence integration).
- No runbook selection logic (match incident category → runbook).
- No step executor (`execute_runbook_step(step_id)`).
- No dry-run mode.
- No rollback capability.

#### Reusable
- `search_knowledge_base` — can be extended to index runbooks.
- GCS storage — runbooks can be stored as GCS blobs alongside postmortems.
- Guardrail decorator — wrap runbook steps with approval (P0-8).

#### Needs to be added
| Component | Notes |
|---|---|
| Runbook YAML schema | `{id, trigger_conditions, steps: [{id, description, command, risk_tier}]}` |
| `data/datasets/runbooks/` | Sample runbooks for demo (restart service, scale deployment, etc.) |
| `tools/runbooks.py` | `search_runbooks(incident_type)`, `execute_runbook_step(step, dry_run)` |
| Step executor | For demo: echo commands; for prod: kubectl / gcloud / shell |
| Runbook agent | ADK `Agent` that selects and walks through steps |

#### Complexity: **High**
Execution safety and dry-run mode are non-trivial; a demo-safe version is Medium complexity.

#### Dependencies
Human approval (P0-8), Incident triage (P0-3) to select runbook.

#### Testing requirements
- Unit: runbook search returns correct runbook for known category.
- Integration: dry-run executes steps and logs output without side effects.

#### Demo value: ⭐⭐⭐⭐⭐
Step-by-step guided remediation is the highest-value agentic behavior to show.

#### Recommended priority: **Sprint 3** (dry-run demo version)

---

### P0-10 · Verification Loop

**Status:** ❌ **Missing**

#### What exists
- Nothing. After a postmortem is saved, the pipeline ends.
- There is no check "did the remediation actually fix the issue?"

#### Gaps
- No `verify_resolution(incident_id)` tool.
- No metric/health-check connector for post-action verification.
- No loop construct in the ADK graph that re-checks after a delay.
- No "resolved" state transition gated on verification.

#### Reusable
- ADK `LoopAgent` (if available) or self-calling agent pattern.
- `get_system_resources` (psutil) — can be extended to check service-specific metrics.

#### Needs to be added
| Component | Notes |
|---|---|
| `tools/verification.py` | `verify_resolution(incident_id, checks: List[HealthCheck])` |
| Health check abstraction | `{name, type: "http"|"metric"|"log", endpoint, expected}` |
| Verification agent | ADK `Agent` that polls checks and reports pass/fail |
| Retry / timeout logic | Max attempts, back-off |
| State update | Mark incident "verified resolved" or "re-opened" |

#### Complexity: **High**
Requires external connectivity for real checks; stubbed version is Medium.

#### Dependencies
Safe remediation (P0-9), Incident state machine (from P0-3).

#### Testing requirements
- Unit: mock health check returns PASS/FAIL correctly.
- Integration: after remediation, verification agent closes incident on PASS.

#### Demo value: ⭐⭐⭐⭐
"Verification check passed: service returned HTTP 200 — incident auto-closed."

#### Recommended priority: **Sprint 4**

---

### P0-11 · Evidence-Backed Postmortem

**Status:** 🟡 **Partially Implemented**

#### What exists
- [`tools/postmortems.py`](file:///c:/Users/prave/Downloads/OPS-Mind-main/opsmind/tools/postmortems.py) `generate_postmortem_content()`:
  - Pulls context from `get_incident_context()` (keyword RAG, capped at 100 rows).
  - Template sections: Executive Summary, Incident Details, Root Cause Analysis, Related Jira Issues, Jira Comments, Timeline, Issue Relationships, Lessons Learned, Action Items.
  - Saves to GCS or local.
- Static "Lessons Learned" / "Action Items" — always the same 3 bullets regardless of incident.
- LLM does **not** write any section; Python assembles the string.

#### Gaps
- RCA, Lessons Learned, Action Items are boilerplate, not evidence-grounded.
- No LLM narrative generation.
- No citation links in the markdown.
- Lessons Learned and Action Items should be derived from the specific incident data.
- Postmortem does not include timeline events (only references jira_changelog manually).

#### Reusable
- `save_postmortem` / `list_postmortem_files` — keep exactly as-is.
- Markdown section structure — keep headings, replace content.
- GCS signed URL and local fallback — production-ready.

#### Needs to be added
| Component | Notes |
|---|---|
| LLM generation prompt | Replace Python string assembly with `generate_content` call |
| Grounded sections | Pass RAG chunks + timeline as context |
| Dynamic Lessons Learned | Derived from `similar_issues` resolutions |
| Dynamic Action Items | Derived from identified root cause |
| Citation in markdown | `[INC-0045][JIRA-WW-712]` inline |

#### Complexity: **Medium**
Primarily prompt engineering; storage layer already complete.

#### Dependencies
Semantic RAG (P0-1), Explainable RCA (P0-5), Incident Timeline (P0-7).

#### Testing requirements
- Unit: generated postmortem contains incident ID and at least one Jira reference.
- Integration: save → list → download round-trip works.
- Quality: RCA section references actual symptom text from the incident.

#### Demo value: ⭐⭐⭐⭐⭐
Downloadable, polished, LLM-authored postmortem with citations is a top-tier demo artifact.

#### Recommended priority: **Sprint 3**

---

### P0-12 · Improved Dashboard

**Status:** ❌ **Missing**

#### What exists
- No custom UI. The only interface is the ADK CLI (`adk run`) or ADK web UI (`adk web`).
- No REST API, no frontend, no dashboard component.
- `output/opsmind.log` contains operational logs but no structured metrics.

#### Gaps
- No incident overview dashboard (active incidents, severity distribution, MTTR).
- No RAG query analytics.
- No postmortem list with status.
- No real-time update stream.
- No visualization of incident timeline or topology.

#### Reusable
- GCS `list_postmortem_files` — can feed a postmortem list panel.
- `get_historical_patterns()` — pandas aggregates can drive charts.
- ADK web UI — can be extended with custom HTML panels if ADK supports it.

#### Needs to be added
| Component | Notes |
|---|---|
| FastAPI app | `opsmind/api/` — `/incidents`, `/postmortems`, `/analytics` endpoints |
| Streamlit or Next.js dashboard | Incident table, severity pie, MTTR trend, timeline viewer |
| WebSocket / SSE | Live incident feed |
| Chart components | Plotly / Recharts |

#### Complexity: **High**
Requires separate web layer; Medium for a Streamlit-only MVP.

#### Dependencies
Persistent incident store, analytics data.

#### Testing requirements
- Unit: API endpoints return correct data shape.
- E2E: dashboard loads and shows at least one incident.

#### Demo value: ⭐⭐⭐⭐⭐
Visual dashboard is essential for hackathon judging — pure chat is not enough for "Improved Dashboard."

#### Recommended priority: **Sprint 4** (Streamlit MVP in Sprint 3)

---

## P1 Features — Detailed Analysis

---

### P1-13 · Change Correlation

**Status:** 🟡 **Partially Implemented**

#### What exists
- `correlate_incident_with_jira()` searches Jira **changelog** entries by symptom keyword.
- `search_jira_changelog()` in [`data/loader.py`](file:///c:/Users/prave/Downloads/OPS-Mind-main/opsmind/data/loader.py#L413-L499) supports `field`, `from_value`, `to_value`, `created_after/before` filters.
- Jira changelog CSV has `field`, `fromString`, `toString`, `created`.

#### Gaps
- Change search term is not passed to `search_jira_changelog` inside `correlate_incident_with_jira` (bug: `search_jira_changelog(limit=10)` only).
- No deployment event source (Git, CI/CD, Helm, kubectl).
- No time-window join to incident `opened_at`.
- No "change caused incident" inference.

#### Needs to be added
- Fix the `correlate_incident_with_jira` bug (pass search term).
- Deployment event connector (GitHub Actions webhook / Cloud Build log).
- Time-window join for change events.

#### Complexity: **Medium**
Bug fix is trivial; deployment connector is Medium.

#### Demo value: ⭐⭐⭐⭐

#### Recommended priority: **Sprint 2** (bug fix first)

---

### P1-14 · Service Topology

**Status:** ❌ **Missing**

#### What exists
- Jira `issuelinks.csv` has `type.name`, `inwardIssue.key`, `outwardIssue.key` — a dependency graph of Jira issues.
- `get_jira_issue_details()` loads issue links.
- No service topology (Kubernetes service graph, APM, service mesh data).

#### Needs to be added
- Service graph data source (k8s API, Datadog APM, or static YAML topology).
- `tools/topology.py` — `get_service_dependencies(service_name)`.
- Graph traversal for blast-radius analysis.
- Topology visualization (Mermaid graph).

#### Complexity: **High**

#### Demo value: ⭐⭐⭐⭐

#### Recommended priority: **Sprint 4**

---

### P1-15 · Alert Deduplication

**Status:** ❌ **Missing**

#### What exists
- `search_incidents()` finds similar incidents by keyword.
- No alert ingestion pipeline, no deduplication logic.

#### Needs to be added
- Alert ingestion tool (`ingest_alert(source, severity, labels)`).
- Deduplication engine: fingerprint alerts by `{source, labels_hash}` with time window.
- Suppress duplicate alerts, group into incident.

#### Complexity: **High**

#### Demo value: ⭐⭐⭐

#### Recommended priority: **Sprint 4**

---

### P1-16 · Incident Clustering

**Status:** ❌ **Missing**

#### What exists
- `get_historical_patterns()` computes pandas `value_counts()` — category/priority distribution. Not clustering.

#### Needs to be added
- Embedding-based clustering of incident descriptions (K-Means or HDBSCAN).
- Cluster labels surfaced in `get_historical_patterns`.
- Auto-assign new incidents to nearest cluster.

#### Complexity: **High**
Requires embeddings (shares infra with P0-1).

#### Demo value: ⭐⭐⭐

#### Recommended priority: **Sprint 4** (after P0-1)

---

### P1-17 · Anomaly Detection

**Status:** ❌ **Missing**

#### What exists
- Nothing related. No metric time-series, no anomaly model.

#### Needs to be added
- Metric ingestion (Cloud Monitoring, Prometheus scrape, or CSV time-series dataset).
- Anomaly model: Z-score baseline or Isolation Forest.
- `tools/anomaly.py` — `detect_anomalies(metric_name, window_hours)`.
- Auto-trigger incident creation on anomaly.

#### Complexity: **Very High**

#### Demo value: ⭐⭐⭐⭐

#### Recommended priority: **Sprint 5+** (post-hackathon)

---

### P1-18 · Recurring Problem Detection

**Status:** 🟡 **Partially Implemented**

#### What exists
- `get_historical_patterns()` — `value_counts()` on category, priority, state. Shows "top categories" but not recurring pattern detection.
- `find_similar_issues()` does surface similar past incidents.

#### Gaps
- No time-series frequency analysis (e.g., "this type of incident recurs every Monday morning").
- No recurrence threshold ("if same category occurs > N times in 30 days → flag as recurring").
- No notification or ticket for recurring problems.

#### Needs to be added
- Time-based frequency analysis in `_analyze_incident_patterns_comprehensive()`.
- `detect_recurring_problems(threshold=3, window_days=30)` tool.
- Recurring pattern report in postmortem "Lessons Learned."

#### Complexity: **Low–Medium**
Pure pandas on existing CSV data.

#### Demo value: ⭐⭐⭐

#### Recommended priority: **Sprint 2** (low effort)

---

### P1-19 · Knowledge Learning Loop

**Status:** ❌ **Missing**

#### What exists
- Postmortems are saved to GCS/local.
- No feedback mechanism; saved postmortems are never re-indexed.

#### Needs to be added
- `ingest_postmortem_to_knowledge_base(postmortem_path)` tool.
- Re-indexing pipeline: parse postmortem markdown → chunks → embeddings → update vector index.
- Explicit feedback tool: `mark_resolution_helpful(incident_id, resolution_id, helpful: bool)`.
- Upvote/downvote weighting in retrieval ranking.

#### Complexity: **High**
Requires persistent vector index and a feedback schema.

#### Demo value: ⭐⭐⭐

#### Recommended priority: **Sprint 4**

---

### P1-20 · Jira Automation

**Status:** ❌ **Missing**

#### What exists
- [`data/connectors/jira.py`](file:///c:/Users/prave/Downloads/OPS-Mind-main/opsmind/data/connectors/jira.py) — read-only REST connector (search, comments, worklogs, changelog). No write methods.
- Baseline doc confirms: "Not implemented: Jira write (create/update issue, comment, transition). Read-only."

#### Needs to be added
| API call | Tool |
|---|---|
| Create issue | `create_jira_issue(summary, description, priority, labels)` |
| Add comment | `add_jira_comment(issue_key, body)` |
| Transition status | `transition_jira_issue(issue_key, new_status)` |
| Link issues | `link_jira_issues(source, target, link_type)` |
| Auto-create on incident | Trigger from triage agent |

#### Complexity: **Medium**
Extend `JiraConnector` with POST methods; auth already in place.

#### Demo value: ⭐⭐⭐⭐
Auto-creating a Jira ticket from a detected incident is highly compelling.

#### Recommended priority: **Sprint 3**

---

### P1-21 · ChatOps

**Status:** ❌ **Missing**

#### What exists
- Nothing. No Slack, Teams, PagerDuty, or webhook integration.
- `requirements.txt` mentions `asyncio-mqtt` as a future comment.

#### Needs to be added
- Slack Events API webhook handler.
- Slash command parser (`/opsmind triage INC-001`).
- Message formatter for incident summaries.
- Bidirectional: agent can post updates to Slack channel.
- Optional: PagerDuty escalation trigger.

#### Complexity: **High**
Requires a webhook server (FastAPI) and Slack app setup.

#### Demo value: ⭐⭐⭐⭐⭐
Live Slack alert → auto-triage → Slack response is the most "production-ready" demo.

#### Recommended priority: **Sprint 4**

---

### P1-22 · Operational Analytics

**Status:** 🟡 **Partially Implemented**

#### What exists
- [`tools/knowledge.py`](file:///c:/Users/prave/Downloads/OPS-Mind-main/opsmind/tools/knowledge.py#L228-L269) `get_historical_patterns()`:
  - `_analyze_incident_patterns_comprehensive()`: total incidents, date range, top categories, priority distribution, state distribution.
  - `_analyze_jira_patterns_comprehensive()`: total issues, top statuses, priorities, issue types, projects, comments/changelog counts.
- `time_period_days` parameter is accepted but **unused** (no date filtering applied).

#### Gaps
- MTTR (mean time to resolution) not computed.
- MTBF (mean time between failures) not computed.
- SLO breach rate not computed.
- Top recurring categories are listed but not trended over time.
- No chart output — text dict only.
- `time_period_days` parameter is silently ignored.

#### Needs to be added
- Fix `time_period_days` filtering in pattern analysis.
- MTTR/MTBF calculation tool.
- Time-series trend output (JSON for chart rendering).
- SLO tracking (requires SLO definitions).

#### Complexity: **Low–Medium**

#### Demo value: ⭐⭐⭐

#### Recommended priority: **Sprint 2**

---

### P1-23 · Audit Trail

**Status:** ❌ **Missing**

#### What exists
- `output/opsmind.log` — Python `logging` to stdout + file. Unstructured text.
- `@with_guardrail` logs warnings when guardrails fire.
- No structured action log, no tamper-evident record, no per-user attribution.

#### Needs to be added
- `opsmind/audit/logger.py` — structured JSONL event log.
- Event schema: `{timestamp, session_id, user_id, action, tool, args_hash, result_code}`.
- Hook into every tool wrapper (`@with_guardrail` or a new `@audit_log` decorator).
- GCS append-only audit log (or Cloud Logging sink).
- `list_audit_events(session_id, start, end)` tool.

#### Complexity: **Medium**

#### Demo value: ⭐⭐⭐
Important for compliance; less flashy in a demo.

#### Recommended priority: **Sprint 3**

---

### P1-24 · RBAC (Role-Based Access Control)

**Status:** ❌ **Missing**

#### What exists
- No auth, no user identity, no role system.
- ADK session has no user context beyond session ID.
- `rate_limiter` guardrail is process-wide (not per-user).

#### Needs to be added
- Identity provider integration (Google OAuth, API key mapping).
- Role definitions: `viewer`, `responder`, `admin`.
- Per-tool role check: `@require_role("responder")`.
- Rate limiting per user identity.
- Token-based session auth if deploying as a REST API.

#### Complexity: **High**
Requires auth layer outside ADK.

#### Demo value: ⭐⭐
Critical for production; low visual demo value.

#### Recommended priority: **Sprint 4** (or post-hackathon)

---

### P1-25 · Advanced Safety Policies

**Status:** 🟡 **Partially Implemented**

#### What exists
- [`core/safety/framework.py`](file:///c:/Users/prave/Downloads/OPS-Mind-main/opsmind/core/safety/framework.py): `GuardrailManager` with `VALIDATION`, `RATE_LIMITING`, `UI_CONTENT_ESCAPING`.
- `@with_guardrail` decorator applied to all `async` tools (not sync tools).
- `data_validation` guardrail: strict, blocks on `<script>` / `javascript:` patterns. But `context['data']` is built from `kwargs.get('data', {})` — **most tools don't pass `data=`**, so the guard sees `{}` and always passes.

#### Gaps
- Guardrails don't inspect actual tool arguments (incident strings, query text, etc.).
- Sync tools (`search_jira_*`, `check_guardrails_health`, `get_system_resources`) bypass `@with_guardrail` entirely.
- Rate limit is process-wide, not per-user.
- No action-level risk policy (`HIGH_RISK`, `MEDIUM_RISK`, `LOW_RISK` classifications).
- No output sanitization (guardrail mutates a local dict, not the return value).
- No deny-list for dangerous runbook commands.
- UI escaping always returns `PASSED` even when it removes content.

#### Needs to be added
- Fix argument binding in `@with_guardrail` to inspect actual positional args.
- Make sync tools async or apply a sync guardrail wrapper.
- Add `ActionRiskGuardrail` — blocks HIGH-risk tools without human approval.
- Per-user rate limit (requires identity, see P1-24).
- Command deny-list for runbook executor.

#### Complexity: **Medium**

#### Demo value: ⭐⭐⭐
Showing "blocked by safety policy" in chat is a good trust-building demo.

#### Recommended priority: **Sprint 2** (fix critical bugs first)

---

### P1-26 · Incident Replay / Simulation

**Status:** ❌ **Missing**

#### What exists
- CSV incident dataset (99 rows) — can serve as replay corpus.
- Pipeline (`listener` → `synthesizer` → `writer`) accepts JSON incident data.

#### Gaps
- No replay driver that injects past incidents into the pipeline in sequence.
- No simulation mode that fakes real-time event delivery.
- No controlled scenario runner for testing agent behavior.
- No comparison of "old vs new" agent responses.

#### Needs to be added
- `scripts/replay_incidents.py` — reads CSV, injects incidents into the pipeline at configurable rate.
- `--dry-run` mode — agent generates analysis without external side effects.
- Scenario YAML: `{name, incidents: [id1, id2], expected_outcome}`.
- Regression test harness comparing postmortem sections.

#### Complexity: **Medium**
Mostly a script + test harness over existing pipeline.

#### Demo value: ⭐⭐⭐⭐
"Let's replay the outage from INC-0045 and show how OpsMind would have responded" is a compelling demo narrative.

#### Recommended priority: **Sprint 3**

---

## Cross-Cutting Issues

> [!CAUTION]
> The following bugs affect multiple features and should be fixed before any new feature work.

### Critical Bugs Found in Source Code

| # | Bug | File | Line | Impact |
|---|-----|------|------|--------|
| B1 | `search_jira_changelog(limit=10)` inside correlation loop — search term not passed | `tools/incidents.py` | 172 | Change correlation broken |
| B2 | `context/retrieval.py` uses wrong column names for comments (`issue_key`, `author.displayName`, `body`) vs CSV (`key`, `comment.author`, `comment.body`) | `context/retrieval.py` | 67–75 | Postmortem Jira data empty |
| B3 | `get_incident_context` uses wrong column names for issuelinks (`sourceIssueKey`, `targetIssueKey`, `linkType.name`) vs CSV (`inwardIssue.key`, `outwardIssue.key`, `type.name`) | `context/retrieval.py` | 91–101 | Issue links missing from RCA |
| B4 | `@with_guardrail` inspects `kwargs.get('data', {})` — most tools pass no `data=` kwarg, so XSS validation always sees `{}` | `tools/guardrail.py` | 36–40 | Safety check bypassed |
| B5 | `search_jira_issues` searches `key` column for `search_term` instead of `summary` | `data/loader.py` | 270–273 | Wrong field searched |
| B6 | `time_period_days` accepted in `get_historical_patterns` but not used | `tools/knowledge.py` | 229 | Analytics filter silently ignored |
| B7 | Signed URL hardcoded to 24 hours, `GCP_FILE_EXPIRATION_DAYS` env var never used | `tools/postmortems.py` | 189 | Config ignored |

---

## Recommended Sprint Plan

```
Sprint 1 (Foundation):
  - Fix critical bugs B1–B7
  - Semantic RAG: embedder + FAISS index (P0-1)
  - Fix column name mismatches in all tools

Sprint 2 (Core Intelligence):
  - Evidence citations (P0-2)
  - Similar incident intelligence (P0-6) — uses new RAG
  - Incident timeline improvements (P0-7)
  - Recurring problem detection (P1-18)
  - Operational analytics fixes (P1-22)
  - Safety guardrail argument binding fix (P1-25 partial)

Sprint 3 (Agentic Workflows):
  - Incident triage agent (P0-3)
  - Explainable LLM-authored RCA (P0-5)
  - Evidence-backed postmortem (P0-11)
  - Jira automation — write tools (P1-20)
  - Incident replay/simulation (P1-26)
  - Audit trail (P1-23)
  - Streamlit dashboard MVP (P0-12 partial)

Sprint 4 (Production Hardening):
  - Human approval loop (P0-8)
  - Safe runbook remediation — dry-run (P0-9)
  - Multi-source correlation (P0-4) — needs aligned data
  - Verification loop (P0-10)
  - ChatOps — Slack integration (P1-21)
  - Full dashboard (P0-12)
  - RBAC skeleton (P1-24)
  - Service topology (P1-14)
  - Knowledge learning loop (P1-19)

Post-Hackathon:
  - Anomaly detection (P1-17)
  - Alert deduplication (P1-15)
  - Incident clustering (P1-16)
```

---

## Dependency Graph

```
P0-1 Semantic RAG
  └─► P0-2 Citations
  └─► P0-6 Similar Incidents
  └─► P0-5 Explainable RCA
        └─► P0-11 Evidence Postmortem
  └─► P1-16 Incident Clustering

P0-3 Incident Triage
  └─► P0-9 Runbook Remediation
        └─► P0-8 Human Approval
              └─► P0-10 Verification Loop

P0-4 Multi-source Correlation ← requires aligned dataset
  └─► P0-7 Timeline (improved)
  └─► P1-13 Change Correlation

P0-12 Dashboard ← needs: P0-1, P0-3, P1-22

P1-20 Jira Automation ← uses existing JiraConnector (extend)

P1-23 Audit Trail ← prerequisite for P1-24 RBAC
```

---

*Report generated from source code inspection — no application files were modified.*
