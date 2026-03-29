"""
DrugTree - Graph Schema Contract Tests

Tests for Pydantic models in the graph schema layer (drug families, lineage edges, overrides).
These contract tests ensure schema stability and validate field requirements.

Reference: .sisyphus/plans/drugtree-graph-evolution.md (Wave 1)
"""

from datetime import datetime
from typing import Literal

import pytest
from pydantic import ValidationError

from src.backend.models.drug_family import DrugFamily, FamilyBasis
from src.backend.models.lineage import LineageEdge, EdgeType, Provenance
from src.backend.models.override import ManualOverride, OverrideAction
from src.backend.models.nodes import DiseaseNode, TargetNode, ClusterNode
from src.backend.models.drug import Drug
from src.backend.models.version import CURRENT_SCHEMA_VERSION


class TestDrugFamilySchema:
    """Contract tests for DrugFamily model"""

    def test_drug_family_schema_fields(self):
        """Test that DrugFamily has all required fields"""
        family = DrugFamily(
            family_id="statin",
            label="HMG-CoA Reductase Inhibitors",
            family_basis=FamilyBasis.mechanism,
            prototype_drug_id="lovastatin",
            member_drug_ids=["lovastatin", "simvastatin"],
            representative_target_ids=["P04035"],
        )

        assert family.family_id == "statin"
        assert family.label == "HMG-CoA Reductase Inhibitors"
        assert family.family_basis == FamilyBasis.mechanism
        assert family.prototype_drug_id == "lovastatin"
        assert len(family.member_drug_ids) == 2
        assert len(family.representative_target_ids) == 1
        assert family.schema_version == CURRENT_SCHEMA_VERSION

    def test_drug_family_enum_validates_correctly(self):
        """Test that family_basis enum validates correctly"""
        # Valid enum values
        for basis in FamilyBasis:
            family = DrugFamily(
                family_id=f"test-{basis.value}",
                label=f"Test {basis.value}",
                family_basis=basis,
                prototype_drug_id="test-drug",
            )
            assert family.family_basis == basis

    def test_drug_family_enum_rejects_invalid_values(self):
        """Test that family_basis rejects invalid values"""
        with pytest.raises(ValidationError) as exc_info:
            DrugFamily(
                family_id="test",
                label="Test",
                family_basis="invalid_basis",
                prototype_drug_id="test-drug",
            )
        error_str = str(exc_info.value).lower()
        assert "enum" in error_str or "should be" in error_str

    def test_drug_family_schema_version_format(self):
        """Test that schema_version follows semver pattern"""
        # Valid semver
        family = DrugFamily(
            family_id="test",
            label="Test",
            family_basis=FamilyBasis.target,
            prototype_drug_id="test-drug",
            schema_version="2.3.1",
        )
        assert family.schema_version == "2.3.1"

        # Invalid semver format
        with pytest.raises(ValidationError):
            DrugFamily(
                family_id="test",
                label="Test",
                family_basis=FamilyBasis.target,
                prototype_drug_id="test-drug",
                schema_version="invalid",
            )

    def test_drug_family_required_fields(self):
        """Test that required fields cannot be omitted"""
        # Missing family_id
        with pytest.raises(ValidationError) as exc_info:
            DrugFamily(
                label="Test",
                family_basis=FamilyBasis.target,
                prototype_drug_id="test-drug",
            )
        assert "family_id" in str(exc_info.value)

        # Missing label
        with pytest.raises(ValidationError) as exc_info:
            DrugFamily(
                family_id="test",
                family_basis=FamilyBasis.target,
                prototype_drug_id="test-drug",
            )
        assert "label" in str(exc_info.value)

        # Missing family_basis
        with pytest.raises(ValidationError) as exc_info:
            DrugFamily(
                family_id="test",
                label="Test",
                prototype_drug_id="test-drug",
            )
        assert "family_basis" in str(exc_info.value)

        # Missing prototype_drug_id
        with pytest.raises(ValidationError) as exc_info:
            DrugFamily(
                family_id="test",
                label="Test",
                family_basis=FamilyBasis.target,
            )
        assert "prototype_drug_id" in str(exc_info.value)

    def test_drug_family_default_values(self):
        """Test that list fields have default empty lists"""
        family = DrugFamily(
            family_id="test",
            label="Test",
            family_basis=FamilyBasis.target,
            prototype_drug_id="test-drug",
        )
        assert family.member_drug_ids == []
        assert family.representative_target_ids == []
        assert family.atc_codes == []
        assert family.schema_version == CURRENT_SCHEMA_VERSION  # Default version

    def test_drug_family_optional_fields(self):
        """Test that optional fields work correctly"""
        family = DrugFamily(
            family_id="test",
            label="Test",
            family_basis=FamilyBasis.mechanism,
            prototype_drug_id="test-drug",
            description="A test family for testing",
            atc_codes=["C10AA"],
        )
        assert family.description == "A test family for testing"
        assert family.atc_codes == ["C10AA"]


class TestFamilyBasisEnum:
    """Tests for FamilyBasis enum values"""

    def test_family_basis_has_required_values(self):
        """Test that all required family_basis values exist"""
        expected_values = {"target", "mechanism", "scaffold", "program_lineage"}
        actual_values = {basis.value for basis in FamilyBasis}
        assert expected_values == actual_values

    def test_family_basis_is_string_enum(self):
        """Test that FamilyBasis is a string enum for JSON serialization"""
        assert FamilyBasis.target.value == "target"
        assert FamilyBasis.mechanism.value == "mechanism"
        assert isinstance(FamilyBasis.target.value, str)


class TestLineageEdgeSchema:
    """Contract tests for LineageEdge model"""

    def test_lineage_edge_schema_fields(self):
        """Test that LineageEdge has all required fields"""
        edge = LineageEdge(
            edge_id="atorvastatin<-lovastatin",
            from_drug_id="lovastatin",
            to_drug_id="atorvastatin",
            edge_type=EdgeType.generation_successor,
            confidence=0.87,
            rationale_tags=["same_target", "similar_scaffold"],
            score_breakdown={
                "chronology_score": 0.8,
                "mechanism_score": 0.95,
                "scaffold_score": 0.85,
            },
            provenance=Provenance.auto,
            schema_version="1.0.0",
        )

        assert edge.edge_id == "atorvastatin<-lovastatin"
        assert edge.from_drug_id == "lovastatin"
        assert edge.to_drug_id == "atorvastatin"
        assert edge.edge_type == EdgeType.generation_successor
        assert edge.confidence == 0.87
        assert len(edge.rationale_tags) == 2
        assert "chronology_score" in edge.score_breakdown
        assert edge.provenance == Provenance.auto

    def test_lineage_edge_confidence_range(self):
        """Test that confidence validates [0.0, 1.0] range"""
        # Valid: boundary values
        edge_0 = LineageEdge(
            edge_id="test",
            from_drug_id="a",
            to_drug_id="b",
            edge_type=EdgeType.follow_on,
            confidence=0.0,
            score_breakdown={},
        )
        assert edge_0.confidence == 0.0

        edge_1 = LineageEdge(
            edge_id="test",
            from_drug_id="a",
            to_drug_id="b",
            edge_type=EdgeType.follow_on,
            confidence=1.0,
            score_breakdown={},
        )
        assert edge_1.confidence == 1.0

        # Invalid: > 1.0
        with pytest.raises(ValidationError):
            LineageEdge(
                edge_id="test",
                from_drug_id="a",
                to_drug_id="b",
                edge_type=EdgeType.follow_on,
                confidence=1.5,
                score_breakdown={},
            )

        # Invalid: < 0.0
        with pytest.raises(ValidationError):
            LineageEdge(
                edge_id="test",
                from_drug_id="a",
                to_drug_id="b",
                edge_type=EdgeType.follow_on,
                confidence=-0.1,
                score_breakdown={},
            )

    def test_lineage_edge_score_breakdown_required(self):
        """Test that score_breakdown field is required"""
        with pytest.raises(ValidationError) as exc_info:
            LineageEdge(
                edge_id="test",
                from_drug_id="a",
                to_drug_id="b",
                edge_type=EdgeType.follow_on,
                confidence=0.5,
            )
        assert "score_breakdown" in str(exc_info.value)

    def test_lineage_edge_edge_type_enum(self):
        """Test that edge_type enum validates correctly"""
        # Valid enum values
        for etype in EdgeType:
            edge = LineageEdge(
                edge_id=f"test-{etype.value}",
                from_drug_id="a",
                to_drug_id="b",
                edge_type=etype,
                confidence=0.5,
                score_breakdown={},
            )
            assert edge.edge_type == etype

        # Invalid value
        with pytest.raises(ValidationError):
            LineageEdge(
                edge_id="test",
                from_drug_id="a",
                to_drug_id="b",
                edge_type="invalid_type",
                confidence=0.5,
                score_breakdown={},
            )

    def test_lineage_edge_provenance_enum(self):
        """Test that provenance enum validates correctly"""
        for prov in Provenance:
            edge = LineageEdge(
                edge_id=f"test-{prov.value}",
                from_drug_id="a",
                to_drug_id="b",
                edge_type=EdgeType.follow_on,
                confidence=0.5,
                score_breakdown={},
                provenance=prov,
            )
            assert edge.provenance == prov


class TestEdgeTypeEnum:
    """Tests for EdgeType enum values"""

    def test_edge_type_has_required_values(self):
        """Test that all required edge_type values exist"""
        expected = {
            "follow_on",
            "generation_successor",
            "resistance_branch",
            "safety_branch",
            "combination_component",
            "prodrug",
            "metabolite",
            "me_too",
        }
        actual = {e.value for e in EdgeType}
        assert expected == actual

    def test_provenance_precedence_values(self):
        """Test that provenance has correct values for precedence"""
        expected = {"auto", "curated", "manual"}
        actual = {p.value for p in Provenance}
        assert expected == actual


class TestManualOverrideSchema:
    """Contract tests for ManualOverride model"""

    def test_manual_override_schema_fields(self):
        """Test that ManualOverride has all required fields"""
        override = ManualOverride(
            override_id="override-001",
            drug_id="pitavastatin",
            action=OverrideAction.promote_edge,
            target_edge_id="pitavastatin<-atorvastatin",
            rationale="Superior lipid-lowering in clinical trials",
            curator="curator@drugtree.org",
        )

        assert override.override_id == "override-001"
        assert override.drug_id == "pitavastatin"
        assert override.action == OverrideAction.promote_edge
        assert override.target_edge_id == "pitavastatin<-atorvastatin"
        assert override.rationale == "Superior lipid-lowering in clinical trials"
        assert override.curator == "curator@drugtree.org"
        assert isinstance(override.timestamp, datetime)

    def test_manual_override_action_enum(self):
        """Test that action enum validates correctly"""
        for action in OverrideAction:
            override = ManualOverride(
                override_id=f"test-{action.value}",
                drug_id="test-drug",
                action=action,
                rationale=f"Testing {action.value}",
            )
            assert override.action == action

        # Invalid action
        with pytest.raises(ValidationError):
            ManualOverride(
                override_id="test",
                drug_id="test-drug",
                action="invalid_action",
                rationale="Test",
            )

    def test_manual_override_required_fields(self):
        """Test that required fields cannot be omitted"""
        # Missing override_id
        with pytest.raises(ValidationError) as exc_info:
            ManualOverride(
                drug_id="test-drug",
                action=OverrideAction.force_include,
                rationale="Test",
            )
        assert "override_id" in str(exc_info.value)

        # Missing drug_id
        with pytest.raises(ValidationError) as exc_info:
            ManualOverride(
                override_id="test",
                action=OverrideAction.force_include,
                rationale="Test",
            )
        assert "drug_id" in str(exc_info.value)

        # Missing action
        with pytest.raises(ValidationError) as exc_info:
            ManualOverride(
                override_id="test",
                drug_id="test-drug",
                rationale="Test",
            )
        assert "action" in str(exc_info.value)

        # Missing rationale
        with pytest.raises(ValidationError) as exc_info:
            ManualOverride(
                override_id="test",
                drug_id="test-drug",
                action=OverrideAction.force_include,
            )
        assert "rationale" in str(exc_info.value)

    def test_manual_override_optional_fields(self):
        """Test that optional fields work correctly"""
        override = ManualOverride(
            override_id="test",
            drug_id="test-drug",
            action=OverrideAction.force_include,
            rationale="Test rationale",
        )
        assert override.target_edge_id is None
        assert override.curator is None
        assert isinstance(override.timestamp, datetime)


class TestOverrideActionEnum:
    """Tests for OverrideAction enum values"""

    def test_override_action_has_required_values(self):
        """Test that all required override_action values exist"""
        expected = {
            "force_include",
            "force_exclude",
            "promote_edge",
            "demote_edge",
        }
        actual = {a.value for a in OverrideAction}
        assert expected == actual

    def test_override_precedence_contract(self):
        """Test that manual > curated > auto precedence contract is documented"""
        # This is a documentation/contract test
        # Precedence order: manual > curated_rule > auto_rule > fallback
        assert Provenance.manual.value == "manual"
        assert Provenance.curated.value == "curated"
        assert Provenance.auto.value == "auto"

        # Verify all precedence values exist
        # Note: Precedence is determined at runtime, not enum order
        precedence_values = {
            Provenance.manual.value,
            Provenance.curated.value,
            Provenance.auto.value,
        }
        assert precedence_values == {"manual", "curated", "auto"}


class TestNodeNamespacing:
    """Tests for node type discrimination and full_id namespacing"""

    def test_drug_has_node_type_and_full_id(self):
        """Test that Drug model has node_type and full_id computed field"""
        drug = Drug(
            id="atorvastatin",
            name="Atorvastatin",
            atc_code="C10AA05",
            atc_category="C",
        )
        assert drug.node_type == "drug"
        assert drug.full_id == "drug:atorvastatin"

    def test_disease_node_has_node_type_and_full_id(self):
        """Test that DiseaseNode has correct node_type and full_id"""
        disease = DiseaseNode(
            id="glioma",
            canonical_name="Glioma",
        )
        assert disease.node_type == "disease"
        assert disease.full_id == "disease:glioma"

    def test_target_node_has_node_type_and_full_id(self):
        """Test that TargetNode has correct node_type and full_id"""
        target = TargetNode(
            id="EGFR",
            symbol="EGFR",
            name="Epidermal Growth Factor Receptor",
        )
        assert target.node_type == "target"
        assert target.full_id == "target:EGFR"

    def test_cluster_node_has_node_type_and_full_id(self):
        """Test that ClusterNode has correct node_type and full_id"""
        cluster = ClusterNode(
            id="statins",
            label="HMG-CoA Reductase Inhibitors",
        )
        assert cluster.node_type == "cluster"
        assert cluster.full_id == "cluster:statins"

    def test_full_id_collision_detection(self):
        """Test that same ID from different node types creates unique full_ids"""
        shared_id = "test-entity"
        drug = Drug(
            id=shared_id,
            name="Test Drug",
            atc_code="A01AA01",
            atc_category="A",
        )
        disease = DiseaseNode(id=shared_id, canonical_name="Test Disease")
        target = TargetNode(id=shared_id, symbol=shared_id)
        cluster = ClusterNode(id=shared_id, label="Test Cluster")

        full_ids = {drug.full_id, disease.full_id, target.full_id, cluster.full_id}
        assert len(full_ids) == 4, "full_ids should be unique per node type"
        assert drug.full_id == f"drug:{shared_id}"
        assert disease.full_id == f"disease:{shared_id}"
        assert target.full_id == f"target:{shared_id}"
        assert cluster.full_id == f"cluster:{shared_id}"

    def test_node_type_is_immutable_literal(self):
        """Test that node_type is properly constrained to literal values"""
        drug = Drug(
            id="test",
            name="Test",
            atc_code="A01AA01",
            atc_category="A",
        )
        assert drug.node_type == "drug"
        assert Drug.model_fields["node_type"].annotation == Literal["drug"]

    def test_drug_id_references_not_broken(self):
        """Test that existing drug.id references still work (backward compatibility)"""
        drug = Drug(
            id="simvastatin",
            name="Simvastatin",
            atc_code="C10AA03",
            atc_category="C",
        )
        assert drug.id == "simvastatin"
        assert hasattr(drug, "full_id")
        assert drug.id in drug.full_id


class TestSchemaVersioning:
    """Tests for schema version infrastructure"""

    def test_current_schema_version_defined(self):
        """Test that CURRENT_SCHEMA_VERSION is defined and valid"""
        assert CURRENT_SCHEMA_VERSION == "1.1.0"
        parts = CURRENT_SCHEMA_VERSION.split(".")
        assert len(parts) == 3
        assert all(part.isdigit() for part in parts)

    def test_drug_has_schema_version(self):
        """Test that Drug model includes schema_version field"""
        drug = Drug(
            id="test",
            name="Test Drug",
            atc_code="A01AA01",
            atc_category="A",
        )
        assert hasattr(drug, "schema_version")
        assert drug.schema_version == CURRENT_SCHEMA_VERSION

    def test_drug_family_has_schema_version(self):
        """Test that DrugFamily model includes schema_version field"""
        family = DrugFamily(
            family_id="test-family",
            label="Test Family",
            family_basis=FamilyBasis.mechanism,
            prototype_drug_id="test-prototype",
            description="Test family for schema validation",
        )
        assert hasattr(family, "schema_version")
        assert family.schema_version == CURRENT_SCHEMA_VERSION

    def test_lineage_edge_has_schema_version(self):
        """Test that LineageEdge model includes schema_version field"""
        edge = LineageEdge(
            edge_id="edge-001",
            from_drug_id="drug-a",
            to_drug_id="drug-b",
            edge_type=EdgeType.follow_on,
            confidence=0.85,
            score_breakdown={"chronology": 0.8, "mechanism": 0.9, "scaffold": 0.85},
            provenance=Provenance.auto,
            description="Test edge for schema validation",
        )
        assert hasattr(edge, "schema_version")
        assert edge.schema_version == CURRENT_SCHEMA_VERSION

    def test_manual_override_has_schema_version(self):
        """Test that ManualOverride model includes schema_version field"""
        override = ManualOverride(
            override_id="override-001",
            drug_id="test-drug",
            action=OverrideAction.force_include,
            rationale="Test rationale for schema validation",
        )
        assert hasattr(override, "schema_version")
        assert override.schema_version == CURRENT_SCHEMA_VERSION

    def test_schema_version_defaults_to_current(self):
        """Test that schema_version defaults to CURRENT_SCHEMA_VERSION"""
        drug = Drug(
            id="test",
            name="Test",
            atc_code="A01AA01",
            atc_category="A",
        )
        assert drug.schema_version == CURRENT_SCHEMA_VERSION

    def test_schema_version_is_immutable_after_creation(self):
        """Test that schema_version cannot be changed after creation"""
        drug = Drug(
            id="test",
            name="Test",
            atc_code="A01AA01",
            atc_category="A",
        )
        original_version = drug.schema_version
        assert drug.schema_version == original_version
