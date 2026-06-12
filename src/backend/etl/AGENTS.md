# DrugTree ETL Pipeline

## OVERVIEW
Canonical ETL layer for drug, disease, and ATC enrichment, with async external lookups, lineage builders, and checkpointed batch runs.

## STRUCTURE
- `atc_orchestrator.py`, thin ATC enrichment public API and CLI wrapper.
- `atc_lookup_service.py`, `atc_enrichment_pipeline.py`, `atc_enrichment_models.py`, `atc_enrichment_reports.py`, ATC lookup/enrichment/reporting stages.
- `drug_etl.py`, core canonical drug loader/orchestrator.
- `drug_metadata.py`, `drug_transform_helpers.py`, drug metadata and transformation helpers.
- `disease_etl.py`, core canonical disease loader/orchestrator.
- `disease_etl_helpers.py`, `disease_source_loaders.py`, disease parsing and source-loading helpers.
- `family_builder.py`, `lineage_builder.py`, `reclassify_category_v.py`, derived classification builders.
- `atc_batch_chembl.py`, `atc_batch_kegg.py`, `atc_batch_pubchem.py`, batch source adapters.
- `chembl_client.py`, `pubchem_client.py`, `fda_client.py`, `clinicaltrials_client.py`, async HTTP clients.
- `atc_kegg_api_lookup.py`, `atc_kegg_brite_lookup.py`, `kegg_drug_lookup.py`, KEGG helpers.
- `dag_validator.py`, dependency order checks.
- `override_loader.py`, curated override ingestion.
- `classify_remaining_drugs.py`, residual classification pass.
- `normalize_drugs.py`, `normalize_diseases.py`, `normalize_targets.py`, data normalizers.
- `generate_edges.py`, `generate_xrefs.py`, `load_graph_edges.py`, graph artifact generators.
- `fetch_*.py` (drugcentral, dgidb, drugmechdb, opentargets, ttd, ctd, rxnorm, mondo), source fetchers.
- `analyze_v_category.py`, V-category analysis utility.

## DATA FLOW
- `data/drugs.json` and `data/diseases.json` feed ETL transforms.
- `data/curated/` overrides load before final classification.
- ATC enrichment fans out ChEMBL, KEGG, and PubChem batches with explicit resolution order: preserve → KEGG → PubChem → ChEMBL → WHO → BRITE → fallback.
- Provenance stays attached to every ATC assignment.
- `data/checkpoints/` stores resumable progress snapshots with keys: `processed_ids`, `results`, `stats`, `timestamp`, `status`.

## EXTERNAL SOURCES
- ChEMBL, KEGG, PubChem, FDA, ClinicalTrials.gov.
- All remote calls should use async `httpx`.
- Retry pattern: `for attempt in range(max_retries)` with `2.0 ** attempt` backoff, special 429 handling.
- Wrap every external call in `try/except`, fail soft, keep partial output.
- Preserve source tags on writes, ChEMBL, KEGG, or PubChem.
- The former sync-`requests` ATC/KEGG files (`atc_orchestrator.py`, `drug_etl.py`, `fetch_atc_from_chembl.py`, `fetch_atc_from_kegg.py`, `atc_kegg_api_lookup.py`) have been migrated to `httpx`; do not reintroduce `requests`.
- `run_etl.sh` defaults to `data/processed/compound_master_table.tsv`; set `COMPOUND_MASTER_TABLE` for alternate source tables.
- `run_etl.sh` uses `ETL_CORE_TIMEOUT_SECONDS` for required steps and `ETL_STEP_TIMEOUT_SECONDS` for optional fetch/normalize/artifact/load steps.

## CONVENTIONS
- Treat canonical data as `data/`, not `src/frontend/data/`.
- Keep ETL steps deterministic and checkpoint friendly.
- Follow DAG order before derived builders run.
- Update provenance and override paths together.
- Use `run_etl.sh` strict mode and timeout expectations when adding launcher steps.

## ANTI-PATTERNS
- Do not edit generated frontend mirrors.
- Do not skip provenance on enrichment writes.
- Do not add sync HTTP clients or blocking remote calls.
- Do not break checkpoint resume semantics.
- Do not assume external sources always respond.
