import pytest
from pydantic import ValidationError

from src.backend.models.graph import (
    Evidence,
    GraphEdgeRef,
    GraphEdgeType,
    GraphNodeRef,
    GraphNodeType,
    NeighborhoodResult,
    SubgraphResult,
)


def test_graph_node_type_values():
    assert {value.value for value in GraphNodeType} == {
        "drug",
        "disease",
        "target",
        "cluster",
    }


def test_graph_edge_type_values():
    assert {value.value for value in GraphEdgeType} == {
        "lineage",
        "disease_drug",
        "drug_target",
        "family_member",
    }


def test_evidence_validation():
    evidence = Evidence(source="test_source", source_type="database", confidence=0.7)
    assert evidence.source == "test_source"
    assert evidence.source_type == "database"
    assert evidence.confidence == 0.7


def test_evidence_confidence_bounds():
    with pytest.raises(ValidationError):
        _ = Evidence(source="x", confidence=-0.1)

    with pytest.raises(ValidationError):
        _ = Evidence(source="x", confidence=1.1)


def test_evidence_requires_source():
    with pytest.raises(ValidationError):
        _ = Evidence.model_validate({"confidence": 0.9})


def test_graph_models_construction():
    center = GraphNodeRef(
        node_id="drug:atorvastatin",
        node_type=GraphNodeType.drug,
        label="Atorvastatin",
    )
    neighbor = GraphNodeRef(
        node_id="drug:simvastatin",
        node_type=GraphNodeType.drug,
        label="Simvastatin",
    )
    edge = GraphEdgeRef(
        edge_id="simvastatin_to_atorvastatin",
        edge_type=GraphEdgeType.lineage,
        source_id="drug:simvastatin",
        target_id="drug:atorvastatin",
        confidence=0.8,
        evidence=[Evidence(source="auto", source_type="inferred", confidence=0.8)],
    )

    neighborhood = NeighborhoodResult(
        center_node=center,
        edges=[edge],
        neighbor_nodes=[neighbor],
        max_hops_reached=1,
    )
    assert neighborhood.center_node.node_id == "drug:atorvastatin"
    assert len(neighborhood.edges) == 1
    assert len(neighborhood.neighbor_nodes) == 1

    subgraph = SubgraphResult(
        nodes=[center, neighbor],
        edges=[edge],
        total_nodes=2,
        total_edges=1,
    )
    assert subgraph.total_nodes == 2
    assert subgraph.total_edges == 1
