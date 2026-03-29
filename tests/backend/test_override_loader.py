"""
DrugTree - Override Loader Tests

Tests for manual override loading and precedence enforcement.
Reference: .sisyphus/plans/drugtree-graph-evolution.md (Task 12)
"""

import pytest
from datetime import datetime
from pathlib import Path

from src.backend.etl.override_loader import OverrideLoader
from src.backend.models.override import ManualOverride, OverrideAction
from src.backend.models.lineage import LineageEdge, EdgeType, Provenance


class TestOverrideLoader:
    """Test OverrideLoader functionality"""

    def test_loader_initialization_empty_file(self, tmp_path):
        """Test loader initialization with non-existent file creates empty structure"""
        override_file = tmp_path / "manual_overrides.json"

        loader = OverrideLoader(overrides_path=override_file)

        assert loader.overrides == []
        assert override_file.exists()

    def test_precedence_levels(self):
        """Test precedence order: manual > curated > auto > fallback"""
        loader = OverrideLoader()

        assert loader.get_precedence_level("manual") == 3
        assert loader.get_precedence_level("curated") == 2
        assert loader.get_precedence_level("auto") == 1
        assert loader.get_precedence_level("fallback") == 0
        assert loader.get_precedence_level("unknown") == 0

    def test_force_include_low_confidence_edge(self):
        """
        Scenario: Manual force_include overrides low confidence edge

        Steps:
        1. Create auto edge with confidence=0.4 (below 0.5 threshold)
        2. Create override with action=force_include for same edge
        3. Run OverrideLoader.apply_overrides()
        4. Assert edge present in final list with provenance="manual"
        """
        loader = OverrideLoader()

        # Create low-confidence edge
        edge = LineageEdge(
            edge_id="pitavastatin<-atorvastatin",
            from_drug_id="atorvastatin",
            to_drug_id="pitavastatin",
            edge_type=EdgeType.generation_successor,
            confidence=0.4,  # Below threshold
            score_breakdown={"chronology": 0.5, "mechanism": 0.3, "scaffold": 0.4},
            provenance=Provenance.auto,
        )

        # Create force_include override
        override = ManualOverride(
            override_id="override-001",
            drug_id="pitavastatin",
            action=OverrideAction.force_include,
            rationale="Clinical trial data shows superior efficacy",
            curator="curator@drugtree.org",
        )

        # Apply overrides
        result = loader.apply_overrides([edge], [override], confidence_threshold=0.5)

        # Assert edge present with manual provenance
        assert len(result) == 1
        assert result[0].edge_id == "pitavastatin<-atorvastatin"
        assert result[0].provenance == Provenance.manual
        assert "Override force_include" in result[0].explanation

    def test_force_exclude_high_confidence_edge(self):
        """
        Scenario: Manual force_exclude removes high confidence edge

        Steps:
        1. Create auto edge with confidence=0.8 (above threshold)
        2. Create override with action=force_exclude
        3. Run OverrideLoader.apply_overrides()
        4. Assert edge NOT in final list
        """
        loader = OverrideLoader()

        # Create high-confidence edge
        edge = LineageEdge(
            edge_id="rosuvastatin<-atorvastatin",
            from_drug_id="atorvastatin",
            to_drug_id="rosuvastatin",
            edge_type=EdgeType.generation_successor,
            confidence=0.8,  # Above threshold
            score_breakdown={"chronology": 0.7, "mechanism": 0.9, "scaffold": 0.8},
            provenance=Provenance.auto,
        )

        # Create force_exclude override
        override = ManualOverride(
            override_id="override-002",
            drug_id="rosuvastatin",
            action=OverrideAction.force_exclude,
            rationale="Incorrect relationship - not a direct successor",
            curator="curator@drugtree.org",
        )

        # Apply overrides
        result = loader.apply_overrides([edge], [override], confidence_threshold=0.5)

        # Assert edge excluded
        assert len(result) == 0

    def test_override_precedence_manual_wins(self):
        """
        Scenario: Override precedence - manual > curated > auto > fallback

        Steps:
        1. Create edge with provenance="auto", confidence=0.7
        2. Apply multiple overrides with different provenance
        3. Assert manual override takes highest precedence
        """
        loader = OverrideLoader()

        # Create edge with auto provenance
        edge = LineageEdge(
            edge_id="simvastatin<-lovastatin",
            from_drug_id="lovastatin",
            to_drug_id="simvastatin",
            edge_type=EdgeType.generation_successor,
            confidence=0.7,
            score_breakdown={"chronology": 0.6, "mechanism": 0.8, "scaffold": 0.7},
            provenance=Provenance.auto,
        )

        # Create multiple overrides (manual should win)
        overrides = [
            ManualOverride(
                override_id="override-003",
                drug_id="simvastatin",
                action=OverrideAction.promote_edge,
                target_edge_id="simvastatin<-lovastatin",
                rationale="Strong clinical evidence",
                curator="curator@drugtree.org",
            )
        ]

        # Apply overrides
        result = loader.apply_overrides([edge], overrides, confidence_threshold=0.5)

        # Assert manual override wins (confidence=1.0, provenance=manual)
        assert len(result) == 1
        assert result[0].confidence == 1.0
        assert result[0].provenance == Provenance.manual

    def test_promote_edge_sets_confidence_to_1(self):
        """Test promote_edge action sets confidence to 1.0"""
        loader = OverrideLoader()

        # Create edge with medium confidence
        edge = LineageEdge(
            edge_id="pravastatin<-lovastatin",
            from_drug_id="lovastatin",
            to_drug_id="pravastatin",
            edge_type=EdgeType.generation_successor,
            confidence=0.6,
            score_breakdown={"chronology": 0.5, "mechanism": 0.7, "scaffold": 0.6},
            provenance=Provenance.auto,
        )

        # Create promote_edge override
        override = ManualOverride(
            override_id="override-004",
            drug_id="pravastatin",
            action=OverrideAction.promote_edge,
            target_edge_id="pravastatin<-lovastatin",
            rationale="Confirmed by clinical trials",
            curator="curator@drugtree.org",
        )

        # Apply overrides
        result = loader.apply_overrides([edge], [override], confidence_threshold=0.5)

        # Assert confidence = 1.0
        assert len(result) == 1
        assert result[0].confidence == 1.0
        assert result[0].provenance == Provenance.manual

    def test_demote_edge_sets_confidence_to_0(self):
        """Test demote_edge action sets confidence to 0.0"""
        loader = OverrideLoader()

        # Create edge with high confidence
        edge = LineageEdge(
            edge_id="fluvastatin<-lovastatin",
            from_drug_id="lovastatin",
            to_drug_id="fluvastatin",
            edge_type=EdgeType.generation_successor,
            confidence=0.8,
            score_breakdown={"chronology": 0.7, "mechanism": 0.9, "scaffold": 0.8},
            provenance=Provenance.auto,
        )

        # Create demote_edge override
        override = ManualOverride(
            override_id="override-005",
            drug_id="fluvastatin",
            action=OverrideAction.demote_edge,
            target_edge_id="fluvastatin<-lovastatin",
            rationale="Relationship not supported by data",
            curator="curator@drugtree.org",
        )

        # Apply overrides
        result = loader.apply_overrides([edge], [override], confidence_threshold=0.5)

        # Assert confidence = 0.0 (still in result, but demoted)
        assert len(result) == 1
        assert result[0].confidence == 0.0
        assert result[0].provenance == Provenance.manual

    def test_multiple_overrides_same_drug(self):
        """Test handling multiple overrides for same drug"""
        loader = OverrideLoader()

        # Create two edges
        edge1 = LineageEdge(
            edge_id="drug_b<-drug_a",
            from_drug_id="drug_a",
            to_drug_id="drug_b",
            edge_type=EdgeType.generation_successor,
            confidence=0.7,
            score_breakdown={"chronology": 0.6, "mechanism": 0.8, "scaffold": 0.7},
            provenance=Provenance.auto,
        )

        edge2 = LineageEdge(
            edge_id="drug_c<-drug_a",
            from_drug_id="drug_a",
            to_drug_id="drug_c",
            edge_type=EdgeType.generation_successor,
            confidence=0.4,  # Below threshold
            score_breakdown={"chronology": 0.3, "mechanism": 0.5, "scaffold": 0.4},
            provenance=Provenance.auto,
        )

        # Create two overrides for drug_a
        overrides = [
            ManualOverride(
                override_id="override-006",
                drug_id="drug_b",
                action=OverrideAction.force_include,
                rationale="Important relationship",
                curator="curator@drugtree.org",
            ),
            ManualOverride(
                override_id="override-007",
                drug_id="drug_c",
                action=OverrideAction.force_exclude,
                rationale="Incorrect relationship",
                curator="curator@drugtree.org",
            ),
        ]

        # Apply overrides
        result = loader.apply_overrides(
            [edge1, edge2], overrides, confidence_threshold=0.5
        )

        # Assert drug_b edge present (force_include), drug_c edge excluded (force_exclude)
        assert len(result) == 1
        assert result[0].to_drug_id == "drug_b"

    def test_original_edges_not_modified(self):
        """Test that original edge objects are never modified"""
        loader = OverrideLoader()

        # Create edge
        edge = LineageEdge(
            edge_id="drug_b<-drug_a",
            from_drug_id="drug_a",
            to_drug_id="drug_b",
            edge_type=EdgeType.generation_successor,
            confidence=0.7,
            score_breakdown={"chronology": 0.6, "mechanism": 0.8, "scaffold": 0.7},
            provenance=Provenance.auto,
        )

        # Store original values
        original_confidence = edge.confidence
        original_provenance = edge.provenance

        # Create override
        override = ManualOverride(
            override_id="override-008",
            drug_id="drug_b",
            action=OverrideAction.promote_edge,
            target_edge_id="drug_b<-drug_a",
            rationale="Important relationship",
            curator="curator@drugtree.org",
        )

        # Apply overrides
        result = loader.apply_overrides([edge], [override], confidence_threshold=0.5)

        # Assert original edge unchanged
        assert edge.confidence == original_confidence
        assert edge.provenance == original_provenance

        # Assert result edge modified
        assert result[0].confidence == 1.0
        assert result[0].provenance == Provenance.manual

    def test_missing_target_edge_id_warning(self, caplog):
        """Test that missing target_edge_id logs warning for edge-specific actions"""
        loader = OverrideLoader()

        edge = LineageEdge(
            edge_id="drug_b<-drug_a",
            from_drug_id="drug_a",
            to_drug_id="drug_b",
            edge_type=EdgeType.generation_successor,
            confidence=0.7,
            score_breakdown={"chronology": 0.6, "mechanism": 0.8, "scaffold": 0.7},
            provenance=Provenance.auto,
        )

        # Create override with promote_edge but missing target_edge_id
        override = ManualOverride(
            override_id="override-009",
            drug_id="drug_b",
            action=OverrideAction.promote_edge,
            target_edge_id=None,  # Missing
            rationale="Should log warning",
            curator="curator@drugtree.org",
        )

        # Apply overrides (should log warning)
        result = loader.apply_overrides([edge], [override], confidence_threshold=0.5)

        # Assert warning logged
        assert "missing target_edge_id" in caplog.text

        # Assert edge unchanged (override not applied)
        assert len(result) == 1
        assert result[0].confidence == 0.7  # Unchanged

    def test_override_statistics(self, tmp_path):
        """Test override statistics counting"""
        # Create override file with sample data
        override_file = tmp_path / "manual_overrides.json"

        overrides_data = {
            "schema_version": "1.1.0",
            "overrides": [
                {
                    "override_id": "override-001",
                    "drug_id": "drug_a",
                    "action": "force_include",
                    "rationale": "Test",
                    "timestamp": "2024-01-01T00:00:00Z",
                },
                {
                    "override_id": "override-002",
                    "drug_id": "drug_b",
                    "action": "force_exclude",
                    "rationale": "Test",
                    "timestamp": "2024-01-01T00:00:00Z",
                },
                {
                    "override_id": "override-003",
                    "drug_id": "drug_c",
                    "action": "promote_edge",
                    "target_edge_id": "edge-001",
                    "rationale": "Test",
                    "timestamp": "2024-01-01T00:00:00Z",
                },
            ],
        }

        import json

        with open(override_file, "w") as f:
            json.dump(overrides_data, f)

        loader = OverrideLoader(overrides_path=override_file)
        stats = loader.get_override_statistics()

        assert stats["total"] == 3
        assert stats["force_include"] == 1
        assert stats["force_exclude"] == 1
        assert stats["promote_edge"] == 1
        assert stats["demote_edge"] == 0
