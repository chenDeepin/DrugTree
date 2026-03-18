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
├── routers/drugs.py     # REST endpoints (203 lines)
├── models/drug.py       # Pydantic schemas (102 lines)
└── etl/drug_etl.py      # ETL pipeline (819 lines)
```

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/drugs` | List all drugs |
| GET | `/api/drugs/{id}` | Get drug by ID |
| GET | `/api/drugs/search` | Search drugs |
| GET | `/api/drugs/atc/{cat}` | Filter by ATC |

---

## Anti-Patterns

### ⚠️ Avoid
1. **Sync requests** - Use `async def` with `httpx`
2. **Hardcoded API keys** - Use environment variables
3. **Skipping validation** - Always validate with Pydantic
4. **Unbounded queries** - Add pagination

### ⚠️ Common Mistakes
1. **Missing CORS** - Frontend on different port needs CORS
2. **No error handling** - Wrap external API calls in try/except
3. **Blocking I/O** - Use async for ChEMBL/PubChem calls

---

## Testing

```bash
pytest tests/backend/
pytest tests/backend/test_drug_etl.py -v
```

