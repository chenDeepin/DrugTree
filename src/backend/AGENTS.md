# DrugTree Backend - FastAPI Service

## Overview

FastAPI backend for DrugTree drug discovery platform. Provides REST API for drug data, search, and ETL pipelines.

---

## Quick Start

```bash
cd src/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

---

## Structure

```
backend/
├── main.py              # FastAPI entry (89 lines)
├── requirements.txt     # Python deps
├── routers/
│   └── drugs.py         # REST endpoints (203 lines)
├── models/
│   └── drug.py          # Pydantic models (102 lines)
└── etl/
    └── drug_etl.py      # ETL pipeline (819 lines)
```

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/drugs` | List all drugs |
| GET | `/api/drugs/{drug_id}` | Get drug by ID |
| GET | `/api/drugs/search` | Search drugs |
| GET | `/api/drugs/atc/{category}` | Filter by ATC |
| GET | `/health` | Health check |

---

## Models

### Drug Schema (`models/drug.py`)
```python
class Drug(BaseModel):
    id: str
    name: str
    smiles: str
    inchikey: str
    atc_code: str
    atc_category: str
    molecular_weight: float
    phase: str
    year_approved: int
    generation: int
    indication: str
    targets: List[str]
    company: str
    synonyms: List[str]
    class_: str  # 'class' is reserved
```

---

## ETL Pipeline

### drug_etl.py (819 lines)
Main data pipeline with:

**Data Sources**:
- ChEMBL API (bioactivity data)
- PubChem (SMILES, properties)
- KEGG (pathway/target info)
- Local JSON (drugs-full.json)

**Key Functions**:
- `fetch_chembl_drugs()` - Pull from ChEMBL
- `enrich_pubchem()` - Add SMILES/molecular weight
- `map_atc_categories()` - Assign ATC codes
- `build_genealogy()` - Compute drug lineage
- `run_full_etl()` - Execute complete pipeline

**KEGG Integration**:
```python
# Fetch pathway/target data
def fetch_kegg_pathways(drug_name: str) -> List[str]:
    # Query KEGG API for drug-target-pathway
```

---

## Anti-Patterns

### ⚠️ Avoid
1. **Sync requests in endpoints** - Use `async def` with `httpx`
2. **Hardcoded API keys** - Use environment variables
3. **Skipping validation** - Always validate with Pydantic
4. **Unbounded queries** - Add pagination to list endpoints

### ⚠️ Common Mistakes
1. **Missing CORS** - Frontend on different port needs CORS
2. **No error handling** - Wrap external API calls in try/except
3. **Blocking I/O** - Use async for ChEMBL/PubChem calls

---

## Testing

```bash
# Run tests
pytest tests/backend/

# Test specific file
pytest tests/backend/test_drug_etl.py -v
```

---

## Dependencies

```
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
pydantic>=2.0.0
httpx>=0.25.0
rdkit>=2023.9
```

---

## Related Files

- [Root AGENTS.md](../../AGENTS.md) - Project overview
- [Frontend AGENTS.md](../frontend/AGENTS.md) - UI layer
- [drugs-full.json](../frontend/data/drugs-full.json) - 61 drugs dataset
