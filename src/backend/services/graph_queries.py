from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, TypeVar, cast

from ..models.graph import (
    Evidence,
    GraphEdgeRef,
    GraphEdgeType,
    GraphNodeRef,
    GraphNodeType,
    NeighborhoodResult,
    SubgraphResult,
)
from ..services.data_snapshot import DataSnapshotService, get_data_snapshot_service
from ..services.graph_index import GraphIndex, get_graph_index


CachedValue = TypeVar("CachedValue")


class GraphQueryService:
    MAX_NEIGHBOR_NODES = 96
    MAX_NEIGHBOR_EDGES = 192
    MAX_SUBGRAPH_NODES = 128
    MAX_SUBGRAPH_EDGES = 256
    CACHE_TTL = timedelta(hours=24)

    def __init__(
        self,
        graph_index: Optional[GraphIndex] = None,
        snapshot_service: Optional[DataSnapshotService] = None,
    ):
        self.graph_index = graph_index or get_graph_index()
        self.snapshot_service = snapshot_service or get_data_snapshot_service()
        self._cache: dict[str, tuple[str, datetime, object]] = {}
        self._cache_hits = {"evidence": 0, "neighborhood": 0, "subgraph": 0}
        self._cache_misses = {"evidence": 0, "neighborhood": 0, "subgraph": 0}

    def _cache_key(self, prefix: str, value: str) -> str:
        return f"{prefix}:{value}"

    def _cache_bucket(self, key: str) -> str:
        return key.split(":", 1)[0]

    def _cache_get(
        self, key: str, default: Optional[CachedValue] = None
    ) -> Optional[CachedValue]:
        cached = self._cache.get(key)
        if cached is None:
            bucket = self._cache_bucket(key)
            if bucket in self._cache_misses:
                self._cache_misses[bucket] += 1
            return default
        source_hash, created_at, value = cached
        snapshot = self.snapshot_service.get_snapshot()
        if snapshot.source_hash != source_hash:
            self._cache.pop(key, None)
            bucket = self._cache_bucket(key)
            if bucket in self._cache_misses:
                self._cache_misses[bucket] += 1
            return default
        if datetime.now(timezone.utc) - created_at > self.CACHE_TTL:
            self._cache.pop(key, None)
            bucket = self._cache_bucket(key)
            if bucket in self._cache_misses:
                self._cache_misses[bucket] += 1
            return default
        bucket = self._cache_bucket(key)
        if bucket in self._cache_hits:
            self._cache_hits[bucket] += 1
        return cast(CachedValue, value)

    def _cache_set(self, key: str, value: CachedValue) -> CachedValue:
        snapshot = self.snapshot_service.get_snapshot()
        self._cache[key] = (snapshot.source_hash, datetime.now(timezone.utc), value)
        return value

    def get_cache_stats(self) -> dict[str, dict[str, int]]:
        return {
            bucket: {
                "hits": self._cache_hits.get(bucket, 0),
                "misses": self._cache_misses.get(bucket, 0),
            }
            for bucket in sorted(set(self._cache_hits) | set(self._cache_misses))
        }

    def _parse_node_id(self, node_id: str) -> Optional[Tuple[str, str]]:
        if ":" not in node_id:
            return None
        node_type, raw_id = node_id.split(":", 1)
        if not node_type or not raw_id:
            return None
        return node_type, raw_id

    def _load_diseases_by_id(self) -> dict[str, dict[str, object]]:
        diseases = self.snapshot_service.get_snapshot().diseases
        return {str(d.get("id")): d for d in diseases if d.get("id")}

    def _load_disease_drug_edges(self) -> list[dict[str, object]]:
        return self.snapshot_service.get_snapshot().disease_drug_edges

    def _resolve_drug_node(self, drug_id: str) -> Optional[GraphNodeRef]:
        self.graph_index.get_node(drug_id)
        node = self.graph_index._nodes.get(drug_id)
        if node is None:
            return None
        return GraphNodeRef(
            node_id=f"drug:{drug_id}",
            node_type=GraphNodeType.drug,
            label=node.name,
            extra={
                "drug_id": node.drug_id,
                "families": list(node.families),
            },
        )

    def _resolve_disease_node(self, disease_id: str) -> Optional[GraphNodeRef]:
        disease = self._load_diseases_by_id().get(disease_id)
        if disease is None:
            return None

        label = disease.get("name") or disease.get("canonical_name") or disease_id
        return GraphNodeRef(
            node_id=f"disease:{disease_id}",
            node_type=GraphNodeType.disease,
            label=str(label),
            extra={
                "body_region": disease.get("body_region"),
                "categories": disease.get("categories", []),
            },
        )

    def _resolve_cluster_node(self, cluster_id: str) -> Optional[GraphNodeRef]:
        self.graph_index.get_all_families()
        family = self.graph_index._families.get(cluster_id)
        if family is None:
            return None

        return GraphNodeRef(
            node_id=f"cluster:{cluster_id}",
            node_type=GraphNodeType.cluster,
            label=family.label,
            extra={
                "family_basis": family.family_basis.value,
                "member_drug_ids": list(family.member_drug_ids),
            },
        )

    def _resolve_target_node(self, target_id: str) -> GraphNodeRef:
        return GraphNodeRef(
            node_id=f"target:{target_id}",
            node_type=GraphNodeType.target,
            label=target_id,
            extra={},
        )

    def get_node(self, node_id: str) -> Optional[GraphNodeRef]:
        parsed = self._parse_node_id(node_id)
        if parsed is None:
            return None
        node_type, raw_id = parsed

        if node_type == GraphNodeType.drug.value:
            return self._resolve_drug_node(raw_id)
        if node_type == GraphNodeType.disease.value:
            return self._resolve_disease_node(raw_id)
        if node_type == GraphNodeType.cluster.value:
            return self._resolve_cluster_node(raw_id)
        if node_type == GraphNodeType.target.value:
            return self._resolve_target_node(raw_id)

        return None

    def _lineage_evidence(self, edge_id: str) -> list[Evidence]:
        self.graph_index.get_all_edges()
        edge = self.graph_index._edges.get(edge_id)
        if edge is None:
            return []

        source_type = (
            "curated" if edge.provenance.value in {"curated", "manual"} else "inferred"
        )
        evidence = [
            Evidence(
                source=edge.provenance.value,
                source_type=source_type,
                confidence=edge.confidence,
                description=edge.explanation,
            )
        ]

        if edge.score_breakdown:
            score_text = ", ".join(f"{k}={v}" for k, v in edge.score_breakdown.items())
            evidence.append(
                Evidence(
                    source="lineage_score_breakdown",
                    source_type="inferred",
                    confidence=edge.confidence,
                    description=score_text,
                )
            )

        return evidence

    def _lineage_edge_ref(self, edge_id: str):
        edge = self.graph_index._edges.get(edge_id)
        if edge is None:
            return None

        evidence = self._lineage_evidence(edge.edge_id)
        return GraphEdgeRef(
            edge_id=edge.edge_id,
            edge_type=GraphEdgeType.lineage,
            source_id=f"drug:{edge.from_drug_id}",
            target_id=f"drug:{edge.to_drug_id}",
            confidence=edge.confidence,
            evidence=[],
            extra={
                "edge_type": edge.edge_type.value,
                "evidence_available": bool(evidence),
                "evidence_count": len(evidence),
            },
        )

    def _disease_edge_id(self, edge: dict[str, object]) -> str:
        return f"disease:{edge.get('disease_id')}_drug:{edge.get('drug_id')}"

    def _disease_edge_evidence(self, edge: dict[str, object]) -> list[Evidence]:
        level = str(edge.get("evidence_level") or "inferred")
        source_type = "curated" if level in {"approved", "curated"} else "database"
        return [
            Evidence(
                source=str(edge.get("evidence_source") or "disease_drug_edges"),
                source_type=source_type,
                confidence=1.0,
                description=f"{edge.get('indication_type', 'associated')} indication",
            )
        ]

    def _disease_edge_ref(self, edge: dict[str, object]):
        evidence = self._disease_edge_evidence(edge)
        disease_id = edge.get("disease_id")
        drug_id = edge.get("drug_id")
        return GraphEdgeRef(
            edge_id=self._disease_edge_id(edge),
            edge_type=GraphEdgeType.disease_drug,
            source_id=f"disease:{disease_id}",
            target_id=f"drug:{drug_id}",
            confidence=1.0,
            evidence=[],
            extra={
                "indication_type": edge.get("indication_type"),
                "evidence_level": edge.get("evidence_level"),
                "evidence_available": bool(evidence),
                "evidence_count": len(evidence),
            },
        )

    def _sort_node_refs(self, nodes: list[GraphNodeRef]) -> list[GraphNodeRef]:
        return sorted(nodes, key=lambda node: (node.node_type.value, node.node_id))

    def _sort_edge_refs(self, edges: list[GraphEdgeRef]) -> list[GraphEdgeRef]:
        return sorted(edges, key=lambda edge: (edge.edge_type.value, edge.edge_id))

    def _with_truncation_extra(
        self,
        node: GraphNodeRef,
        *,
        omitted_neighbor_nodes: int = 0,
        omitted_edges: int = 0,
    ) -> GraphNodeRef:
        extra = dict(node.extra or {})
        if omitted_neighbor_nodes or omitted_edges:
            extra["truncation"] = {
                "omitted_neighbor_nodes": omitted_neighbor_nodes,
                "omitted_edges": omitted_edges,
            }
        return GraphNodeRef(
            node_id=node.node_id,
            node_type=node.node_type,
            label=node.label,
            extra=extra,
        )

    def get_evidence(self, edge_id: str) -> list[Evidence]:
        cache_key = self._cache_key("evidence", edge_id)
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cast(list[Evidence], cached)

        lineage_evidence = self._lineage_evidence(edge_id)
        if lineage_evidence:
            return self._cache_set(cache_key, lineage_evidence)

        for edge in self._load_disease_drug_edges():
            if self._disease_edge_id(edge) == edge_id:
                return self._cache_set(cache_key, self._disease_edge_evidence(edge))
        return []

    def get_neighborhood(
        self, node_id: str, max_hops: int = 1
    ) -> Optional[NeighborhoodResult]:
        cache_key = self._cache_key("neighborhood", f"{node_id}:{max_hops}")
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cast(NeighborhoodResult, cached)

        center = self.get_node(node_id)
        if center is None:
            return None

        if center.node_type != GraphNodeType.drug:
            return self._cache_set(
                cache_key,
                NeighborhoodResult(
                    center_node=center,
                    edges=[],
                    neighbor_nodes=[],
                    max_hops_reached=0,
                ),
            )

        center_drug_id = node_id.split(":", 1)[1]
        neighborhood = self.graph_index.get_neighborhood(
            center_drug_id, max_hops=max_hops
        )
        if not neighborhood:
            return self._cache_set(
                cache_key,
                NeighborhoodResult(
                    center_node=center,
                    edges=[],
                    neighbor_nodes=[],
                    max_hops_reached=0,
                ),
            )

        drug_ids: set[str] = set(neighborhood.keys())
        for neighbors in neighborhood.values():
            drug_ids.update(neighbors)

        edge_refs: list[GraphEdgeRef] = []
        for edge in self.graph_index.get_all_edges():
            if edge.from_drug_id in drug_ids and edge.to_drug_id in drug_ids:
                edge_ref = self._lineage_edge_ref(edge.edge_id)
                if edge_ref is not None:
                    edge_refs.append(edge_ref)

        disease_nodes: dict[str, GraphNodeRef] = {}
        for edge in self._load_disease_drug_edges():
            drug_id = edge.get("drug_id")
            disease_id = edge.get("disease_id")
            if drug_id in drug_ids and disease_id:
                disease_node = self._resolve_disease_node(str(disease_id))
                if disease_node is not None:
                    disease_nodes[disease_node.node_id] = disease_node
                    edge_refs.append(self._disease_edge_ref(edge))

        neighbor_nodes: list[GraphNodeRef] = []
        for drug_id in sorted(drug_ids):
            if drug_id == center_drug_id:
                continue
            node_ref = self._resolve_drug_node(drug_id)
            if node_ref is not None:
                neighbor_nodes.append(node_ref)
        neighbor_nodes.extend(disease_nodes.values())

        sorted_neighbors = self._sort_node_refs(neighbor_nodes)
        kept_neighbors = sorted_neighbors[: self.MAX_NEIGHBOR_NODES]
        kept_node_ids = {center.node_id, *(node.node_id for node in kept_neighbors)}

        bounded_edges = [
            edge
            for edge in self._sort_edge_refs(edge_refs)
            if edge.source_id in kept_node_ids and edge.target_id in kept_node_ids
        ]
        kept_edges = bounded_edges[: self.MAX_NEIGHBOR_EDGES]

        center = self._with_truncation_extra(
            center,
            omitted_neighbor_nodes=max(0, len(sorted_neighbors) - len(kept_neighbors)),
            omitted_edges=max(0, len(bounded_edges) - len(kept_edges)),
        )

        return self._cache_set(
            cache_key,
            NeighborhoodResult(
                center_node=center,
                edges=kept_edges,
                neighbor_nodes=kept_neighbors,
                max_hops_reached=max_hops,
            ),
        )

    def get_subgraph(self, node_ids: list[str]) -> SubgraphResult:
        ordered_node_ids = ",".join(sorted(node_ids))
        cache_key = self._cache_key("subgraph", ordered_node_ids)
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cast(SubgraphResult, cached)

        resolved_nodes: dict[str, GraphNodeRef] = {}
        for node_id in node_ids:
            node = self.get_node(node_id)
            if node is not None:
                resolved_nodes[node.node_id] = node

        drug_ids = [
            node_id.split(":", 1)[1]
            for node_id in resolved_nodes
            if node_id.startswith("drug:")
        ]
        disease_ids = {
            node_id.split(":", 1)[1]
            for node_id in resolved_nodes
            if node_id.startswith("disease:")
        }

        edge_refs: list[GraphEdgeRef] = []

        for edge in self.graph_index.get_all_edges():
            if edge.from_drug_id in drug_ids and edge.to_drug_id in drug_ids:
                edge_ref = self._lineage_edge_ref(edge.edge_id)
                if edge_ref is not None:
                    edge_refs.append(edge_ref)

        for edge in self._load_disease_drug_edges():
            disease_id = str(edge.get("disease_id"))
            drug_id = str(edge.get("drug_id"))
            if disease_id in disease_ids and drug_id in drug_ids:
                edge_refs.append(self._disease_edge_ref(edge))

        all_nodes = self._sort_node_refs(list(resolved_nodes.values()))
        nodes = all_nodes[: self.MAX_SUBGRAPH_NODES]
        kept_node_ids = {node.node_id for node in nodes}
        bounded_edges = [
            edge
            for edge in self._sort_edge_refs(edge_refs)
            if edge.source_id in kept_node_ids and edge.target_id in kept_node_ids
        ]
        edges = bounded_edges[: self.MAX_SUBGRAPH_EDGES]
        truncation = {}
        if len(all_nodes) > len(nodes):
            truncation["omitted_nodes"] = len(all_nodes) - len(nodes)
        if len(bounded_edges) > len(edges):
            truncation["omitted_edges"] = len(bounded_edges) - len(edges)
        return self._cache_set(
            cache_key,
            SubgraphResult(
                nodes=nodes,
                edges=edges,
                total_nodes=len(nodes),
                total_edges=len(edges),
                truncation=truncation,
            ),
        )


_graph_query_service: Optional[GraphQueryService] = None


def get_graph_query_service() -> GraphQueryService:
    global _graph_query_service
    if _graph_query_service is None:
        _graph_query_service = GraphQueryService()
    return _graph_query_service
