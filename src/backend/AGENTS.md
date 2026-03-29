# DrugTree Backend - FastAPI Service

## Overview

FastAPI backend for DrugTree. Runtime data should come from the canonical repo-root `data/` directory, not frontend-local JSON files.

---

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r src/backend/requirements.txt
uvicorn src.backend.main:app --reload --port 8000
```

---

## Structure

```
backend/
├── main.py              # FastAPI entry
├── routers/
│   ├── drugs.py         # Drug/family/lineage endpoints
│   ├── diseases.py      # Disease endpoints
│   ├── admin.py         # Admin endpoints
│   └── graph.py         # Graph-native endpoints
├── models/
│   ├── drug.py          # Drug Pydantic schemas
│   ├── graph.py         # Unified graph types (GraphNodeType, Evidence, GraphNodeRef, etc.)
│   ├── nodes.py         # Graph node models (DiseaseNode, TargetNode, ClusterNode)
│   ├── lineage.py       # Lineage edge model
│   └── ...
├── services/
│   ├── graph_index.py   # In-memory graph index with adjacency
│   └── graph_queries.py # Graph query service (neighborhood, evidence, subgraph)
└── etl/                 # drug / disease / ATC pipelines
```

## Canonical Inputs

- `data/drugs.json`
- `data/diseases.json`
- `data/disease_drug_edges.json`
- `data/ontology/body-ontology.json`

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/drugs` | List all drugs |
| GET | `/api/v1/drugs/{id}` | Get drug by ID |
| GET | `/api/v1/drugs/search` | Search drugs (`?q=query`) |
| GET | `/api/v1/drugs/category/{cat}` | Filter by ATC |
| GET | `/api/v1/families` | List all drug families |
| GET | `/api/v1/families/{family_id}` | Get family by ID |
| GET | `/api/v1/lineages` | List all lineage edges |
| GET | `/api/v1/lineage/{drug_id}` | Get genealogy tree for a drug |
| GET | `/api/v1/regions` | List body regions |
| GET | `/api/v1/tree/disease/{disease_id}` | Get disease tree with drugs |
| GET | `/api/v1/graph/stats` | Graph index statistics |
| GET | `/api/v1/graph/node/{node_id}` | Get graph node by namespaced ID |
| GET | `/api/v1/graph/neighborhood/{node_id}` | N-hop neighborhood (`?max_hops=1-5`) |
| GET | `/api/v1/graph/evidence/{edge_id}` | Evidence for a graph edge |
| GET | `/api/v1/graph/subgraph` | Subgraph extraction (`?node_ids=a,b,c`) |
| GET | `/api/v1/admin/health/data-quality` | Data quality health check |

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
