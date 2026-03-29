import pytest
from typing import List

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from backend.models.drug import Drug
from backend.models.drug_family import DrugFamily, FamilyBasis
from backend.models.lineage import LineageEdge, EdgeType, Provenance
from backend.etl.lineage_builder import LineageBuilder


def create_test_drug(
    drug_id: str,
    name: str,
    year_approved: int,
    atc_code: str,
    smiles: str,
    targets: List[str],
) -> Drug:
    return Drug(
        id=drug_id,
        name=name,
        smiles=smiles,
        inchikey=f"TEST-{drug_id}",
        atc_code=atc_code,
        atc_category=atc_code[0] if atc_code else "V",
        molecular_weight=300.0,
        phase="IV",
        year_approved=year_approved,
        generation=1,
        indication="Test indication",
        targets=targets,
        company="Test Company",
        synonyms=[],
        class_="Test Class",
        body_region="test",
        body_regions=["test"],
        public_summary="Test summary",
        kegg_id=None,
        pubchem_cid=None,
        drugbank_id=None,
    )


def create_test_family(
    family_id: str,
    label: str,
    member_ids: List[str],
    prototype_id: str,
    target_ids: List[str],
) -> DrugFamily:
    return DrugFamily(
        family_id=family_id,
        label=label,
        family_basis=FamilyBasis.target,
        prototype_drug_id=prototype_id,
        member_drug_ids=member_ids,
        representative_target_ids=target_ids,
        description=f"Test family {label}",
        atc_codes=["C10AA"],
    )


class TestHybridScoring:
    def test_chronology_score_older_to_newer(self):
        builder = LineageBuilder()
        parent = create_test_drug(
            "drug1", "Drug1", 1996, "C10AA05", "CC1CC2", ["Target1"]
        )
        child = create_test_drug(
            "drug2", "Drug2", 2000, "C10AB02", "CC1CC2", ["Target1"]
        )

        score = builder._compute_chronology_score(parent, child)
        assert score == 1.0

    def test_chronology_score_same_year(self):
        builder = LineageBuilder()
        parent = create_test_drug(
            "drug1", "Drug1", 2000, "C10AA05", "CC1CC2", ["Target1"]
        )
        child = create_test_drug(
            "drug2", "Drug2", 2000, "C10AB02", "CC1CC2", ["Target1"]
        )

        score = builder._compute_chronology_score(parent, child)
        assert score == 0.0

    def test_mechanism_score_same_third_level(self):
        builder = LineageBuilder()
        parent = create_test_drug(
            "drug1", "Drug1", 1996, "C10AA05", "CC1CC2", ["Target1"]
        )
        child = create_test_drug(
            "drug2", "Drug2", 2000, "C10AA02", "CC1CC2", ["Target1"]
        )

        score = builder._compute_mechanism_score(parent, child)
        assert score == 1.0

    def test_mechanism_score_same_second_level(self):
        builder = LineageBuilder()
        parent = create_test_drug(
            "drug1", "Drug1", 1996, "C10BA05", "CC1CC2", ["Target1"]
        )
        child = create_test_drug(
            "drug2", "Drug2", 2000, "C10CA02", "CC1CC2", ["Target1"]
        )

        score = builder._compute_mechanism_score(parent, child)
        assert score == 0.5

    def test_mechanism_score_different_category(self):
        builder = LineageBuilder()
        parent = create_test_drug(
            "drug1", "Drug1", 1996, "C10AA05", "CC1CC2", ["Target1"]
        )
        child = create_test_drug(
            "drug2", "Drug2", 2000, "N05AB02", "CC1CC2", ["Target1"]
        )

        score = builder._compute_mechanism_score(parent, child)
        assert score == 0.0

    def test_scaffold_score_identical_smiles(self):
        builder = LineageBuilder()
        parent = create_test_drug(
            "drug1", "Drug1", 1996, "C10AA05", "CCOc1ccccc1", ["Target1"]
        )
        child = create_test_drug(
            "drug2", "Drug2", 2000, "C10AB02", "CCOc1ccccc1", ["Target1"]
        )

        score = builder._compute_scaffold_score(parent, child)
        assert score == 1.0

    def test_hybrid_scoring_formula(self):
        builder = LineageBuilder()
        parent = create_test_drug(
            "drug1", "Drug1", 1996, "C10AA05", "CC1CC2", ["Target1"]
        )
        child = create_test_drug(
            "drug2", "Drug2", 2000, "C10AB02", "CC1CC3", ["Target1"]
        )

        breakdown = builder._compute_scores(parent, child, None)

        chronology = breakdown.chronology_score
        mechanism = breakdown.mechanism_score
        scaffold = breakdown.scaffold_score

        expected = chronology * 0.3 + mechanism * 0.4 + scaffold * 0.3

        actual = (
            breakdown.chronology_score * LineageBuilder.CHRONOLOGY_WEIGHT
            + breakdown.mechanism_score * LineageBuilder.MECHANISM_WEIGHT
            + breakdown.scaffold_score * LineageBuilder.SCAFFOLD_WEIGHT
        )

        assert abs(actual - expected) < 0.001


class TestEdgeGeneration:
    def test_creates_edge_within_family(self):
        builder = LineageBuilder()

        drugs = [
            create_test_drug(
                "lovastatin",
                "Lovastatin",
                1987,
                "C10AA01",
                "CCC1CC2",
                ["HMG-CoA reductase"],
            ),
            create_test_drug(
                "simvastatin",
                "Simvastatin",
                1991,
                "C10AA02",
                "CCC1CC3",
                ["HMG-CoA reductase"],
            ),
        ]

        family = create_test_family(
            "statin",
            "Statin Family",
            ["lovastatin", "simvastatin"],
            "lovastatin",
            ["HMG-CoA reductase"],
        )

        edges = builder.build_edges(drugs, [family])

        assert len(edges) == 1
        assert edges[0].from_drug_id == "lovastatin"
        assert edges[0].to_drug_id == "simvastatin"

    def test_no_edge_below_confidence_threshold(self):
        builder = LineageBuilder()

        drugs = [
            create_test_drug("drug1", "Drug1", 2000, "C10AA01", "AAA", ["Target1"]),
            create_test_drug("drug2", "Drug2", 2001, "N05AB02", "BBB", ["Target2"]),
        ]

        family = create_test_family(
            "test", "Test Family", ["drug1", "drug2"], "drug1", ["Target1"]
        )

        edges = builder.build_edges(drugs, [family])

        low_confidence_edges = [e for e in edges if e.confidence < 0.3]
        assert len(low_confidence_edges) == 0

    def test_no_edge_for_same_year_drugs(self):
        builder = LineageBuilder()

        drugs = [
            create_test_drug("drug1", "Drug1", 2000, "C10AA01", "AAA", ["Target1"]),
            create_test_drug("drug2", "Drug2", 2000, "C10AA02", "BBB", ["Target1"]),
        ]

        family = create_test_family(
            "test", "Test Family", ["drug1", "drug2"], "drug1", ["Target1"]
        )

        edges = builder.build_edges(drugs, [family])

        assert len(edges) == 0


class TestSchemaValidation:
    def test_edge_has_all_required_fields(self):
        builder = LineageBuilder()

        drugs = [
            create_test_drug("drug1", "Drug1", 1996, "C10AA01", "AAA", ["Target1"]),
            create_test_drug("drug2", "Drug2", 2000, "C10AA02", "BBB", ["Target1"]),
        ]

        family = create_test_family(
            "test", "Test Family", ["drug1", "drug2"], "drug1", ["Target1"]
        )

        edges = builder.build_edges(drugs, [family])

        assert len(edges) > 0
        edge = edges[0]

        assert edge.edge_id is not None
        assert edge.from_drug_id == "drug1"
        assert edge.to_drug_id == "drug2"
        assert edge.edge_type in [EdgeType.follow_on, EdgeType.generation_successor]
        assert 0.0 <= edge.confidence <= 1.0
        assert edge.score_breakdown is not None
        assert edge.provenance is not None
        assert edge.explanation is not None

    def test_edge_id_format(self):
        builder = LineageBuilder()

        drugs = [
            create_test_drug(
                "atorvastatin", "Atorvastatin", 1996, "C10AA01", "AAA", ["Target1"]
            ),
            create_test_drug(
                "rosuvastatin", "Rosuvastatin", 2003, "C10AA02", "BBB", ["Target1"]
            ),
        ]

        family = create_test_family(
            "statin",
            "Statin Family",
            ["atorvastatin", "rosuvastatin"],
            "atorvastatin",
            ["Target1"],
        )

        edges = builder.build_edges(drugs, [family])

        assert len(edges) > 0
        assert edges[0].edge_id == "atorvastatin_to_rosuvastatin"


class TestSaveAndLoad:
    def test_save_edges_to_json(self, tmp_path):
        builder = LineageBuilder()

        drugs = [
            create_test_drug("drug1", "Drug1", 1996, "C10AA01", "AAA", ["Target1"]),
            create_test_drug("drug2", "Drug2", 2000, "C10AA02", "BBB", ["Target1"]),
        ]

        family = create_test_family(
            "test", "Test Family", ["drug1", "drug2"], "drug1", ["Target1"]
        )

        edges = builder.build_edges(drugs, [family])

        output_path = tmp_path / "edges.json"
        builder.save_edges(str(output_path))

        assert output_path.exists()

        import json

        with open(output_path) as f:
            data = json.load(f)

        assert data["version"] == "1.0.0"
        assert data["total_edges"] == len(edges)
        assert len(data["edges"]) == len(edges)
