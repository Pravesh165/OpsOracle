# OPS-Mind Hackathon Roadmap
## "OpsMind — Evidence-Grounded Autonomous Incident Response Copilot"

> **Design rule:** Reuse everything possible. Replace mechanisms, not APIs. Never delete working code.

---

## Target Architecture

```
USER / SLACK / DASHBOARD
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│  root agent  (orchestrator — UPGRADED)                       │
│  ┌──────────┐  ┌────────┐  ┌──────────┐  ┌──────────────┐  │
│  │ triage   │  │  rag   │  │ approval │  │   pipeline   │  │
│  │  agent   │  │ agent  │  │  agent   │  │ (PRESERVED)  │  │
│  └──────────┘  └────────┘  └──────────┘  └──────────────┘  │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  search agent (PRESERVED)                              │  │
│  └────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
        │
        ▼ tools
┌──────────────────────────────────────────────────────────────┐
│ P0: knowledge (UPGRADED) │ incidents (UPGRADED)              │
│ P1: triage (NEW)         │ rca (NEW)                         │
│ P2: runbooks (NEW)       │ approval (NEW)                    │
│ P3: verification (NEW)   │ postmortems (UPGRADED)            │
│ P4: audit (NEW)          │ guardrail (UPGRADED)              │
└──────────────────────────────────────────────────────────────┘
        │
        ▼ retrieval
┌──────────────────────────────────────────────────────────────┐
│  opsmind/retrieval/  (NEW MODULE)                            │
│  embedder.py │ index.py (FAISS) │ hybrid.py (BM25+dense)    │
└──────────────────────────────────────────────────────────────┘
        │
        ▼ data
┌──────────────────────────────────────────────────────────────┐
│  loader.py (BUG-FIXED) │ manager.py (WIRED) │ connectors/   │
│  datasets/incidents/ │ datasets/jira/ │ datasets/runbooks/   │
└──────────────────────────────────────────────────────────────┘
        │
        ▼ storage / ui
┌──────────────────────────────────────────────────────────────┐
│  GCS (PRESERVED) │ local output/ │ Streamlit dashboard (NEW) │
└──────────────────────────────────────────────────────────────┘
```

---

## What Is Preserved, Upgraded, or New

### ✅ PRESERVED AS-IS (do not touch)
| Component | File(s) |
|-----------|---------|
| ADK entry point | `opsmind/agent.py` |
| Pipeline SequentialAgent | `core/agents/pipeline.py` |
| Listener agent | `core/agents/listener.py` |
| Search agent | `core/agents/search.py` |
| Base connector + ConnectorManager | `data/connectors/base.py`, `data/connectors/manager.py` |
| JiraConnector (live REST) | `data/connectors/jira.py` |
| GCS upload/download/list | `utils/gcp_storage.py` |
| `save_postmortem` + `list_postmortem_files` | `tools/postmortems.py` (storage half) |
| `safe_get`, `safe_json_loads`, `clean_nan_values` | `utils/helpers.py` |
| Config + env template | `config/settings.py`, `env.template` |
| `GuardrailManager` class + `BaseGuardrail` ABC | `core/safety/framework.py` |
| Deploy script | `deploy.sh`, `DEPLOYMENT.md` |

### 🔧 UPGRADED (same file, same API, better internals)
| Component | File(s) | Change |
|-----------|---------|--------|
| `search_knowledge_base` | `tools/knowledge.py` | Swap keyword search → hybrid RAG retriever |
| `answer_devops_question` | `tools/knowledge.py` | Add evidence citation objects + confidence per item |
| `find_similar_issues` | `tools/knowledge.py` | Use semantic similarity score instead of resolution-string-length sort |
| `get_historical_patterns` | `tools/knowledge.py` | Fix `time_period_days` filtering; add MTTR/recurring |
| `get_incident_context` | `context/retrieval.py` | Fix column name bugs; delegate to retrieval module |
| `correlate_incident_with_jira` | `tools/incidents.py` | Fix changelog search-term bug; add time-window join |
| `get_incident_jira_timeline` | `tools/incidents.py` | Replace `head(5)` fallback with time-window correlation |
| `search_jira_issues` | `data/loader.py` | Fix: search `summary` column, not `key` |
| `generate_postmortem_content` | `tools/postmortems.py` | Replace string template with LLM generation |
| `with_guardrail` decorator | `tools/guardrail.py` | Fix arg binding so actual inputs are inspected |
| Root agent instruction + tool list | `core/agents/root.py` | Add new tools; update system prompt |
| Writer agent | `core/agents/writer.py` | Add citation rendering; call LLM RCA |
| Synthesizer agent | `core/agents/synthesizer.py` | Use new retriever; output structured evidence |
| `DataManager` | `data/manager.py` | Wire to agents via `context/interface.py` |

### 🆕 NEW (net-new files)
| Module | Files | Purpose |
|--------|-------|---------|
| Retrieval | `opsmind/retrieval/__init__.py` | Package |
| | `opsmind/retrieval/embedder.py` | `embed_texts()` via Gemini API |
| | `opsmind/retrieval/index.py` | FAISS vector store wrapper |
| | `opsmind/retrieval/hybrid.py` | BM25 + dense merge, re-rank |
| | `opsmind/retrieval/chunker.py` | Text splitter for long documents |
| | `scripts/build_index.py` | One-shot index build from CSVs |
| Triage | `opsmind/tools/triage.py` | Severity scoring, routing |
| | `opsmind/core/agents/triage_agent.py` | ADK agent for triage workflow |
| RCA | `opsmind/tools/rca.py` | LLM-grounded root cause analysis |
| Runbooks | `opsmind/tools/runbooks.py` | Search + step executor (dry-run) |
| | `opsmind/data/datasets/runbooks/*.yaml` | Sample runbook library |
| Approval | `opsmind/tools/approval.py` | Human-in-the-loop gate |
| | `opsmind/core/agents/approval_agent.py` | ADK agent for approval workflow |
| Verification | `opsmind/tools/verification.py` | Post-remediation health checks |
| | `opsmind/core/agents/verification_agent.py` | ADK agent for verify loop |
| Audit | `opsmind/audit/__init__.py` | Package |
| | `opsmind/audit/logger.py` | Structured JSONL audit log |
| | `opsmind/audit/decorator.py` | `@audit_action` decorator |
| Dashboard | `dashboard/app.py` | Streamlit app |
| | `dashboard/pages/incidents.py` | Incident table + severity chart |
| | `dashboard/pages/postmortems.py` | Postmortem list + viewer |
| | `dashboard/pages/analytics.py` | MTTR, patterns, recurring |
| | `dashboard/pages/timeline.py` | Mermaid timeline renderer |
| Datasets | `opsmind/data/datasets/runbooks/` | 5-10 YAML runbooks for demo |
| Tests | `tests/__init__.py` | Package |
| | `tests/test_retrieval.py` | Index + hybrid search |
| | `tests/test_triage.py` | Severity scorer |
| | `tests/test_rca.py` | RCA output structure |
| | `tests/test_postmortem.py` | Generation + save round-trip |
| | `tests/test_approval.py` | Approval gate |
| | `tests/test_guardrails.py` | Arg binding |
| | `tests/test_loader.py` | Column fix regressions |
| | `tests/fixtures/` | Sample incident + Jira JSON |

---

## Phase Details

---

## Phase 0 — Baseline Stabilization

**Objective:** Fix all 7 critical bugs. Make the existing system actually work before adding anything new.

### Files to Modify
| File | Change |
|------|--------|
| `opsmind/tools/incidents.py` | **B1:** Pass `search_term` to `search_jira_changelog()` in `correlate_incident_with_jira` |
| `opsmind/context/retrieval.py` | **B2:** Fix comment column names (`key`→`issue_key`, `comment.author`→`author`, `comment.body`→`body`) |
| `opsmind/context/retrieval.py` | **B3:** Fix issuelinks column names (`sourceIssueKey`→`inwardIssue.key`, `targetIssueKey`→`outwardIssue.key`, `linkType.name`→`type.name`) |
| `opsmind/tools/guardrail.py` | **B4:** Fix `with_guardrail` to bind actual positional args into context `data` dict |
| `opsmind/data/loader.py` | **B5:** `search_jira_issues` — search `summary` column, not `key` column |
| `opsmind/tools/knowledge.py` | **B6:** Apply `time_period_days` date filter in `get_historical_patterns` |
| `opsmind/tools/postmortems.py` | **B7:** Replace hardcoded `expiration_hours=24` with `GCP_FILE_EXPIRATION_DAYS` from config |

### New Files
| File | Purpose |
|------|---------|
| `tests/__init__.py` | Create test package |
| `tests/fixtures/sample_incident.json` | Known incident for regression tests |
| `tests/fixtures/sample_jira_issue.json` | Known Jira issue for regression tests |
| `tests/test_loader.py` | Verify column-name bug fixes don't regress |

### Dependencies
None — pure bug fixes, no new packages.

### Implementation Order
1. Fix B5 (`search_jira_issues` column) — highest impact on search quality.
2. Fix B1 (changelog search term) — correlation quality.
3. Fix B2 + B3 (retrieval column names) — postmortem Jira data.
4. Fix B4 (guardrail arg binding) — safety correctness.
5. Fix B6 (time_period_days) — analytics.
6. Fix B7 (GCP expiration) — config honesty.
7. Write fixture files + `test_loader.py`.

### Tests
- `test_loader.py::test_search_jira_issues_uses_summary_column`
- `test_loader.py::test_search_jira_changelog_passes_term`
- `test_loader.py::test_retrieval_comment_columns_match_csv`
- `test_loader.py::test_retrieval_issuelinks_columns_match_csv`

### Acceptance Criteria
- `search_jira_issues("nginx")` returns rows where `summary` contains "nginx" (not `key`).
- `correlate_incident_with_jira("INC0000001")` returns non-empty `related_changelog`.
- `get_incident_context("database")` returns items with non-empty `body` fields from comments.
- Guardrail `check_all` receives non-empty `data` dict when a query string is passed.
- All 4 tests pass.

---

## Phase 1 — Semantic / Hybrid RAG

**Objective:** Replace keyword `str.contains` with embedding-based retrieval. Keep all existing tool names and signatures.

### Files to Modify
| File | Change |
|------|--------|
| `opsmind/context/retrieval.py` | Replace inline keyword loop with call to `opsmind.retrieval.hybrid.search()` |
| `opsmind/tools/knowledge.py` | `search_knowledge_base` → delegate to `hybrid.search()`; keep return schema |
| `opsmind/tools/knowledge.py` | `find_similar_issues` → sort by `similarity_score` from retriever, not resolution-length |
| `opsmind/tools/knowledge.py` | `answer_devops_question` → attach per-item similarity scores to evidence list |
| `opsmind/data/manager.py` | Wire `DataManager` query to use `hybrid.search()` when index exists |
| `requirements.txt` | Add `faiss-cpu`, `rank-bm25`, `google-genai` (if not already present) |
| `pyproject.toml` | Sync deps with `requirements.txt` |

### New Files
| File | Purpose |
|------|---------|
| `opsmind/retrieval/__init__.py` | Exports: `search`, `build_index`, `embed` |
| `opsmind/retrieval/embedder.py` | `embed_texts(texts: List[str]) → np.ndarray` via `genai.embed_content` |
| `opsmind/retrieval/chunker.py` | `chunk_document(text, max_tokens=512) → List[str]` |
| `opsmind/retrieval/index.py` | `VectorIndex`: `build(docs)`, `search(query_vec, k)`, `save(path)`, `load(path)` using FAISS |
| `opsmind/retrieval/hybrid.py` | `search(query, k, alpha=0.5) → List[RankedResult]`; merges BM25 + dense scores |
| `scripts/build_index.py` | CLI: reads CSVs → chunks → embeds → saves FAISS index to `output/opsmind.index` |
| `tests/test_retrieval.py` | Unit + integration tests |

### Dependencies
```
faiss-cpu>=1.7.4
rank-bm25>=0.2.2
google-genai>=0.8.0   # already likely present via google-adk
numpy>=1.21.0          # already present
```

### Implementation Order
1. `chunker.py` — text splitting (no external deps).
2. `embedder.py` — Gemini embedding call.
3. `index.py` — FAISS wrapper + save/load.
4. `scripts/build_index.py` — build index from CSVs; verify with a test query.
5. `hybrid.py` — BM25 index from same corpus + merge.
6. Update `context/retrieval.py` to call `hybrid.search()`.
7. Update `tools/knowledge.py` to use hybrid results.
8. Update `find_similar_issues` sort to use `similarity_score`.
9. Write tests.

### Tests
```
test_retrieval.py::test_embedder_returns_correct_shape
test_retrieval.py::test_index_build_and_query
test_retrieval.py::test_hybrid_search_returns_ranked_results
test_retrieval.py::test_known_incident_top_result  # "redis memory" → redis incident
test_retrieval.py::test_index_save_load_roundtrip
```

### Acceptance Criteria
- `search_knowledge_base("redis out of memory")` returns a result with `similarity_score > 0.5` for a redis-related record.
- `find_similar_issues("nginx 502")` returns results sorted by `similarity_score` descending.
- Index builds from CSVs in < 30 seconds on demo machine.
- Index loads from disk; tool calls do not re-embed on every invocation.
- Existing tool return schemas unchanged (no breakage to root agent).

---

## Phase 2 — Incident Triage

**Objective:** Auto-classify incoming incidents by severity, route to team, track state. Wire into the existing pipeline.

### Files to Modify
| File | Change |
|------|--------|
| `opsmind/core/agents/listener.py` | After `process_incident_stream`, trigger `triage_agent` |
| `opsmind/core/agents/root.py` | Add `triage_incident` and `get_triage_status` to tool list; add `triage_agent` as sub-agent |
| `opsmind/core/agents/pipeline.py` | Insert triage step between listener and synthesizer |

### New Files
| File | Purpose |
|------|---------|
| `opsmind/tools/triage.py` | `triage_incident(incident_data)` → `{severity, team, urgency, confidence, routing_reason}` |
| | `get_triage_status(incident_id)` → current state from session |
| | `transition_incident_state(incident_id, new_state)` → state machine |
| | `_severity_score(priority, category, keywords)` → float 0–1 |
| `opsmind/core/agents/triage_agent.py` | ADK `Agent` with tools: `triage_incident`, `transition_incident_state`, `search_incidents` |
| `tests/test_triage.py` | Severity scorer + routing logic tests |

### Triage State Machine
```
DETECTED → TRIAGED → ACKNOWLEDGED → MITIGATING → RESOLVED → CLOSED
                                  ↘ ESCALATED ↗
```
States stored in `tool_context.state["incident_states"][incident_id]`.

### Severity Scoring Logic (rules-based v1)
```python
# In triage.py
SEVERITY_MATRIX = {
    ("P1", "network"):    1.0,
    ("P1", "database"):   0.95,
    ("P1", "security"):   1.0,
    ("P2", "network"):    0.7,
    ("P2", "database"):   0.65,
    ...
}
# Keyword boosters: "outage"→+0.2, "data loss"→+0.3, "customer"→+0.15
```

### Dependencies
None new — pure Python.

### Implementation Order
1. `tools/triage.py` — severity matrix + state machine functions.
2. `core/agents/triage_agent.py` — ADK Agent wrapping triage tools.
3. Modify `pipeline.py` — insert triage between listener and synthesizer.
4. Modify `root.py` — add triage tools + sub-agent.
5. Tests.

### Tests
```
test_triage.py::test_p1_network_is_critical
test_triage.py::test_outage_keyword_boosts_severity
test_triage.py::test_state_transition_valid
test_triage.py::test_state_transition_invalid_raises
test_triage.py::test_triage_returns_routing_team
```

### Acceptance Criteria
- `triage_incident({priority:"P1", category:"network", symptom:"site outage"})` returns `severity ≥ 0.9` and `team = "network-ops"`.
- Incident state persists in session: `DETECTED → TRIAGED` transition works.
- Root agent can query triage status for a known incident ID.
- Pipeline auto-triages an injected incident JSON without user prompting.

---

## Phase 3 — Explainable RCA + Evidence Citations

**Objective:** Replace static postmortem template with LLM-authored RCA grounded on retrieved evidence with citations.

### Files to Modify
| File | Change |
|------|--------|
| `opsmind/tools/postmortems.py` | `generate_postmortem_content`: replace Python string assembly with LLM call; add citation rendering |
| `opsmind/tools/knowledge.py` | `answer_devops_question`: add `citation_id` field to each evidence item |
| `opsmind/tools/incidents.py` | `get_incident_jira_timeline`: use time-window correlation (from Phase 2 correlation fix) |
| `opsmind/core/agents/synthesizer.py` | Update instruction to produce structured evidence JSON, not prose |
| `opsmind/core/agents/writer.py` | Update to pass evidence + timeline to `generate_postmortem_content`; render citations |

### New Files
| File | Purpose |
|------|---------|
| `opsmind/tools/rca.py` | `generate_rca(incident_id, evidence_chunks, timeline) → {root_cause, contributing_factors, confidence, evidence_ids}` |
| | `format_citations(evidence_list) → str` — render `[INC-001][JIRA-WW-712]` inline |
| | `extract_action_items(rca_result, similar_resolutions) → List[str]` |
| | `extract_lessons_learned(rca_result, incident_data) → List[str]` |
| `tests/test_rca.py` | RCA structure + citation tests |

### RCA Generation Pattern
```python
# In rca.py — generates via Gemini, grounded on context
system_prompt = """
You are an SRE expert performing root cause analysis.
Given: incident data, evidence chunks, timeline events, similar past incidents.
Output JSON: {root_cause, contributing_factors:[{factor,evidence_id,confidence}], 
              recommended_actions, lessons_learned}
Be specific. Reference evidence by ID. Use 5-Whys reasoning.
"""
```

### Evidence Citation Format
```markdown
The root cause was a misconfigured nginx upstream timeout [INC-0045].
A similar issue was resolved by increasing `proxy_read_timeout` [JIRA-WW-712][INC-0032].
```

### Dependencies
None new — uses existing `google-adk` / `google-genai`.

### Implementation Order
1. `tools/rca.py` — `generate_rca()` with Gemini structured output.
2. `tools/rca.py` — `format_citations()` and `extract_action_items()`.
3. Update `tools/postmortems.py` — call `generate_rca` + `format_citations`.
4. Update `core/agents/writer.py` — pass evidence to writer.
5. Update `core/agents/synthesizer.py` — structured evidence output.
6. Tests.

### Tests
```
test_rca.py::test_rca_output_has_required_fields
test_rca.py::test_format_citations_renders_brackets
test_rca.py::test_extract_action_items_returns_list
test_postmortem.py::test_generated_postmortem_contains_incident_id
test_postmortem.py::test_generated_postmortem_has_citation
test_postmortem.py::test_save_list_download_roundtrip  # existing storage preserved
```

### Acceptance Criteria
- `generate_postmortem_content("INC0000001")` returns LLM-authored RCA text (not the old boilerplate).
- Postmortem markdown contains at least one `[INC-*]` or `[JIRA-*]` citation.
- "Lessons Learned" section differs between two different incidents.
- `save_postmortem` / `list_postmortem_files` still work unchanged (storage layer preserved).

---

## Phase 4 — Human Approval + Safe Runbook Remediation

**Objective:** Gate risky actions behind a human approval step. Provide runbook-guided dry-run remediation.

### Files to Modify
| File | Change |
|------|--------|
| `opsmind/core/safety/framework.py` | Add `GuardrailType.HUMAN_APPROVAL` + `HumanApprovalGuardrail` class |
| `opsmind/tools/guardrail.py` | Add `@require_approval(risk_tier)` decorator; add `initialize_guardrails` to include approval guardrail |
| `opsmind/core/agents/root.py` | Add `request_approval`, `execute_runbook_step`, `search_runbooks` to tool list; add approval + runbook agents as sub-agents |
| `requirements.txt` | Add `pyyaml>=6.0` for runbook YAML parsing |

### New Files
| File | Purpose |
|------|---------|
| `opsmind/tools/approval.py` | `request_human_approval(action, description, risk_tier)` → stores pending approval in session state |
| | `approve_action(approval_id)` / `reject_action(approval_id)` → user-callable tools |
| | `get_pending_approvals(tool_context)` → list all pending |
| `opsmind/core/agents/approval_agent.py` | ADK `Agent` that pauses workflow, requests approval, resumes on response |
| `opsmind/tools/runbooks.py` | `search_runbooks(incident_type, category)` → match from YAML library |
| | `get_runbook_steps(runbook_id)` → ordered step list |
| | `execute_runbook_step(runbook_id, step_id, dry_run=True)` → log or execute |
| | `_classify_step_risk(step)` → `LOW/MEDIUM/HIGH` |
| `opsmind/core/agents/runbook_agent.py` | ADK `Agent` that walks runbook steps, calls approval for HIGH-risk |
| `opsmind/data/datasets/runbooks/restart_service.yaml` | Demo runbook: restart a service |
| `opsmind/data/datasets/runbooks/scale_deployment.yaml` | Demo runbook: scale replicas |
| `opsmind/data/datasets/runbooks/db_failover.yaml` | Demo runbook: database failover |
| `opsmind/data/datasets/runbooks/flush_cache.yaml` | Demo runbook: clear cache |
| `opsmind/data/datasets/runbooks/rollback_deployment.yaml` | Demo runbook: deployment rollback |
| `tests/test_approval.py` | Approval gate unit tests |

### Runbook YAML Schema
```yaml
# restart_service.yaml
id: restart_service
name: Restart Application Service
trigger_conditions:
  - category: software
  - keywords: [crash, not responding, hang]
steps:
  - id: check_health
    description: Check service health endpoint
    command: "curl -f http://{service_host}/health"
    risk_tier: LOW
    dry_run_output: "HTTP 503 Service Unavailable (simulated)"
  - id: graceful_restart
    description: Gracefully restart the service
    command: "systemctl restart {service_name}"
    risk_tier: MEDIUM
    dry_run_output: "Would restart {service_name} (dry-run)"
  - id: verify_health
    description: Verify service health after restart
    command: "curl -f http://{service_host}/health"
    risk_tier: LOW
    dry_run_output: "HTTP 200 OK (simulated)"
```

### Approval Flow (session-state based)
```
runbook_agent calls execute_runbook_step (HIGH risk)
  → @require_approval fires
  → request_human_approval(action, risk=HIGH) stores {approval_id, status: PENDING}
  → agent responds: "⚠️ Awaiting your approval. ID: APR-001"
  → USER: "approve APR-001"
  → root agent calls approve_action("APR-001")
  → runbook_agent resumes execution
```

### Dependencies
```
pyyaml>=6.0
```

### Implementation Order
1. `data/datasets/runbooks/*.yaml` — 5 sample runbooks.
2. `tools/runbooks.py` — `search_runbooks`, `get_runbook_steps`, `execute_runbook_step` (dry-run only first).
3. `tools/approval.py` — session-state approval gate.
4. `core/safety/framework.py` — `HumanApprovalGuardrail`.
5. `tools/guardrail.py` — `@require_approval` decorator.
6. `core/agents/approval_agent.py` + `core/agents/runbook_agent.py`.
7. Update `core/agents/root.py`.
8. Tests.

### Tests
```
test_approval.py::test_high_risk_step_creates_pending_approval
test_approval.py::test_approve_action_clears_pending
test_approval.py::test_reject_action_blocks_execution
test_approval.py::test_low_risk_step_skips_approval
tests/test_runbooks.py::test_search_runbooks_by_category
tests/test_runbooks.py::test_dry_run_returns_simulated_output
tests/test_runbooks.py::test_execute_real_blocks_without_approval
```

### Acceptance Criteria
- `execute_runbook_step("restart_service", "graceful_restart", dry_run=True)` returns simulated output without executing anything.
- A HIGH-risk step creates a pending approval record in session state.
- `approve_action(id)` → step executes (dry-run mode still, just unblocked).
- `reject_action(id)` → step returns `{"status": "rejected"}` and pipeline stops.
- Root agent displays pending approvals when user asks "what needs my approval?"

---

## Phase 5 — Verification Loop

**Objective:** After remediation, verify the fix actually worked. Auto-close incident on success; re-open on failure.

### Files to Modify
| File | Change |
|------|--------|
| `opsmind/core/agents/root.py` | Add `verify_resolution`, `run_health_check` to tool list; add `verification_agent` |
| `opsmind/tools/triage.py` | Add `close_incident(incident_id)` and `reopen_incident(incident_id)` transitions |

### New Files
| File | Purpose |
|------|---------|
| `opsmind/tools/verification.py` | `verify_resolution(incident_id, checks)` → poll health checks, return PASS/FAIL |
| | `run_health_check(check: HealthCheck)` → execute single check |
| | `_http_check(url, expected_status)` → HTTP GET with timeout |
| | `_metric_check(metric_name, threshold)` → stub for demo |
| | `_log_check(pattern, last_n_lines)` → stub for demo |
| `opsmind/core/agents/verification_agent.py` | ADK `Agent` that runs checks, updates incident state |
| `tests/test_verification.py` | Mock health check tests |

### Health Check Schema (session-state)
```python
@dataclass
class HealthCheck:
    name: str
    type: Literal["http", "metric", "log"]
    endpoint: str          # URL / metric name / log path
    expected: str          # "200" / "<100" / "no errors"
    timeout_sec: int = 10
    max_retries: int = 3
```

### Verification Flow
```
runbook_agent completes final step
  → verification_agent called automatically
  → run_health_check for each configured check
  → ALL pass  → transition_incident_state(id, "RESOLVED")
               → trigger postmortem generation
  → ANY fail  → transition_incident_state(id, "MITIGATING")
               → re-notify team
               → offer next runbook step or escalation
```

### Dependencies
None new — `aiohttp` already present.

### Implementation Order
1. `tools/verification.py` — `_http_check` (real), `_metric_check` + `_log_check` (stubs).
2. `tools/verification.py` — `verify_resolution` orchestrator.
3. `core/agents/verification_agent.py`.
4. Add `close_incident` / `reopen_incident` to `triage.py`.
5. Update `root.py`.
6. Tests.

### Tests
```
test_verification.py::test_http_check_pass_on_200
test_verification.py::test_http_check_fail_on_503
test_verification.py::test_verify_resolution_all_pass_closes_incident
test_verification.py::test_verify_resolution_any_fail_reopens
test_verification.py::test_metric_check_stub_returns_pending
```

### Acceptance Criteria
- `verify_resolution("INC0000001", [{"type":"http","endpoint":"http://httpbin.org/status/200","expected":"200"}])` returns `PASS`.
- Verified-resolved incident transitions to `RESOLVED` state.
- Failed check transitions incident back to `MITIGATING`.
- Verification agent auto-triggers postmortem generation on `RESOLVED`.

---

## Phase 6 — Evidence-Backed Postmortem + Knowledge Learning

**Objective:** Postmortem is fully LLM-authored with citations. Saved postmortems are re-ingested into the RAG index (learning loop).

### Files to Modify
| File | Change |
|------|--------|
| `opsmind/tools/postmortems.py` | Call `rca.generate_rca()` + `rca.format_citations()`; dynamic lessons/actions |
| `opsmind/core/agents/writer.py` | Pass full evidence bundle (RAG chunks + timeline + triage result) to postmortem generator |
| `requirements.txt` | Add `mistune` or `markdown` for postmortem parsing |

### New Files
| File | Purpose |
|------|---------|
| `opsmind/tools/learning.py` | `ingest_postmortem(postmortem_path)` → parse → chunk → embed → upsert to index |
| | `mark_resolution_helpful(incident_id, helpful: bool)` → upvote weight in index |
| | `get_knowledge_stats()` → index size, last updated, top sources |
| `tests/test_postmortem.py` | Full postmortem generation + learning loop |

### Learning Loop Flow
```
save_postmortem(content)
  → GCS / local saved
  → ingest_postmortem(path)
      → parse markdown sections
      → chunk each section
      → embed chunks
      → upsert into FAISS index with metadata {source: "postmortem", incident_id}
  → next query to search_knowledge_base benefits from this incident's data
```

### Dependencies
```
mistune>=3.0.0   # markdown parser for learning loop
```

### Implementation Order
1. `tools/learning.py` — `ingest_postmortem` that reads saved markdown, chunks, embeds, upserts.
2. `tools/learning.py` — `mark_resolution_helpful`.
3. Update `tools/postmortems.py` — call `ingest_postmortem` after `save_postmortem`.
4. Update `core/agents/writer.py` — pass full evidence bundle.
5. Tests.

### Tests
```
test_postmortem.py::test_full_postmortem_is_llm_authored
test_postmortem.py::test_postmortem_contains_rca_section
test_postmortem.py::test_postmortem_learning_increases_index_size
test_postmortem.py::test_helpful_mark_updates_weight
test_postmortem.py::test_save_and_list_roundtrip  # must still pass
```

### Acceptance Criteria
- Generated postmortem RCA is different prose for different incidents (not the same 3-bullet boilerplate).
- After saving a postmortem, `get_knowledge_stats()` shows increased document count.
- `search_knowledge_base` can surface content from a previously saved postmortem.
- `save_postmortem` + `list_postmortem_files` still work (no regression).

---

## Phase 7 — Streamlit Dashboard

**Objective:** Visual UI for incidents, postmortems, analytics, and timeline. Runs alongside ADK web.

### Files to Modify
| File | Change |
|------|--------|
| `requirements.txt` | Add `streamlit>=1.35`, `plotly>=5.20`, `mistune>=3.0` |
| `Makefile` | Add `dashboard` target: `streamlit run dashboard/app.py` |

### New Files
| File | Purpose |
|------|---------|
| `dashboard/__init__.py` | Package |
| `dashboard/app.py` | Main Streamlit app with nav sidebar |
| `dashboard/pages/incidents.py` | Live incident table; severity pie chart; filter by state/priority |
| `dashboard/pages/postmortems.py` | Postmortem list from GCS/local; inline viewer; download link |
| `dashboard/pages/analytics.py` | MTTR trend, top categories, recurring pattern table |
| `dashboard/pages/timeline.py` | Mermaid sequence diagram renderer from timeline JSON |
| `dashboard/pages/knowledge.py` | Knowledge base stats; recent searches; top similar incidents |
| `dashboard/data_bridge.py` | Thin wrapper: calls `load_incident_data()`, `load_jira_data()`, `list_postmortem_files()` |
| `dashboard/charts.py` | Plotly chart helpers: `severity_pie()`, `mttr_trend()`, `category_bar()` |

### Dashboard Pages
```
Sidebar Nav:
  🏠 Overview          — summary KPIs: active incidents, avg MTTR, postmortem count
  🚨 Incidents         — table with state filter; click → detail modal
  📋 Postmortems       — list + inline markdown viewer + download
  📊 Analytics         — MTTR trend, top categories, recurring problems
  🕐 Timeline          — select incident → mermaid timeline
  🧠 Knowledge Stats   — index size, top retrieved, recent queries
```

### Dependencies
```
streamlit>=1.35.0
plotly>=5.20.0
mistune>=3.0.0
```

### Implementation Order
1. `dashboard/data_bridge.py` — wires to existing data loaders.
2. `dashboard/charts.py` — Plotly helpers.
3. `dashboard/pages/incidents.py` — table + severity chart.
4. `dashboard/pages/postmortems.py` — list + viewer.
5. `dashboard/pages/analytics.py` — MTTR + patterns.
6. `dashboard/pages/timeline.py` — Mermaid renderer.
7. `dashboard/app.py` — main app with sidebar.
8. Update `Makefile`.

### Tests
```
# Dashboard tests are integration/visual — manual for hackathon
# Automated: test data_bridge returns correct shapes
tests/test_dashboard_bridge.py::test_incidents_returns_dataframe
tests/test_dashboard_bridge.py::test_postmortems_list_is_list
```

### Acceptance Criteria
- `make dashboard` launches Streamlit on `localhost:8501`.
- Incidents page shows all rows from `incident_event_log.csv`.
- Postmortems page shows all saved `.md` files with download links.
- Analytics page renders MTTR trend chart (even if data is mock).
- Timeline page renders a Mermaid diagram for INC0000001.

---

## Phase 8 — Optional Integrations (Jira Write + Audit Trail)

**Objective:** Auto-create Jira tickets from incidents. Structured audit log for all agent actions.

### Priority 8a: Jira Write

#### Files to Modify
| File | Change |
|------|--------|
| `opsmind/data/connectors/jira.py` | Add `create_issue()`, `add_comment()`, `transition_issue()`, `link_issues()` async methods |
| `opsmind/core/agents/root.py` | Add `create_jira_ticket`, `add_jira_comment` to tool list |

#### New Files
| File | Purpose |
|------|---------|
| `opsmind/tools/jira_write.py` | `create_jira_ticket(summary, description, priority, labels)` |
| | `add_jira_comment(issue_key, body)` |
| | `transition_jira_issue(issue_key, new_status)` |

#### Acceptance Criteria
- `create_jira_ticket(...)` returns a new issue key (or simulated key in test mode).
- Triage agent auto-creates a Jira ticket for P1 incidents.

---

### Priority 8b: Audit Trail

#### New Files
| File | Purpose |
|------|---------|
| `opsmind/audit/__init__.py` | Package |
| `opsmind/audit/logger.py` | `AuditLogger`: writes JSONL to `output/audit.jsonl` + optional GCS |
| `opsmind/audit/decorator.py` | `@audit_action(action_type)` decorator for tools |
| `opsmind/tools/audit_tools.py` | `list_audit_events(start, end, session_id)` tool for root agent |

#### Audit Event Schema
```json
{
  "timestamp": "2026-10-03T18:00:00Z",
  "session_id": "abc123",
  "action": "triage_incident",
  "tool": "triage_incident",
  "args_summary": {"incident_id": "INC0000001", "priority": "P1"},
  "result_code": "success",
  "duration_ms": 245
}
```

#### Acceptance Criteria
- Every tool call annotated with `@audit_action` writes a JSONL line to `output/audit.jsonl`.
- `list_audit_events()` returns events filterable by time range.

---

## Phase 9 — Testing + Demo Hardening

**Objective:** Full test suite. Incident replay script. Demo scenario script.

### New Files
| File | Purpose |
|------|---------|
| `tests/test_guardrails.py` | Arg binding, rate limit, XSS block |
| `tests/test_triage.py` | Full triage workflow (if not done in Phase 2) |
| `tests/test_rca.py` | RCA + citation output |
| `tests/test_approval.py` | Full approval gate workflow |
| `tests/test_verification.py` | Health check + incident state |
| `tests/test_postmortem.py` | End-to-end postmortem |
| `tests/test_learning.py` | Knowledge loop |
| `tests/conftest.py` | Shared fixtures: sample incident, sample Jira |
| `scripts/replay_incidents.py` | Inject CSV incidents into pipeline at configurable rate |
| `scripts/demo_scenario.py` | End-to-end demo: inject INC0000001 → triage → RCA → postmortem |
| `scripts/seed_demo_data.py` | Generate aligned incident+Jira sample data for demo |

### Replay Script Interface
```bash
python scripts/replay_incidents.py \
  --incident-id INC0000001 \
  --dry-run \
  --verbose
# Outputs: triage result, evidence, RCA, postmortem path
```

### Demo Scenario Script
```bash
python scripts/demo_scenario.py
# 1. Inject INC0000001 (P1, network outage)
# 2. Auto-triage → CRITICAL, routes to network-ops
# 3. Search runbook: restart_service
# 4. Request approval for MEDIUM-risk step
# 5. User approves → dry-run executes
# 6. Verification check → PASS
# 7. Generate postmortem → save to GCS
# 8. Ingest postmortem → knowledge base updated
```

### Final Test Run
```bash
# All tests must pass before demo
pytest tests/ -v --tb=short
# Expected: 35+ tests, 0 failures
```

### Acceptance Criteria
- `pytest tests/` exits 0 (no failures).
- `scripts/demo_scenario.py` runs end-to-end in < 60 seconds.
- All 7 Phase 0 bug fixes have regression tests.
- Dashboard launches and shows real data.
- At least one postmortem generated and downloadable.

---

## Implementation Order Summary

```
Phase 0  (Day 1 AM)   — Bug fixes. Foundation must be solid.
Phase 1  (Day 1 PM)   — Semantic RAG. Everything downstream depends on this. ✅ DONE
Phase 2  (Day 2 AM)   — Incident Triage. Core agentic workflow. ✅ DONE
Phase 3  (Day 2 PM)   — RCA + Citations. The "wow" LLM feature. ✅ DONE
Phase 4  (Day 3 AM)   — Approval + Runbooks. The "trust" feature. ✅ DONE
Phase 5  (Day 3 PM)   — Verification. Closes the loop.
Phase 6  (Day 4 AM)   — Postmortem + Learning. Polishes the output.
Phase 7  (Day 4 PM)   — Dashboard. Makes it visual.
Phase 8  (Day 5)      — Jira Write + Audit (if time allows).
Phase 9  (Day 6)      — Tests + Demo scripts. Ship.
```

---

## File Change Map (Complete)

```
MODIFY (10 files):
  opsmind/core/agents/root.py
  opsmind/core/agents/pipeline.py
  opsmind/core/agents/listener.py
  opsmind/core/agents/synthesizer.py
  opsmind/core/agents/writer.py
  opsmind/core/safety/framework.py
  opsmind/context/retrieval.py
  opsmind/tools/knowledge.py
  opsmind/tools/incidents.py
  opsmind/tools/postmortems.py
  opsmind/tools/guardrail.py
  opsmind/data/loader.py
  opsmind/data/manager.py
  requirements.txt
  pyproject.toml
  Makefile

CREATE - Tools (8 new files):
  opsmind/tools/triage.py
  opsmind/tools/rca.py
  opsmind/tools/runbooks.py
  opsmind/tools/approval.py
  opsmind/tools/verification.py
  opsmind/tools/learning.py
  opsmind/tools/jira_write.py      (Phase 8)
  opsmind/tools/audit_tools.py    (Phase 8)

CREATE - Agents (4 new files):
  opsmind/core/agents/triage_agent.py
  opsmind/core/agents/approval_agent.py
  opsmind/core/agents/runbook_agent.py
  opsmind/core/agents/verification_agent.py

CREATE - Retrieval (5 new files):
  opsmind/retrieval/__init__.py
  opsmind/retrieval/embedder.py
  opsmind/retrieval/index.py
  opsmind/retrieval/hybrid.py
  opsmind/retrieval/chunker.py

CREATE - Audit (3 new files):            (Phase 8)
  opsmind/audit/__init__.py
  opsmind/audit/logger.py
  opsmind/audit/decorator.py

CREATE - Dashboard (8 new files):
  dashboard/__init__.py
  dashboard/app.py
  dashboard/data_bridge.py
  dashboard/charts.py
  dashboard/pages/incidents.py
  dashboard/pages/postmortems.py
  dashboard/pages/analytics.py
  dashboard/pages/timeline.py
  dashboard/pages/knowledge.py

CREATE - Data (5 new YAML runbooks):
  opsmind/data/datasets/runbooks/restart_service.yaml
  opsmind/data/datasets/runbooks/scale_deployment.yaml
  opsmind/data/datasets/runbooks/db_failover.yaml
  opsmind/data/datasets/runbooks/flush_cache.yaml
  opsmind/data/datasets/runbooks/rollback_deployment.yaml

CREATE - Tests (10 new files):
  tests/__init__.py
  tests/conftest.py
  tests/fixtures/sample_incident.json
  tests/fixtures/sample_jira_issue.json
  tests/test_loader.py
  tests/test_retrieval.py
  tests/test_triage.py
  tests/test_rca.py
  tests/test_approval.py
  tests/test_verification.py
  tests/test_postmortem.py
  tests/test_learning.py
  tests/test_guardrails.py
  tests/test_dashboard_bridge.py

CREATE - Scripts (3 new files):
  scripts/build_index.py
  scripts/replay_incidents.py
  scripts/demo_scenario.py
  scripts/seed_demo_data.py

PRESERVED (never touch):
  opsmind/agent.py
  opsmind/core/agents/search.py
  opsmind/data/connectors/base.py
  opsmind/data/connectors/jira.py
  opsmind/data/connectors/manager.py
  opsmind/utils/gcp_storage.py
  opsmind/utils/helpers.py
  opsmind/utils/logging.py
  opsmind/config/settings.py
  env.template
  deploy.sh
  DEPLOYMENT.md
```

---

## Key Invariants (Never Break These)

> [!IMPORTANT]
> These contracts must hold after every phase.

1. `opsmind/agent.py` exports `root_agent` — ADK entry point never changes.
2. `adk run opsmind` must launch without error after every phase.
3. `save_postmortem` + `list_postmortem_files` + `check_guardrails_health` signatures unchanged.
4. All existing tool names in `root.py` remain present (new tools are additions, not replacements).
5. `data/loader.py` CSV loading still works with the bundled sample CSVs.
6. GCS and local-fallback storage both work.
7. `deploy.sh` Cloud Run deploy still works.

---

*Roadmap generated from source code inspection. No application files were modified.*

