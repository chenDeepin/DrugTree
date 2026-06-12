# DrugTree Benchmark Contract

## Scope

This contract defines the local benchmark mode for the DrugTree performance program.
It is the Task 1 source of truth for baseline capture, evidence format, freshness rules,
and the Task 12 escalation gate.

The contract follows the release-gate principle in `docs/operations/release-gates.md`:
stability before expansion, benchmark evidence before optimization claims, and no CI-only
timing claims.

## Benchmark source of truth

- **Primary source of truth**: local benchmark mode on the current execution host.
- **Frontend benchmark mode**: Playwright against the existing static harness from
  `tests/frontend/playwright.config.ts` on `http://localhost:8766`.
- **Backend benchmark mode**: local in-process FastAPI access or same-host backend execution
  against repo-root canonical data.
- **ETL benchmark mode**: deterministic local transforms only; no external network dependency
  is allowed for the benchmark pass/fail path.
- **CI role**: smoke/perf guardrails only. CI timing numbers must never replace local evidence.

## Canonical inputs

Benchmark fixtures and evidence derive from repo-root canonical JSON inputs only:

- `data/drugs.json`
- `data/diseases.json`
- `data/disease_drug_edges.json`
- `data/ontology/body-ontology.json`
- `data/processed/drug_families.json`
- `data/processed/lineage_edges.json`

`src/frontend/data/*` remains generated test/runtime material, never canonical input.

## Deterministic fixture contract

Task 1 fixture generation is handled by `scripts/perf/generate_fixtures.py`.

- Output root: `tests/fixtures/perf/`
- Required artifacts:
  - `tests/fixtures/perf/benchmark-fixtures.json`
  - `tests/fixtures/perf/manifest.json`
- Deterministic ordering rule:
  - sort records by stable identifier when available (`id`, `edge_id`, `family_id`,
    `drug_id`, `disease_id`)
  - otherwise sort by SHA-256 of normalized JSON
- Manifest requirements:
  - canonical source path
  - SHA-256 for each canonical source file
  - record counts for each source
  - SHA-256 for each generated fixture file
  - `manifest.json` may hash a canonical projection with its own hash field blank to avoid a self-referential checksum loop
- Failure behavior:
  - missing canonical input is a hard error
  - fixture generation must leave no partial output directory behind on failure

## Freshness and invalidation policy

- Shell/embed artifacts and request caches may be stale for at most **24 hours**.
- Any canonical source hash change invalidates the fixture set and cached benchmark evidence.
- Task 1 evidence must record the source-hash snapshot that produced the benchmark fixtures.

## Measured benchmark flows

Task 1 establishes baseline evidence for these exact flows:

1. Cold atlas boot to first `.drug-card`
2. ATC/search filter update
3. Route transition to `#drug/{id}`
4. `/api/v1/drugs?limit=50`
5. `/api/v1/graph/neighborhood/drug:atorvastatin?max_hops=1`
6. `/api/v1/graph/evidence/{edge_id}`
7. Deterministic ETL phase: family build + lineage build + frontend embed generation

## Performance budgets

These are fixed at Task 1 and must not be rewritten after optimization work starts.

| Flow | Budget |
| --- | --- |
| Cold atlas boot (`navigation start -> first .drug-card`) | **<= 1800 ms** and **>= 25% faster than the Task 1 baseline** |
| ATC/search/filter interaction | **median <= 120 ms** |
| Route-to-detail (`.drug-card` click -> `#drug-detail-page` visible and URL updated) | **median <= 500 ms** |
| `/api/v1/drugs?limit=50` | **p95 <= 120 ms** |
| `/api/v1/graph/neighborhood/drug:atorvastatin?max_hops=1` | **p95 <= 180 ms** and **payload <= 300 KB** |
| `/api/v1/graph/evidence/{edge_id}` | **p95 <= 80 ms** and **payload <= 20 KB** |
| Deterministic ETL phase | **<= 90 s** and **>= 25% faster than the Task 1 baseline** |
| Network-bound enrichment | **concurrency cap 5**, **cache TTL 24 h**, unresolved/report artifacts emitted on partial failure |

## Evidence contract

Task 1 evidence must be machine-readable JSON under `.sisyphus/evidence/`.

- Aggregate Task 1 evidence: `.sisyphus/evidence/task-1-benchmark-contract.json`
- Frontend per-suite evidence: `.sisyphus/evidence/frontend-perf/*.json`
- Backend per-suite evidence: `.sisyphus/evidence/backend-perf/*.json`
- Local bench summary: `.sisyphus/evidence/final-performance-summary.json` or caller-provided output

Minimum aggregate JSON sections:

- `fixture_manifest`
- `frontend`
- `backend`
- `etl`
- `budget_evaluation`
- `task_12_trigger`

The local benchmark runner must write the aggregate summary JSON even when fixture generation or a benchmark suite fails, so failed runs still leave a machine-readable audit trail.

Each measured metric must record:

- raw sample list or deterministic measurement summary
- median and/or p95 as applicable
- payload bytes when applicable
- budget threshold
- `within_budget`
- benchmark mode metadata (`static_harness`, `same_host_backend`, `network_free`, etc.)

## Escalation rule: Task 12 activation

Task 12 is not permitted to activate early.

Task 12 becomes eligible **only after Tasks 1-11 complete**, and only if **any two** of the
following still fail in local benchmark mode:

- cold boot **> 1800 ms**
- filter interaction **> 120 ms**
- route-to-detail **> 500 ms**
- graph neighborhood p95 **> 180 ms**
- graph neighborhood payload **> 300 KB**
- deterministic ETL phase **> 90 s**

Task 1 tooling must record this rule exactly in machine-readable form even though Task 1 only
captures the baseline and does not itself authorize Task 12.

## Guardrails

- Do not use CI timings as the primary benchmark decision signal.
- Do not require manual stopwatch checks.
- Do not change `/api/v1/*` response shapes to support Task 1 measurement.
- Do not reintroduce `src/frontend/data/*` as canonical input.
- Do not fold unrelated UI redesign or speculative infrastructure migration into benchmark work.

## Local execution commands

```bash
python3 scripts/perf/generate_fixtures.py --output tests/fixtures/perf
npx playwright test tests/frontend/e2e/perf --config tests/frontend/playwright.config.ts --project=chromium
pytest tests/backend/perf -q
python3 scripts/perf/run_local_bench.py --output .sisyphus/evidence/final-performance-summary.json
```

## Acceptance mapping for Task 1

- Fixture generation must succeed from canonical inputs and emit a source-hash manifest.
- Frontend perf tests must run against the existing static harness on port `8766`.
- Backend perf tests must be deterministic and network-free.
- All Task 1 evidence must be machine-readable JSON and merge into the aggregate evidence file.
