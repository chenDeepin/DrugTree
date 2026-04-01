# DrugTree Tests

## OVERVIEW
Test code only. Backend uses pytest, frontend uses Playwright and Node checks.

## STRUCTURE
- `tests/backend/`, 35 pytest files, shared fixtures in `tests/backend/conftest.py`
- `tests/backend/perf/`, performance coverage for backend paths
- `tests/frontend/e2e/`, Playwright regression and browser flows
- `tests/frontend/e2e/perf/`, frontend perf coverage
- `tests/frontend/e2e/disease-universe.mjs`, Node integration check
- `tests/fixtures/` and `tests/fixtures/perf/`, shared test data
- `tests/frontend/playwright.config.ts`, serves on port `8766` to avoid backend API port `8765`

## TEST CONVENTIONS
- Treat `data/drugs.json`, `data/diseases.json`, `data/disease_drug_edges.json`, and `data/ontology/body-ontology.json` as canonical inputs
- Use `src/frontend/data/` mirrors only when a test is checking generated embeds
- Cover `drug_etl`, `disease_api`, `graph_index`, `atc_orchestrator`, `family_builder`, `change_detector`, `validation_pipeline`
- `test_graph_schema_contract.py` is the largest schema contract suite, keep assertions strict
- Mock external APIs in unit tests, keep network off by default
- ATC assertions must separate valid WHO codes from placeholder `*99XX99` codes
- Disease assertions must check edge-backed filtering, not body-region coincidence
- `tests/frontend/e2e/p0-regression.spec.ts` is the high-signal route, detail, and disease regression file

## COMMANDS
```bash
pytest tests/backend/
pytest tests/backend/test_atc_orchestrator.py tests/backend/test_drug_etl.py tests/backend/test_disease_api.py tests/backend/test_graph_index.py
npx playwright test --config tests/frontend/playwright.config.ts
node tests/frontend/e2e/disease-universe.mjs
```

## ANTI-PATTERNS
- Do not edit generated `src/frontend/data/*` files directly
- Do not let frontend tests collide with backend API ports
- Do not use live external services in unit tests
- Do not infer disease matches from anatomy alone
- Do not treat placeholder ATC codes as valid WHO classifications
