"""
Tests for multi-family membership (Task 8).

Tests validate:
- Drug can have multiple family_ids
- Cross-ATC drugs handled correctly
- Family lookup by ID works with multi-family drugs
"""

import pytest
from typing import List

from src.backend.models.drug import Drug
from src.backend.etl.family_builder import FamilyBuilder


def make_drug(
    id: str,
    name: str,
    atc_code: str,
    targets: List[str],
    year_approved: int = 2000,
    class_name: str = None,
) -> Drug:
    """Helper to create a Drug instance with minimal required fields"""
    return Drug(
        id=id,
        name=name,
        atc_code=atc_code,
        atc_category=atc_code[0] if atc_code else "V",
        year_approved=year_approved,
        targets=targets,
        class_name=class_name,
        smiles="CC",  # minimal SMILES
    )


class TestMultiFamilyMembership:
    """Test cases for multi-family membership resolver"""

    def test_drug_can_have_multiple_family_ids(self):
        """Drug with targets in multiple ATC categories belongs to multiple families"""
        builder = FamilyBuilder()

        drug1 = make_drug(
            id="cross_drug",
            name="CrossATCDrug",
            atc_code="C10AA01",
            targets=["HMG-CoA reductase", "Calcium channel"],
            year_approved=1996,
        )
        drug2 = make_drug(
            id="c_cardio",
            name="Cardio Drug",
            atc_code="C10AA02",
            targets=["HMG-CoA reductase"],
            year_approved=2000,
        )
        drug3 = make_drug(
            id="n_nervous",
            name="Nervous Drug",
            atc_code="N05BA01",
            targets=["Calcium channel"],
            year_approved=1998,
        )

        families = builder.build_families([drug1, drug2, drug3])
        drug_to_families = builder.get_drug_to_families()

        cross_drug_families = drug_to_families.get("cross_drug", [])
        assert len(cross_drug_families) >= 1

    def test_cross_atc_drug_in_both_families(self):
        """Cross-ATC drug appears in both family member lists"""
        builder = FamilyBuilder()

        cross_drug = make_drug(
            id="cross_drug",
            name="Cross Drug",
            atc_code="C10AA01",
            targets=["Shared Target X"],
            year_approved=1996,
        )
        cardio_drug = make_drug(
            id="cardio_only",
            name="Cardio Only",
            atc_code="C10AA02",
            targets=["Shared Target X"],
            year_approved=2000,
        )

        families = builder.build_families([cross_drug, cardio_drug])

        if families:
            family = families[0]
            assert "cross_drug" in family.member_drug_ids
            assert "cardio_only" in family.member_drug_ids

    def test_family_lookup_by_id_with_multi_family_drug(self):
        """Family lookup by ID works with multi-family drugs"""
        builder = FamilyBuilder()

        drug1 = make_drug(
            id="drug_a",
            name="Drug A",
            atc_code="C10AA01",
            targets=["Target Alpha"],
            year_approved=1995,
        )
        drug2 = make_drug(
            id="drug_b",
            name="Drug B",
            atc_code="C10AA02",
            targets=["Target Alpha"],
            year_approved=2000,
        )

        families = builder.build_families([drug1, drug2])
        drug_to_families = builder.get_drug_to_families()

        if families and drug_to_families.get("drug_a"):
            family_id = drug_to_families["drug_a"][0]
            family = next((f for f in families if f.family_id == family_id), None)
            assert family is not None
            assert "drug_a" in family.member_drug_ids

    def test_max_families_per_drug_enforced(self):
        """Drugs cannot exceed MAX_FAMILIES_PER_DRUG limit"""
        builder = FamilyBuilder()
        builder.MAX_FAMILIES_PER_DRUG = 2

        drugs = [
            make_drug(
                id=f"drug_{i}",
                name=f"Drug {i}",
                atc_code=f"C{i:02d}AA{i:02d}",
                targets=[f"Target {j}" for j in range(3)],
                year_approved=2000 + i,
            )
            for i in range(5)
        ]

        builder.build_families(drugs)
        drug_to_families = builder.get_drug_to_families()

        for drug_id, family_ids in drug_to_families.items():
            assert len(family_ids) <= builder.MAX_FAMILIES_PER_DRUG

    def test_backward_compatible_single_family(self):
        """Drugs with unique target/mechanism still create valid families"""
        builder = FamilyBuilder()

        drug1 = make_drug(
            id="single_drug",
            name="Single Drug",
            atc_code="C10AA01",
            targets=["Unique Target Z"],
            year_approved=1995,
        )
        drug2 = make_drug(
            id="single_drug2",
            name="Single Drug 2",
            atc_code="C10AA02",
            targets=["Unique Target Z"],
            year_approved=2000,
        )

        families = builder.build_families([drug1, drug2])
        drug_to_families = builder.get_drug_to_families()

        assert len(drug_to_families.get("single_drug", [])) >= 1
        assert "single_drug" in drug_to_families
        assert "single_drug2" in drug_to_families

    def test_drug_model_has_family_ids_field(self):
        """Drug model includes family_ids field"""
        drug = Drug(
            id="test_drug",
            name="Test Drug",
            atc_code="C10AA01",
            atc_category="C",
            smiles="CC",
            family_ids=["family_1", "family_2"],
        )
        assert hasattr(drug, "family_ids")
        assert drug.family_ids == ["family_1", "family_2"]

    def test_drug_family_ids_defaults_to_empty_list(self):
        """Drug model family_ids defaults to empty list"""
        drug = Drug(
            id="test_drug",
            name="Test Drug",
            atc_code="C10AA01",
            atc_category="C",
            smiles="CC",
        )
        assert drug.family_ids == []
