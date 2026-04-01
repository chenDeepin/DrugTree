# DrugTree API Routers

## OVERVIEW
FastAPI router modules for `/api/v1` surface. Each router is a standalone `APIRouter` with its own prefix.

## STRUCTURE
```
routers/
├── __init__.py      # re-exports all routers for main.py include
├── drugs.py         # 534 lines — drug, family, lineage, graph-stats endpoints
├── diseases.py      # 303 lines — disease, edge, target/drug, approvals endpoints
├── targets.py       # 258 lines — drug target lookup endpoints
├── admin.py         # 409 lines — sync, rollback, audit, health, perf endpoints
└── graph.py         # 49 lines  — graph-native query endpoints
```

## WHERE TO LOOK
| Task | File | Prefix |
|------|------|--------|
| Drug CRUD + search | `drugs.py` | `/api/v1/` |
| Drug families | `drugs.py` | `/api/v1/families/` |
| Drug genealogy | `drugs.py` | `/api/v1/lineages/` |
| Disease hierarchy | `diseases.py` | `/api/v1/diseases/` |
| Disease-drug edges | `diseases.py` | `/api/v1/diseases/{id}/drugs` |
| Drug targets | `targets.py` | `/api/v1/targets/` |
| Graph queries | `graph.py` | `/api/v1/graph/` |
| Admin/health | `admin.py` | `/api/v1/admin/` |

## KEY ENDPOINTS
- `GET /api/v1/drugs` — paginated list (filters: `category`, `search`, `phase`)
- `GET /api/v1/drugs/{id}` — single drug detail
- `GET /api/v1/drugs/search?q=` — text search (name, target, class, synonyms)
- `GET /api/v1/lineage/{drug_id}?threshold=` — genealogy tree
- `GET /api/v1/families/{family_id}` — drug family detail
- `GET /api/v1/graph/neighborhood/{node_id}?max_hops=` — N-hop graph
- `GET /api/v1/graph/subgraph?node_ids=` — subgraph extraction
- `GET /api/v1/targets/{drug_id}` — target lookup for a drug
- `GET /api/v1/admin/health/data-quality` — data quality check

## CONVENTIONS
- All routers use `APIRouter(prefix="/api/v1")` (except admin: `/api/v1/admin`, graph: `/api/v1/graph`)
- Use Pydantic response models for type safety
- Add pagination to list endpoints (`skip`/`limit` or `page`/`size`)
- Delegate business logic to `services/` layer — routers are thin

## ANTI-PATTERNS
- No business logic in router functions
- No unbounded list endpoints without pagination
- No direct `data/` file reads from routers — go through services or data_snapshot
- No sync HTTP calls — use `async def` with `httpx`
