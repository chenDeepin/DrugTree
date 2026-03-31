# DrugTree ETL Pipeline

## OVERVIEW
Canonical ETL layer for drug, disease, and ATC enrichment, with async external lookups, lineage builders, and checkpointed batch runs.

## STRUCTURE
- `atc_orchestrator.py`, main ATC enrichment entrypoint.
- `drug_etl.py`, `disease_etl.py`, core canonical loaders.
- `family_builder.py`, `lineage_builder.py`, `reclassify_category_v.py`, derived classification builders.
- `atc_batch_chembl.py`, `atc_batch_kegg.py`, `atc_batch_pubchem.py`, batch source adapters.
- `chembl_client.py`, `pubchem_client.py`, `fda_client.py`, `clinicaltrials_client.py`, async HTTP clients.
- `atc_kegg_brite_lookup.py`, `kegg_drug_lookup.py`, KEGG helpers.
- `dag_validator.py`, dependency order checks.
- `override_loader.py`, curated override ingestion.
- `classify_remaining_drugs.py`, residual classification pass.

## DATA FLOW
- `data/drugs.json` and `data/diseases.json` feed ETL transforms.
- `data/curated/` overrides load before final classification.
- `atc_orchestrator.py` fans out ChEMBL, KEGG, and PubChem batches.
- Provenance stays attached to every ATC assignment.
- `data/checkpoints/` stores resumable progress snapshots.

## EXTERNAL SOURCES
- ChEMBL, KEGG, PubChem, FDA, ClinicalTrials.gov.
- All remote calls use async `httpx`.
- Wrap every external call in `try/except`, fail soft, keep partial output.
- Preserve source tags on writes, ChEMBL, KEGG, or PubChem.

## CONVENTIONS
- Treat canonical data as `data/`, not `src/frontend/data/`.
- Keep ETL steps deterministic and checkpoint friendly.
- Follow DAG order before derived builders run.
- Update provenance and override paths together.
- Use `run_etl.sh` strict mode expectations when adding launcher steps.

## ANTI-PATTERNS
- Do not edit generated frontend mirrors.
- Do not skip provenance on enrichment writes.
- Do not add sync HTTP clients or blocking requests.
- Do not break checkpoint resume semantics.
- Do not assume external sources always respond.
