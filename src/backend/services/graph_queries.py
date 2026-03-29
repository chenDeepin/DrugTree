import json
from pathlib import Path
from typing import Optional, Tuple

from ..models.graph import (
    Evidence,
    GraphEdgeRef,
    GraphEdgeType,
    GraphNodeRef,
    GraphNodeType,
    NeighborhoodResult,
    SubgraphResult,
)
from ..services.graph_index import GraphIndex, get_graph_index


class GraphQueryService:
    def __init__(
        self,
        graph_index: Optional[GraphIndex] = None,
        data_dir: Optional[Path] = None,
    ):
        self.graph_index = graph_index or get_graph_index()
        self.data_dir = data_dir or Path(__file__).resolve().parents[3] / "data"
        self._diseases_by_id: Optional[dict[str, dict[str, object]]] = None
        self._disease_drug_edges: Optional[list[dict[str, object]]] = None

    def _parse_node_id(self, node_id: str) -> Optional[Tuple[str, str]]:
        if ":" not in node_id:
            return None
        node_type, raw_id = node_id.split(":", 1)
        if not node_type or not raw_id:
            return None
        return node_type, raw_id

    def _load_diseases_by_id(self) -> dict[str, dict[str, object]]:
        if self._diseases_by_id is not None:
            return self._diseases_by_id

        path = self.data_dir / "diseases.json"
        if not path.exists():
            self._diseases_by_id = {}
            return self._diseases_by_id

        with open(path, "r") as f:
            payload = json.load(f)
        diseases = payload.get("diseases", []) if isinstance(payload, dict) else []
        self._diseases_by_id = {str(d.get("id")): d for d in diseases if d.get("id")}
        return self._diseases_by_id

    def _load_disease_drug_edges(self) -> list[dict[str, object]]:
        if self._disease_drug_edges is not None:
            return self._disease_drug_edges

        path = self.data_dir / "disease_drug_edges.json"
        if not path.exists():
            self._disease_drug_edges = []
            return self._disease_drug_edges

        with open(path, "r") as f:
            payload = json.load(f)
        self._disease_drug_edges = (
            payload.get("edges", []) if isinstance(payload, dict) else []
        )
        return self._disease_drug_edges

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

    def get_evidence(self, edge_id: str) -> list[Evidence]:
        lineage_evidence = self._lineage_evidence(edge_id)
        if lineage_evidence:
            return lineage_evidence

        for edge in self._load_disease_drug_edges():
            if self._disease_edge_id(edge) == edge_id:
                return self._disease_edge_evidence(edge)
        return []

    def get_neighborhood(
        self, node_id: str, max_hops: int = 1
    ) -> Optional[NeighborhoodResult]:
        center = self.get_node(node_id)
        if center is None:
            return None

        if center.node_type != GraphNodeType.drug:
            return NeighborhoodResult(
                center_node=center,
                edges=[],
                neighbor_nodes=[],
                max_hops_reached=0,
            )

        center_drug_id = node_id.split(":", 1)[1]
        neighborhood = self.graph_index.get_neighborhood(
            center_drug_id, max_hops=max_hops
        )
        if not neighborhood:
            return NeighborhoodResult(
                center_node=center,
                edges=[],
                neighbor_nodes=[],
                max_hops_reached=0,
            )

        drug_ids: set[str] = set(neighborhood.keys())
        for neighbors in neighborhood.values():
            drug_ids.update(neighbors)

        edge_refs: list[GraphEdgeRef] = []
        for edge in self.graph_index.get_all_edges():
            if edge.from_drug_id in drug_ids and edge.to_drug_id in drug_ids:
                edge_refs.append(
                    GraphEdgeRef(
                        edge_id=edge.edge_id,
                        edge_type=GraphEdgeType.lineage,
                        source_id=f"drug:{edge.from_drug_id}",
                        target_id=f"drug:{edge.to_drug_id}",
                        confidence=edge.confidence,
                        evidence=self._lineage_evidence(edge.edge_id),
                        extra={"edge_type": edge.edge_type.value},
                    )
                )

        disease_nodes: dict[str, GraphNodeRef] = {}
        for edge in self._load_disease_drug_edges():
            drug_id = edge.get("drug_id")
            disease_id = edge.get("disease_id")
            if drug_id in drug_ids and disease_id:
                disease_node = self._resolve_disease_node(str(disease_id))
                if disease_node is not None:
                    disease_nodes[disease_node.node_id] = disease_node
                    edge_refs.append(
                        GraphEdgeRef(
                            edge_id=self._disease_edge_id(edge),
                            edge_type=GraphEdgeType.disease_drug,
                            source_id=f"disease:{disease_id}",
                            target_id=f"drug:{drug_id}",
                            confidence=1.0,
                            evidence=self._disease_edge_evidence(edge),
                            extra={
                                "indication_type": edge.get("indication_type"),
                                "evidence_level": edge.get("evidence_level"),
                            },
                        )
                    )

        neighbor_nodes: list[GraphNodeRef] = []
        for drug_id in sorted(drug_ids):
            if drug_id == center_drug_id:
                continue
            node_ref = self._resolve_drug_node(drug_id)
            if node_ref is not None:
                neighbor_nodes.append(node_ref)
        neighbor_nodes.extend(disease_nodes.values())

        return NeighborhoodResult(
            center_node=center,
            edges=edge_refs,
            neighbor_nodes=neighbor_nodes,
            max_hops_reached=max_hops,
        )

    def get_subgraph(self, node_ids: list[str]) -> SubgraphResult:
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
                edge_refs.append(
                    GraphEdgeRef(
                        edge_id=edge.edge_id,
                        edge_type=GraphEdgeType.lineage,
                        source_id=f"drug:{edge.from_drug_id}",
                        target_id=f"drug:{edge.to_drug_id}",
                        confidence=edge.confidence,
                        evidence=self._lineage_evidence(edge.edge_id),
                        extra={"edge_type": edge.edge_type.value},
                    )
                )

        for edge in self._load_disease_drug_edges():
            disease_id = str(edge.get("disease_id"))
            drug_id = str(edge.get("drug_id"))
            if disease_id in disease_ids and drug_id in drug_ids:
                edge_refs.append(
                    GraphEdgeRef(
                        edge_id=self._disease_edge_id(edge),
                        edge_type=GraphEdgeType.disease_drug,
                        source_id=f"disease:{disease_id}",
                        target_id=f"drug:{drug_id}",
                        confidence=1.0,
                        evidence=self._disease_edge_evidence(edge),
                        extra={
                            "indication_type": edge.get("indication_type"),
                            "evidence_level": edge.get("evidence_level"),
                        },
                    )
                )

        nodes = list(resolved_nodes.values())
        return SubgraphResult(
            nodes=nodes,
            edges=edge_refs,
            total_nodes=len(nodes),
            total_edges=len(edge_refs),
        )


_graph_query_service: Optional[GraphQueryService] = None


def get_graph_query_service() -> GraphQueryService:
    global _graph_query_service
    if _graph_query_service is None:
        _graph_query_service = GraphQueryService()
    return _graph_query_service
