# Testcase-centric JSON aggregates + reactive UI plan

## Goal

Reshape `evals/llm_bench` so each testcase has one canonical JSON artifact containing:
- prompt
- expected result / assertions
- testcase metadata
- all model runs for that testcase
- scores, errors, timings, provider metadata

Then expose a web UI that renders those JSON artifacts and updates when they change.

## Feasibility

Yes. The current framework already has most primitives:
- YAML-backed testcase registry in `server.py`
- SQLite cache of per-testcase/per-model results in `benchmark_case_results`
- `matrix_results` and `report_summary` payload assembly
- frontend fetching `/api/status`, `/api/testcases`, `/api/providers`

The main change is a **view-model inversion**:
- current primary shape: `matrix_results` = row per testcase/model pair
- target primary shape: `testcase_aggregate.json` = one file per testcase, containing nested `models[]`

## Existing relevant code

- `server.py`
  - `list_testcases()`
  - `benchmark_case_results` table
  - `result_row_to_payload()`
  - `plan_benchmark_matrix()`
  - `record_case_result()`
  - `build_latest_run_payload()`
  - `GET /api/status`
  - `GET /api/testcases`
  - `POST /api/run`
- `site/app.js`
  - already renders `last_run.report_summary`
  - already renders `matrix_results`
  - already reacts to API payloads

## Proposed target data model

### Directory layout

```text
evals/llm_bench/
  testcase_results/
    manifest.json
    sol-flagship__<content_hash>.json
    hacan-flagship-base__<content_hash>.json
```

### One file per testcase

```json
{
  "schema_version": 1,
  "testcase": {
    "id": 1,
    "name": "Sol flagship reference",
    "slug": "sol-flagship-reference",
    "content_hash": "...",
    "source_path": ".../testcases/sol-flagship.yaml",
    "question": "What is the name ...?",
    "prompt_text": "...",
    "assertions": [...],
    "expected_result": {
      "name": "Genesis",
      "cost": "8",
      "combat": "5",
      "move": "1",
      "capacity": "12",
      "sustain_damage": "yes",
      "ability_must_contain": ["place 1 infantry", "status phase", "space area"]
    },
    "created_at": "...",
    "updated_at": "..."
  },
  "summary": {
    "model_count": 35,
    "pass_count": 0,
    "fail_count": 20,
    "error_count": 15,
    "last_updated": "..."
  },
  "models": [
    {
      "model_name": "gemma3:27b",
      "provider_name": "Ollama Cloud",
      "provider_type": "openai-compatible",
      "base_url": "https://ollama.com/v1",
      "execution_trace": "...",
      "result_kind": "fail",
      "label": "Wrong answer",
      "detail": "2 of 9 checks matched.",
      "success": false,
      "score": 22,
      "http_status": 200,
      "response_output": "...",
      "error_text": "",
      "latency_ms": 1234,
      "token_usage": {},
      "result": {...},
      "saved_at": "..."
    }
  ]
}
```

### Manifest file

`manifest.json` should contain lightweight cards for fast listing/filtering:

```json
{
  "schema_version": 1,
  "generated_at": "...",
  "testcases": [
    {
      "name": "Sol flagship reference",
      "slug": "sol-flagship-reference",
      "content_hash": "...",
      "file": "sol-flagship__<content_hash>.json",
      "model_count": 35,
      "pass_count": 0,
      "fail_count": 20,
      "error_count": 15,
      "last_updated": "..."
    }
  ]
}
```

## Why this is a good fit

- Modular testcases: each testcase becomes an independent artifact.
- New models append naturally into the testcase file.
- New testcases do not require schema changes.
- UI can poll one manifest, then fetch testcase files lazily.
- SQLite can remain the execution/cache layer; JSON files become the publishing layer.

## Backend changes

### 1. Add testcase aggregate builders in `server.py`

Add functions like:
- `group_results_by_testcase(results: list[dict]) -> dict[str, list[dict]]`
- `build_testcase_aggregate_payload(testcase: dict, model_results: list[dict]) -> dict`
- `write_testcase_aggregate_files(testcases: list[dict], results: list[dict]) -> dict`
- `build_testcase_manifest(aggregate_payloads: list[dict]) -> dict`

### 2. Write JSON artifacts after every run

After `payload = build_latest_run_payload(...)` in `POST /api/run`:
- build testcase-grouped aggregates from `matrix_results`
- write per-testcase JSON files under `testcase_results/`
- write `manifest.json`

Also do this on cache-only runs so files stay fresh.

### 3. Add read endpoints

New endpoints:
- `GET /api/results/manifest`
- `GET /api/results/testcases/<slug-or-hash>`

Optional:
- `GET /api/results/testcases/<slug-or-hash>/raw`

This avoids making the browser read files directly from disk paths.

### 4. Add change detection metadata

Return:
- `generated_at`
- `etag` or `content_hash`
- `last_updated`

This allows cheap polling and conditional refresh.

## Frontend changes

### 1. New testcase-results page section

Show:
- testcase list from manifest
- counters per testcase
- click into one testcase
- model result table/cards for that testcase
- filters: pass/fail/error, provider, model name

### 2. React to JSON changes

Simplest robust approach:
- poll `/api/results/manifest` every 10-30s
- compare `generated_at` or manifest hash
- if changed, refresh testcase list
- if current testcase changed, re-fetch its JSON and re-render

This is enough. No WebSocket needed initially.

### 3. Progressive loading

- load manifest first
- load testcase JSON on demand
- do not dump all testcase files on initial page load

## Request-error analysis rule improvements

Current issue: request errors are mixed into generic errors. Improve classification:
- `403 subscription_required`
- `429 rate_limited`
- `500 provider_internal_error`
- `transport_timeout`
- `invalid_json`
- `wrong_answer`

This should be normalized in backend so the UI can distinguish:
- inaccessible model
- flaky provider
- bad formatting
- factual failure

## Specific analysis from current batch

From the saved batch:
- total request-errors: 15
- 14x `HTTP 403`
- 1x `HTTP 500`

The 14x `403` bodies explicitly say:
- `this model requires a subscription, upgrade for access`

Conclusion:
- these 14 are **not framework bugs**
- they are **access-tier restrictions on specific Ollama Cloud models**
- they should be classified as `subscription_required`, not as generic request errors

The 1x `500` (`rnj-1:8b`) is likely:
- provider-side transient failure
- should be classified as `provider_internal_error`
- worth one retry policy later, but not required for MVP

## Recommended MVP sequence

1. Keep SQLite as source-of-truth execution cache.
2. Add testcase aggregate JSON writer.
3. Add manifest writer.
4. Add `/api/results/manifest` and `/api/results/testcases/<id>`.
5. Add frontend manifest-driven testcase browser.
6. Add normalized error taxonomy.
7. Add polling refresh.

## Nice-to-have later

- WebSocket/SSE instead of polling
- retry policy for 500/timeout only
- batch history per testcase over time
- compare model answers across multiple runs
- diffing when assertions change

## Verdict

Yes, this is very feasible.

In fact, the current framework is already close:
- execution cache exists
- testcase metadata exists
- frontend API fetch/render exists

What’s missing is mainly:
- testcase-first aggregate JSON publishing
- dedicated results endpoints
- frontend manifest/testcase viewer
- cleaner error classification
