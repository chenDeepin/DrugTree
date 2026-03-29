"""
Task 10: Generation Rationale Tagging Tests

Tests for rationale tag assignment in lineage edges.
"""

import pytest
from typing import List
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from backend.models.drug import Drug
from backend.models.drug_family import DrugFamily, FamilyBasis
from backend.etl.lineage_builder import LineageBuilder


def make_drug(
    drug_id: str,
    name: str,
    year: int,
    targets: list = None,
    smiles: str = None,
    atc_code: str = "C10AA",
):
    return Drug(
        id=drug_id,
        name=name,
        smiles=smiles or "CC(C)C1=CC=CC=C1",
        inchikey=f"FAKE-{drug_id.upper()}",
        atc_code=atc_code,
        atc_category=atc_code[0] if atc_code else "C",
        molecular_weight=300.0,
        phase="IV",
        year_approved=year,
        generation=1,
        indication="Test",
        targets=targets or ["HMG-CoA reductase"],
        company="Test",
        synonyms=[],
        class_="Test",
        family_ids=[],
    )


def make_family(
    family_id: str,
    member_ids: list,
    prototype_id: str = None,
    targets: list = None,
    atc_codes: list = None,
):
    return DrugFamily(
        family_id=family_id,
        label=f"Test Family {family_id}",
        family_basis=FamilyBasis.mechanism,
        prototype_drug_id=prototype_id or member_ids[0] if member_ids else "unknown",
        member_drug_ids=member_ids,
        representative_target_ids=targets or ["HMG-CoA reductase"],
        atc_codes=atc_codes or ["C10AA"],
    )


class TestRationaleTags:
    def test_first_in_class_tag_for_oldest_drug(self):
        builder = LineageBuilder()

        parent = make_drug("lovastatin", "Lovastatin", 1987)
        child = make_drug("simvastatin", "Simvastatin", 1991)

        family = make_family("statin_family", ["lovastatin", "simvastatin"])

        edges = builder.build_edges([parent, child], [family])

        assert len(edges) == 1
        edge = edges[0]
        assert "first_in_class" in edge.generation_rationale
        assert "same_target" in edge.generation_rationale

    def test_me_too_tag_for_similar_drugs_close_years(self):
        builder = LineageBuilder()

        parent = make_drug("drug_a", "Drug A", 2000, smiles="CC(C)C1=CC=CC=C1")
        child = make_drug("drug_b", "Drug B", 2003, smiles="CC(C)C1=CC=CC=C1")

        family = make_family("test_family", ["drug_a", "drug_b"])

        edges = builder.build_edges([parent, child], [family])

        assert len(edges) == 1
        edge = edges[0]

        assert any(
            tag in edge.generation_rationale
            for tag in ["me_too", "same_target", "similar_scaffold"]
        )

    def test_improved_pk_tag_for_different_scaffold(self):
        builder = LineageBuilder()

        parent = make_drug(
            "old_drug", "Old Drug", 1990, smiles="c1ccccc1", atc_code="C10AA"
        )
        child = make_drug(
            "new_drug",
            "New Drug",
            2000,
            smiles="CC(=O)Oc1ccccc1C(=O)O",
            atc_code="C10AA",
        )

        family = make_family("test_family", ["old_drug", "new_drug"])

        edges = builder.build_edges([parent, child], [family])

        assert len(edges) == 1
        edge = edges[0]

        assert "same_target" in edge.generation_rationale

    def test_combination_tag_for_multi_parent_drug(self):
        builder = LineageBuilder()

        parent1 = make_drug("parent1", "Parent 1", 1990, targets=["Target A"])
        parent2 = make_drug("parent2", "Parent 2", 1992, targets=["Target A"])
        child = make_drug("child", "Child Drug", 2000, targets=["Target A"])

        family1 = make_family("family1", ["parent1", "child"])
        family2 = make_family("family2", ["parent2", "child"])

        edges = builder.build_edges([parent1, parent2, child], [family1, family2])

        parent_count = sum(1 for e in edges if e.to_drug_id == "child")
        assert parent_count == 2

        for edge in edges:
            if edge.to_drug_id == "child":
                assert "combination" in edge.generation_rationale

    def test_rationale_tags_never_empty_for_valid_edge(self):
        builder = LineageBuilder()

        parent = make_drug("parent", "Parent Drug", 1990)
        child = make_drug("child", "Child Drug", 2000)

        family = make_family("test_family", ["parent", "child"])

        edges = builder.build_edges([parent, child], [family])

        assert len(edges) == 1
        edge = edges[0]

        assert len(edge.generation_rationale) > 0

    def test_no_conflicting_first_in_class_and_me_too(self):
        builder = LineageBuilder()

        parent = make_drug("first", "First Drug", 1990)
        child = make_drug("second", "Second Drug", 1995)

        family = make_family("test_family", ["first", "second"])

        edges = builder.build_edges([parent, child], [family])

        assert len(edges) == 1
        edge = edges[0]

        has_first_in_class = "first_in_class" in edge.generation_rationale
        has_me_too = "me_too" in edge.generation_rationale

        if has_first_in_class:
            assert not has_me_too, "first_in_class and me_too are mutually exclusive"

    def test_schema_validation_generation_rationale_is_list(self):
        from backend.models.lineage import LineageEdge, EdgeType, Provenance

        edge = LineageEdge(
            edge_id="test_edge",
            from_drug_id="drug_a",
            to_drug_id="drug_b",
            edge_type=EdgeType.follow_on,
            confidence=0.7,
            generation_rationale=["first_in_class", "same_target"],
            score_breakdown={
                "chronology_score": 0.8,
                "mechanism_score": 0.6,
                "scaffold_score": 0.7,
            },
            provenance=Provenance.auto,
        )

        assert edge.generation_rationale == ["first_in_class", "same_target"]
        assert isinstance(edge.generation_rationale, list)

    def test_sequential_generation_tag(self):
        builder = LineageBuilder()

        parent = make_drug("gen1", "Gen 1 Drug", 1990)
        child = make_drug("gen2", "Gen 2 Drug", 2000)

        family = make_family("test_family", ["gen1", "gen2"])

        edges = builder.build_edges([parent, child], [family])

        assert len(edges) == 1
        edge = edges[0]

        assert "sequential_generation" in edge.generation_rationale
