from fastapi import APIRouter, HTTPException

from ..models.graph import Evidence, GraphNodeRef, NeighborhoodResult, SubgraphResult
from ..services.graph_queries import get_graph_query_service


router = APIRouter(prefix="/api/v1/graph", tags=["graph"])


@router.get("/node/{node_id}", response_model=GraphNodeRef)
async def get_graph_node(node_id: str):
    query_service = get_graph_query_service()
    node = query_service.get_node(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")
    return node


@router.get("/neighborhood/{node_id}", response_model=NeighborhoodResult)
async def get_graph_neighborhood(node_id: str, max_hops: int = 1):
    if max_hops < 1 or max_hops > 5:
        raise HTTPException(status_code=400, detail="max_hops must be between 1 and 5")
    query_service = get_graph_query_service()
    result = query_service.get_neighborhood(node_id=node_id, max_hops=max_hops)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")
    return result


@router.get("/evidence/{edge_id}", response_model=list[Evidence])
async def get_graph_evidence(edge_id: str):
    query_service = get_graph_query_service()
    evidence = query_service.get_evidence(edge_id=edge_id)
    if not evidence:
        raise HTTPException(status_code=404, detail=f"Edge '{edge_id}' not found")
    return evidence


@router.get("/subgraph", response_model=SubgraphResult)
async def get_graph_subgraph(node_ids: str):
    query_service = get_graph_query_service()
    parsed_node_ids = [
        node_id.strip() for node_id in node_ids.split(",") if node_id.strip()
    ]
    if not parsed_node_ids:
        raise HTTPException(
            status_code=400, detail="node_ids must include at least one node"
        )
    return query_service.get_subgraph(parsed_node_ids)
