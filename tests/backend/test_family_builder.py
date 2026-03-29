"""
DrugTree - Family Builder Tests

Tests for the FamilyBuilder class that groups drugs into families
based on shared targets, mechanisms, and scaffolds.

Reference: .sisyphus/plans/drugtree-graph-evolution.md (Task 6)
"""

import json
import pytest
from pathlib import Path
from typing import List

from src.backend.models.drug import Drug
from src.backend.models.drug_family import DrugFamily, FamilyBasis
from src.backend.models.version import CURRENT_SCHEMA_VERSION
from src.backend.etl.family_builder import FamilyBuilder, FamilyCandidate


# Test fixtures
@pytest.fixture
def sample_drugs() -> List[Drug]:
    """Sample drugs for testing - statins with shared target"""
    return [
        Drug(
            id="lovastatin",
            name="Lovastatin",
            smiles="CC1=...",
            inchikey="CHEBI:40303",
            atc_code="C10AA02",
            atc_category="C",
            molecular_weight=404.55,
            phase="IV",
            year_approved=1987,
            generation=1,
            indication="Hypercholesterolemia",
            targets=["HMG-CoA reductase"],
            company="Merck",
            synonyms=["Mevacor"],
            class_name="Statin",
        ),
        Drug(
            id="simvastatin",
            name="Simvastatin",
            smiles="CC2=...",
            inchikey="CHEBI:40304",
            atc_code="C10AA01",
            atc_category="C",
            molecular_weight=418.57,
            phase="IV",
            year_approved=1991,
            generation=2,
            indication="Hypercholesterolemia",
            targets=["HMG-CoA reductase"],
            company="Merck",
            synonyms=["Zocor"],
            class_name="Statin",
        ),
        Drug(
            id="atorvastatin",
            name="Atorvastatin",
            smiles="CC3=...",
            inchikey="XUKUURHRXDUEBC-UHFFFAOYSA-N",
            atc_code="C10AA05",
            atc_category="C",
            molecular_weight=558.64,
            phase="IV",
            year_approved=1996,
            generation=2,
            indication="Hypercholesterolemia",
            targets=["HMG-CoA reductase"],
            company="Pfizer",
            synonyms=["Lipitor"],
            class_name="Statin",
        ),
        Drug(
            id="rosuvastatin",
            name="Rosuvastatin",
            smiles="CC4=...",
            inchikey="BPRHIVZBDXFDRE-UHFFFAOYSA-N",
            atc_code="C10AA07",
            atc_category="C",
            molecular_weight=1001.14,
            phase="IV",
            year_approved=2003,
            generation=2,
            indication="Hypercholesterolemia",
            targets=["HMG-CoA reductase"],
            company="AstraZeneca",
            synonyms=["Crestor"],
            class_name="Statin",
        ),
        Drug(
            id="metformin",
            name="Metformin",
            smiles="CN=...",
            inchikey="XKHYZBZRLZFKPM-UHFFFAOYSA-N",
            atc_code="A10BA02",
            atc_category="A",
            molecular_weight=165.62,
            phase="IV",
            year_approved=1995,
            generation=1,
            indication="Type 2 diabetes",
            targets=["AMPK", "Complex I"],
            company="Bristol-Myers Squibb",
            synonyms=["Glucophage"],
            class_name="Biguanide",
        ),
        Drug(
            id="phenformin",
            name="Phenformin",
            smiles="CCC1=...",
            inchikey="PHENFORMIN123",
            atc_code="A10BA01",
            atc_category="A",
            molecular_weight=205.26,
            phase="IV",
            year_approved=1960,
            generation=1,
            indication="Type 2 diabetes",
            targets=["AMPK", "Complex I"],
            company="CIBA",
            synonyms=["DBI"],
            class_name="Biguanide",
        ),
    ]


@pytest.fixture
def builder() -> FamilyBuilder:
    """FamilyBuilder instance"""
    return FamilyBuilder()


class TestGroupByTarget:
    """Test case 1: Groups drugs by shared target"""

    def test_groups_drugs_by_shared_target(
        self, builder: FamilyBuilder, sample_drugs: List[Drug]
    ):
        """Verify drugs sharing a target are grouped together"""
        families = builder.build_families(sample_drugs)

        # Find target-based family for HMG-CoA reductase (original case)
        target_families = [
            f
            for f in families
            if f.family_basis == FamilyBasis.target
            and "HMG-CoA reductase" in f.representative_target_ids
        ]

        assert len(target_families) == 1, (
            "Should have exactly one HMG-CoA reductase target family"
        )

        family = target_families[0]

        # Verify all statins are in the family
        assert "lovastatin" in family.member_drug_ids
        assert "simvastatin" in family.member_drug_ids
        assert "atorvastatin" in family.member_drug_ids
        assert "rosuvastatin" in family.member_drug_ids

        # Verify metformin is NOT in this family (different target)
        assert "metformin" not in family.member_drug_ids

    def test_multi_target_drugs(self, builder: FamilyBuilder, sample_drugs: List[Drug]):
        """Verify drugs with multiple targets appear in multiple families"""
        families = builder.build_families(sample_drugs)

        ampk_families = [
            f
            for f in families
            if f.family_basis == FamilyBasis.target
            and "AMPK" in f.representative_target_ids
        ]
        complex_i_families = [
            f
            for f in families
            if f.family_basis == FamilyBasis.target
            and "Complex I" in f.representative_target_ids
        ]

        assert len(ampk_families) >= 1, "Should have at least one AMPK target family"
        assert len(complex_i_families) >= 1, (
            "Should have at least one Complex I target family"
        )

        assert "metformin" in ampk_families[0].member_drug_ids
        assert "phenformin" in ampk_families[0].member_drug_ids
        assert "metformin" in complex_i_families[0].member_drug_ids
        assert "phenformin" in complex_i_families[0].member_drug_ids

    def test_single_drug_no_family(self, builder: FamilyBuilder):
        """Verify a single drug with unique target doesn't create a family"""
        single_drug = [
            Drug(
                id="unique_drug",
                name="Unique Drug",
                smiles="CC1=...",
                inchikey="UNIQUE123",
                atc_code="N05BA01",
                atc_category="N",
                molecular_weight=300.0,
                phase="II",
                year_approved=2020,
                generation=1,
                indication="Test indication",
                targets=["Unique Target"],
                company="TestCo",
                synonyms=[],
                class_name="Test",
            )
        ]

        families = builder.build_families(single_drug)
        target_families = [f for f in families if f.family_basis == FamilyBasis.target]

        # Single drug should not create a family (need at least 2)
        assert len(target_families) == 0


class TestPrototypeSelection:
    """Test case 2: Oldest drug selected as prototype"""

    def test_oldest_drug_is_prototype(
        self, builder: FamilyBuilder, sample_drugs: List[Drug]
    ):
        """Verify the oldest approved drug is selected as prototype"""
        families = builder.build_families(sample_drugs)

        statin_families = [
            f
            for f in families
            if f.family_basis == FamilyBasis.target
            and "HMG-CoA reductase" in f.representative_target_ids
        ]

        assert len(statin_families) == 1
        family = statin_families[0]

        assert family.prototype_drug_id == "lovastatin"

    def test_prototype_fallback_no_year(self, builder: FamilyBuilder):
        """Verify first drug is selected when no year_approved available"""
        drugs_no_year = [
            Drug(
                id="drug_a",
                name="Drug A",
                smiles="CC1=...",
                inchikey="DRUGA123",
                atc_code="C10AA09",
                atc_category="C",
                molecular_weight=300.0,
                phase="IV",
                year_approved=None,  # No year
                generation=1,
                indication="Test",
                targets=["Target X"],
                company="TestCo",
                synonyms=[],
                class_name="Test",
            ),
            Drug(
                id="drug_b",
                name="Drug B",
                smiles="CC2=...",
                inchikey="DRUGB456",
                atc_code="C10AA10",
                atc_category="C",
                molecular_weight=320.0,
                phase="IV",
                year_approved=None,  # No year
                generation=1,
                indication="Test",
                targets=["Target X"],
                company="TestCo",
                synonyms=[],
                class_name="Test",
            ),
        ]

        families = builder.build_families(drugs_no_year)
        target_families = [f for f in families if f.family_basis == FamilyBasis.target]

        assert len(target_families) == 1
        # Falls back to first drug
        assert target_families[0].prototype_drug_id == "drug_a"

    def test_prototype_generation_order(
        self, builder: FamilyBuilder, sample_drugs: List[Drug]
    ):
        """Verify prototype selection respects chronological order (not generation field)"""
        families = builder.build_families(sample_drugs)

        statin_families = [
            f
            for f in families
            if f.family_basis == FamilyBasis.target
            and "HMG-CoA reductase" in f.representative_target_ids
        ]

        assert len(statin_families) == 1
        family = statin_families[0]

        assert family.prototype_drug_id == "lovastatin"


class TestMechanismGrouping:
    """Test case 3: Groups drugs by ATC 3rd level (mechanism)"""

    def test_groups_by_atc_3rd_level(
        self, builder: FamilyBuilder, sample_drugs: List[Drug]
    ):
        """Verify drugs with same ATC 3rd level are grouped"""
        families = builder.build_families(sample_drugs)

        mechanism_families = [
            f
            for f in families
            if f.family_basis == FamilyBasis.mechanism
            and any(code.startswith("C10A") for code in f.atc_codes)
        ]

        assert len(mechanism_families) >= 1, (
            "Should have at least one mechanism family for C10A"
        )

        statin_mechanism_family = None
        for f in mechanism_families:
            if any(d in f.member_drug_ids for d in ["lovastatin", "atorvastatin"]):
                statin_mechanism_family = f
                break

        assert statin_mechanism_family is not None, (
            "Should have mechanism family containing statins"
        )


class TestSchemaValidation:
    """Test case 4: Output schema validation"""

    def test_family_schema_valid(
        self, builder: FamilyBuilder, sample_drugs: List[Drug]
    ):
        """Verify all generated families pass DrugFamily schema validation"""
        families = builder.build_families(sample_drugs)

        assert len(families) > 0, "Should generate at least one family"

        for family in families:
            # This will raise ValidationError if schema is invalid
            assert isinstance(family, DrugFamily)
            assert family.family_id
            assert family.label
            assert family.family_basis in FamilyBasis
            assert family.prototype_drug_id
            assert len(family.member_drug_ids) >= 2
            assert family.schema_version == CURRENT_SCHEMA_VERSION

    def test_family_id_format(self, builder: FamilyBuilder, sample_drugs: List[Drug]):
        """Verify family_id follows expected format: {basis}_{key}_{hash}"""
        families = builder.build_families(sample_drugs)

        for family in families:
            parts = family.family_id.split("_")
            assert len(parts) >= 3, (
                f"family_id should have at least 3 parts: {family.family_id}"
            )
            assert parts[0] in [
                "target",
                "mechanism",
                "scaffold",
                "program",
            ], f"First part should be basis: {family.family_id}"
            # Last part should be 8-char hex hash
            assert len(parts[-1]) == 8, (
                f"Last part should be 8-char hash: {family.family_id}"
            )

    def test_no_duplicate_family_members(
        self, builder: FamilyBuilder, sample_drugs: List[Drug]
    ):
        """Verify member_drug_ids has no duplicates"""
        families = builder.build_families(sample_drugs)

        for family in families:
            member_ids = family.member_drug_ids
            assert len(member_ids) == len(set(member_ids)), (
                f"Duplicate members in family {family.family_id}"
            )

    def test_members_are_sorted(self, builder: FamilyBuilder, sample_drugs: List[Drug]):
        """Verify member_drug_ids are sorted alphabetically"""
        families = builder.build_families(sample_drugs)

        for family in families:
            member_ids = family.member_drug_ids
            assert member_ids == sorted(member_ids), (
                f"Members should be sorted: {member_ids}"
            )


class TestSaveFamilies:
    """Test JSON output functionality"""

    def test_save_families_to_json(
        self, builder: FamilyBuilder, sample_drugs: List[Drug], tmp_path: Path
    ):
        """Verify families can be saved to valid JSON"""
        builder.build_families(sample_drugs)
        output_path = str(tmp_path / "test_families.json")

        builder.save_families(output_path)

        # Verify file exists
        assert Path(output_path).exists()

        # Verify JSON is valid
        with open(output_path) as f:
            data = json.load(f)

        assert "version" in data
        assert "total_families" in data
        assert "families" in data
        assert data["total_families"] == len(data["families"])

    def test_load_drugs_from_json(self, builder: FamilyBuilder, tmp_path: Path):
        """Verify drugs can be loaded from JSON file"""
        # Create test drugs JSON
        test_data = {
            "drugs": [
                {
                    "id": "test_drug",
                    "name": "Test Drug",
                    "smiles": "CC1=...",
                    "inchikey": "TEST123",
                    "atc_code": "C10AA01",
                    "atc_category": "C",
                    "molecular_weight": 300.0,
                    "phase": "IV",
                    "year_approved": 2000,
                    "generation": 1,
                    "indication": "Test",
                    "targets": ["Target X"],
                    "company": "TestCo",
                    "synonyms": [],
                    "class_name": "Test",
                }
            ]
        }

        json_path = str(tmp_path / "test_drugs.json")
        with open(json_path, "w") as f:
            json.dump(test_data, f)

        # Load and verify
        drugs = FamilyBuilder.load_drugs_from_json(json_path)
        assert len(drugs) == 1
        assert drugs[0].id == "test_drug"
        assert drugs[0].name == "Test Drug"


class TestEdgeCases:
    """Edge case tests"""

    def test_empty_drug_list(self, builder: FamilyBuilder):
        """Verify empty drug list returns no families"""
        families = builder.build_families([])
        assert len(families) == 0

    def test_drug_with_no_targets(self, builder: FamilyBuilder):
        """Verify drug with empty targets list doesn't crash"""
        drugs = [
            Drug(
                id="no_target_drug",
                name="No Target Drug",
                smiles="CC1=...",
                inchikey="NOTARGET123",
                atc_code="C10AA01",
                atc_category="C",
                molecular_weight=300.0,
                phase="II",
                year_approved=2020,
                generation=1,
                indication="Test",
                targets=[],  # Empty targets
                company="TestCo",
                synonyms=[],
                class_name="Test",
            )
        ]

        families = builder.build_families(drugs)
        target_families = [f for f in families if f.family_basis == FamilyBasis.target]
        assert len(target_families) == 0

    def test_drug_with_no_atc_code(self, builder: FamilyBuilder):
        """Verify drug with missing ATC code handles gracefully"""
        # This test checks that _get_atc_3rd_level returns None for invalid ATC
        result = builder._get_atc_3rd_level("")
        assert result is None

        result = builder._get_atc_3rd_level("A")  # Too short
        assert result is None

        result = builder._get_atc_3rd_level("C10AA05")
        assert result == "C10A"


class TestTargetNormalization:
    """Test target name normalization"""

    def test_normalize_target_variations(self, builder: FamilyBuilder):
        """Verify target names are normalized correctly"""
        assert builder._normalize_target("HMG-CoA Reductase") == "hmg coa reductase"
        assert builder._normalize_target("HMG_CoA_Reductase") == "hmg coa reductase"
        assert builder._normalize_target("  HMG-CoA Reductase  ") == "hmg coa reductase"
        assert builder._normalize_target("") is None
        assert builder._normalize_target(None) is None
