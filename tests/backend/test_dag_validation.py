"""
Tests for DAG validation (Task 9).

Tests validate:
- Cycle detection works
- Time-directional check rejects anachronistic edges
- Valid DAG passes validation
"""

import pytest
from typing import Dict

from src.backend.models.drug import Drug
from src.backend.models.lineage import LineageEdge, EdgeType, Provenance
from src.backend.etl.dag_validator import DAGValidator, ValidationResult


def make_drug(id: str, year_approved: int) -> Drug:
    return Drug(
        id=id,
        name=f"Drug {id}",
        atc_code="C10AA01",
        atc_category="C",
        year_approved=year_approved,
        smiles="CC",
    )


def make_edge(from_id: str, to_id: str, edge_id: str = None) -> LineageEdge:
    edge_id = edge_id or f"{from_id}_{to_id}"
    return LineageEdge(
        edge_id=edge_id,
        from_drug_id=from_id,
        to_drug_id=to_id,
        edge_type=EdgeType.follow_on,
        confidence=0.7,
        score_breakdown={
            "chronology_score": 0.8,
            "mechanism_score": 0.6,
            "scaffold_score": 0.7,
        },
        provenance=Provenance.auto,
    )


class TestDAGValidator:
    """Test cases for DAG validation"""

    def test_valid_dag_passes(self):
        validator = DAGValidator()

        drugs: Dict[str, Drug] = {
            "drug_1990": make_drug("drug_1990", 1990),
            "drug_2000": make_drug("drug_2000", 2000),
            "drug_2010": make_drug("drug_2010", 2010),
        }

        edges = [
            make_edge("drug_1990", "drug_2000"),
            make_edge("drug_2000", "drug_2010"),
        ]

        result = validator.validate(edges, drugs)

        assert result.is_valid is True
        assert result.cycles == []
        assert result.time_violations == []

    def test_detects_simple_cycle(self):
        validator = DAGValidator()

        drugs: Dict[str, Drug] = {
            "drug_A": make_drug("drug_A", 1990),
            "drug_B": make_drug("drug_B", 2000),
        }

        edges = [
            make_edge("drug_A", "drug_B"),
            make_edge("drug_B", "drug_A"),
        ]

        result = validator.validate(edges, drugs)

        assert result.is_valid is False
        assert len(result.cycles) >= 1

    def test_detects_longer_cycle(self):
        validator = DAGValidator()

        drugs: Dict[str, Drug] = {
            "drug_A": make_drug("drug_A", 1990),
            "drug_B": make_drug("drug_B", 2000),
            "drug_C": make_drug("drug_C", 2010),
        }

        edges = [
            make_edge("drug_A", "drug_B"),
            make_edge("drug_B", "drug_C"),
            make_edge("drug_C", "drug_A"),
        ]

        result = validator.validate(edges, drugs)

        assert result.is_valid is False
        assert len(result.cycles) >= 1

    def test_time_directional_rejects_anachronistic_edge(self):
        validator = DAGValidator()

        drugs: Dict[str, Drug] = {
            "parent_2010": make_drug("parent_2010", 2010),
            "child_2000": make_drug("child_2000", 2000),
        }

        edges = [make_edge("parent_2010", "child_2000", "edge_anachronistic")]

        result = validator.validate(edges, drugs)

        assert result.is_valid is False
        assert "edge_anachronistic" in result.time_violations

    def test_time_directional_accepts_same_year(self):
        validator = DAGValidator()

        drugs: Dict[str, Drug] = {
            "parent_2000": make_drug("parent_2000", 2000),
            "child_2000": make_drug("child_2000", 2000),
        }

        edges = [make_edge("parent_2000", "child_2000")]

        result = validator.validate(edges, drugs)

        assert result.time_violations == []

    def test_multi_parent_dag_valid(self):
        validator = DAGValidator()

        drugs: Dict[str, Drug] = {
            "parent_A": make_drug("parent_A", 1990),
            "parent_B": make_drug("parent_B", 1995),
            "child": make_drug("child", 2000),
        }

        edges = [
            make_edge("parent_A", "child"),
            make_edge("parent_B", "child"),
        ]

        result = validator.validate(edges, drugs)

        assert result.is_valid is True
        assert result.cycles == []

    def test_empty_edges_valid(self):
        validator = DAGValidator()
        drugs: Dict[str, Drug] = {}

        result = validator.validate([], drugs)

        assert result.is_valid is True

    def test_missing_drug_data_skipped(self):
        validator = DAGValidator()

        drugs: Dict[str, Drug] = {
            "drug_A": make_drug("drug_A", 2000),
        }

        edges = [make_edge("drug_A", "missing_drug")]

        result = validator.validate(edges, drugs)

        assert result.cycles == []
