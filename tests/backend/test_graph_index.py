import pytest
from pathlib import Path
from unittest.mock import Mock, patch
import json
import tempfile
import os

import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from backend.services.graph_index import GraphIndex, DrugNode, get_graph_index
from backend.models.drug_family import DrugFamily
from backend.models.lineage import LineageEdge, EdgeType, Provenance


@pytest.fixture
def temp_data_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        families_data = {
            "families": [
                {
                    "family_id": "statins",
                    "label": "Statin Family",
                    "family_basis": "mechanism",
                    "prototype_drug_id": "lovastatin",
                    "member_drug_ids": ["atorvastatin", "simvastatin", "lovastatin"],
                    "generation_range": [1, 2, 3],
                },
                {
                    "family_id": "ace_inhibitors",
                    "label": "ACE Inhibitors",
                    "family_basis": "mechanism",
                    "prototype_drug_id": "captopril",
                    "member_drug_ids": ["lisinopril", "enalapril", "captopril"],
                    "generation_range": [1, 2, 3],
                },
            ]
        }

        edges_data = {
            "edges": [
                {
                    "edge_id": "atorvastatin_to_lovastatin",
                    "from_drug_id": "lovastatin",
                    "to_drug_id": "atorvastatin",
                    "edge_type": "generation_successor",
                    "confidence": 0.87,
                    "generation_rationale": ["sequential_generation", "same_target"],
                    "score_breakdown": {
                        "chronology_score": 0.8,
                        "mechanism_score": 0.95,
                        "scaffold_score": 0.85,
                    },
                    "provenance": "auto",
                },
                {
                    "edge_id": "simvastatin_to_lovastatin",
                    "from_drug_id": "lovastatin",
                    "to_drug_id": "simvastatin",
                    "edge_type": "generation_successor",
                    "confidence": 0.82,
                    "generation_rationale": ["sequential_generation", "same_target"],
                    "score_breakdown": {
                        "chronology_score": 0.75,
                        "mechanism_score": 0.90,
                        "scaffold_score": 0.80,
                    },
                    "provenance": "auto",
                },
            ]
        }

        drugs_data = [
            {"id": "atorvastatin", "name": "Atorvastatin"},
            {"id": "simvastatin", "name": "Simvastatin"},
            {"id": "lovastatin", "name": "Lovastatin"},
            {"id": "lisinopril", "name": "Lisinopril"},
            {"id": "enalapril", "name": "Enalapril"},
            {"id": "captopril", "name": "Captopril"},
        ]

        families_file = tmpdir_path / "drug_families.json"
        edges_file = tmpdir_path / "lineage_edges.json"
        drugs_file = tmpdir_path / "drugs-full.json"

        with open(families_file, "w") as f:
            json.dump(families_data, f)
        with open(edges_file, "w") as f:
            json.dump(edges_data, f)
        with open(drugs_file, "w") as f:
            json.dump(drugs_data, f)

        yield {
            "families_path": families_file,
            "edges_path": edges_file,
            "drugs_path": drugs_file,
        }


class TestGraphIndex:
    def test_init_with_custom_paths(self, temp_data_files):
        index = GraphIndex(
            families_path=temp_data_files["families_path"],
            edges_path=temp_data_files["edges_path"],
            drugs_path=temp_data_files["drugs_path"],
        )
        assert index._loaded is False

    def test_load_creates_nodes(self, temp_data_files):
        index = GraphIndex(
            families_path=temp_data_files["families_path"],
            edges_path=temp_data_files["edges_path"],
            drugs_path=temp_data_files["drugs_path"],
        )
        index.load()

        assert index._loaded is True
        assert len(index._nodes) > 0

    def test_get_node_returns_drug_node(self, temp_data_files):
        index = GraphIndex(
            families_path=temp_data_files["families_path"],
            edges_path=temp_data_files["edges_path"],
            drugs_path=temp_data_files["drugs_path"],
        )

        node = index.get_node("atorvastatin")

        assert node is not None
        assert node.drug_id == "atorvastatin"
        assert node.name == "Atorvastatin"

    def test_get_node_returns_none_for_unknown(self, temp_data_files):
        index = GraphIndex(
            families_path=temp_data_files["families_path"],
            edges_path=temp_data_files["edges_path"],
            drugs_path=temp_data_files["drugs_path"],
        )

        node = index.get_node("unknown_drug")

        assert node is None

    def test_get_edges_returns_drug_edges(self, temp_data_files):
        index = GraphIndex(
            families_path=temp_data_files["families_path"],
            edges_path=temp_data_files["edges_path"],
            drugs_path=temp_data_files["drugs_path"],
        )

        edges = index.get_edges("atorvastatin")

        assert len(edges) > 0
        assert any(e.to_drug_id == "atorvastatin" for e in edges)

    def test_get_outgoing_edges(self, temp_data_files):
        index = GraphIndex(
            families_path=temp_data_files["families_path"],
            edges_path=temp_data_files["edges_path"],
            drugs_path=temp_data_files["drugs_path"],
        )

        edges = index.get_outgoing_edges("lovastatin")

        assert len(edges) == 2
        assert all(e.from_drug_id == "lovastatin" for e in edges)

    def test_get_incoming_edges(self, temp_data_files):
        index = GraphIndex(
            families_path=temp_data_files["families_path"],
            edges_path=temp_data_files["edges_path"],
            drugs_path=temp_data_files["drugs_path"],
        )

        edges = index.get_incoming_edges("atorvastatin")

        assert len(edges) == 1
        assert edges[0].from_drug_id == "lovastatin"

    def test_get_family(self, temp_data_files):
        index = GraphIndex(
            families_path=temp_data_files["families_path"],
            edges_path=temp_data_files["edges_path"],
            drugs_path=temp_data_files["drugs_path"],
        )

        family = index.get_family("statins")

        assert family is not None
        assert family.family_id == "statins"
        assert "atorvastatin" in family.member_drug_ids

    def test_get_families_for_drug(self, temp_data_files):
        index = GraphIndex(
            families_path=temp_data_files["families_path"],
            edges_path=temp_data_files["edges_path"],
            drugs_path=temp_data_files["drugs_path"],
        )

        families = index.get_families_for_drug("atorvastatin")

        assert len(families) == 1
        assert families[0].family_id == "statins"

    def test_get_all_drugs(self, temp_data_files):
        index = GraphIndex(
            families_path=temp_data_files["families_path"],
            edges_path=temp_data_files["edges_path"],
            drugs_path=temp_data_files["drugs_path"],
        )

        drugs = index.get_all_drugs()

        assert len(drugs) == 6
        assert "atorvastatin" in drugs
        assert "lisinopril" in drugs

    def test_get_all_families(self, temp_data_files):
        index = GraphIndex(
            families_path=temp_data_files["families_path"],
            edges_path=temp_data_files["edges_path"],
            drugs_path=temp_data_files["drugs_path"],
        )

        families = index.get_all_families()

        assert len(families) == 2
        assert "statins" in families
        assert "ace_inhibitors" in families

    def test_get_all_edges(self, temp_data_files):
        index = GraphIndex(
            families_path=temp_data_files["families_path"],
            edges_path=temp_data_files["edges_path"],
            drugs_path=temp_data_files["drugs_path"],
        )

        edges = index.get_all_edges()

        assert len(edges) == 2

    def test_stats_property(self, temp_data_files):
        index = GraphIndex(
            families_path=temp_data_files["families_path"],
            edges_path=temp_data_files["edges_path"],
            drugs_path=temp_data_files["drugs_path"],
        )

        stats = index.stats

        assert stats["total_nodes"] == 6
        assert stats["total_edges"] == 2
        assert stats["total_families"] == 2

    def test_refresh_reloads_data(self, temp_data_files):
        index = GraphIndex(
            families_path=temp_data_files["families_path"],
            edges_path=temp_data_files["edges_path"],
            drugs_path=temp_data_files["drugs_path"],
        )

        index.load()
        initial_stats = index.stats

        index.refresh()
        refreshed_stats = index.stats

        assert initial_stats == refreshed_stats

    def test_lazy_loading(self, temp_data_files):
        index = GraphIndex(
            families_path=temp_data_files["families_path"],
            edges_path=temp_data_files["edges_path"],
            drugs_path=temp_data_files["drugs_path"],
        )

        assert index._loaded is False

        index.get_node("atorvastatin")

        assert index._loaded is True


class TestDrugNode:
    def test_drug_node_creation(self):
        node = DrugNode(drug_id="test_drug", name="Test Drug")

        assert node.drug_id == "test_drug"
        assert node.name == "Test Drug"
        assert node.families == []
        assert node.outgoing_edges == []
        assert node.incoming_edges == []

    def test_drug_node_default_name(self):
        node = DrugNode(drug_id="test_drug")

        assert node.name == "test_drug"


class TestGetGraphIndex:
    def test_singleton_returns_same_instance(self):
        from backend.services import graph_index as gi

        gi._index_instance = None

        index1 = get_graph_index()
        index2 = get_graph_index()

        assert index1 is index2
