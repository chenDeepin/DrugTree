"""
DrugTree - Override Loader

Applies manual curation overrides to auto-generated lineage edges.
Follows precedence contract: manual > curated > auto > fallback

Override Actions:
- force_include: Add edge even if confidence < threshold
- force_exclude: Remove edge even if confidence >= threshold
- promote_edge: Set confidence = 1.0, provenance = manual
- demote_edge: Set confidence = 0.0, provenance = manual

Reference: .sisyphus/plans/drugtree-graph-evolution.md (Task 12)
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from copy import deepcopy

from ..models.override import ManualOverride, OverrideAction
from ..models.lineage import LineageEdge, Provenance

logger = logging.getLogger(__name__)


class OverrideLoader:
    """
    Loads and applies manual curation overrides to lineage edges.

    Precedence Contract: manual > curated > auto > fallback

    All override applications are logged for audit trail.
    Original edge objects are NEVER modified - new list is returned.
    """

    PRECEDENCE_ORDER: Dict[str, int] = {
        "manual": 3,
        "curated": 2,
        "auto": 1,
        "fallback": 0,
    }

    def __init__(self, overrides_path: Optional[Path] = None):
        """
        Initialize OverrideLoader.

        Args:
            overrides_path: Path to manual_overrides.json file.
                           Defaults to data/curated/manual_overrides.json
        """
        if overrides_path is None:
            # Default path
            project_root = Path(__file__).parent.parent.parent.parent
            overrides_path = project_root / "data" / "curated" / "manual_overrides.json"

        self.overrides_path = Path(overrides_path)
        self.overrides: List[ManualOverride] = []
        self._load_overrides()

    def _load_overrides(self) -> None:
        """Load manual overrides from JSON file."""
        if not self.overrides_path.exists():
            logger.info(
                f"Override file not found: {self.overrides_path}. Creating empty file."
            )
            self._create_empty_override_file()
            return

        try:
            with open(self.overrides_path, "r") as f:
                data = json.load(f)

            if "overrides" not in data:
                logger.warning(f"No 'overrides' key in {self.overrides_path}")
                return

            self.overrides = [
                ManualOverride(**override_data) for override_data in data["overrides"]
            ]

            logger.info(
                f"Loaded {len(self.overrides)} manual overrides from {self.overrides_path}"
            )

        except Exception as e:
            logger.error(f"Failed to load overrides from {self.overrides_path}: {e}")
            self.overrides = []

    def _create_empty_override_file(self) -> None:
        """Create empty manual_overrides.json file."""
        self.overrides_path.parent.mkdir(parents=True, exist_ok=True)

        empty_data = {
            "schema_version": "1.1.0",
            "description": "Manual curation overrides for lineage edges",
            "overrides": [],
        }

        with open(self.overrides_path, "w") as f:
            json.dump(empty_data, f, indent=2)

        logger.info(f"Created empty override file: {self.overrides_path}")

    def get_precedence_level(self, provenance: str) -> int:
        """
        Get precedence level for a provenance value.

        Higher number = higher precedence.
        manual (3) > curated (2) > auto (1) > fallback (0)

        Args:
            provenance: Provenance value (auto/curated/manual/fallback)

        Returns:
            Precedence level (0-3)
        """
        return self.PRECEDENCE_ORDER.get(provenance, 0)

    def apply_overrides(
        self,
        edges: List[LineageEdge],
        overrides: Optional[List[ManualOverride]] = None,
        confidence_threshold: float = 0.5,
    ) -> List[LineageEdge]:
        """
        Apply manual overrides to lineage edges.

        This method:
        1. Creates deep copy of edges (never modifies original)
        2. Applies force_include for edges below threshold
        3. Applies force_exclude for edges above threshold
        4. Applies promote_edge to set confidence=1.0
        5. Applies demote_edge to set confidence=0.0
        6. Enforces precedence: manual > curated > auto

        Args:
            edges: List of auto-generated LineageEdge objects
            overrides: List of ManualOverride objects (uses loaded overrides if None)
            confidence_threshold: Minimum confidence to include edge (default 0.5)

        Returns:
            New list of LineageEdge objects with overrides applied
        """
        if overrides is None:
            overrides = self.overrides

        # Deep copy to avoid modifying original edges
        result_edges = [deepcopy(edge) for edge in edges]

        # Track which edges have been overridden (for precedence)
        overridden: Dict[
            str, Tuple[LineageEdge, str]
        ] = {}  # edge_id -> (edge, provenance)

        # Group overrides by drug_id for efficient lookup
        drug_overrides: Dict[str, List[ManualOverride]] = {}
        for override in overrides:
            if override.drug_id not in drug_overrides:
                drug_overrides[override.drug_id] = []
            drug_overrides[override.drug_id].append(override)

        # Apply overrides
        for override in overrides:
            # Handle edge-specific actions (promote_edge, demote_edge)
            if override.action in [
                OverrideAction.promote_edge,
                OverrideAction.demote_edge,
            ]:
                if not override.target_edge_id:
                    logger.warning(
                        f"Override {override.override_id} missing target_edge_id for {override.action}"
                    )
                    continue

                # Find target edge
                target_edge = None
                for edge in result_edges:
                    if edge.edge_id == override.target_edge_id:
                        target_edge = edge
                        break

                if not target_edge:
                    logger.warning(
                        f"Override {override.override_id} target edge not found: {override.target_edge_id}"
                    )
                    continue

                # Check precedence
                current_precedence = self.get_precedence_level(
                    target_edge.provenance.value
                )
                new_precedence = self.get_precedence_level("manual")

                if target_edge.edge_id in overridden:
                    _, previous_provenance = overridden[target_edge.edge_id]
                    current_precedence = self.get_precedence_level(previous_provenance)

                if new_precedence <= current_precedence:
                    logger.info(
                        f"Skip override {override.override_id}: "
                        f"precedence manual ({new_precedence}) <= current ({current_precedence})"
                    )
                    continue

                # Apply action
                if override.action == OverrideAction.promote_edge:
                    target_edge.confidence = 1.0
                    target_edge.provenance = Provenance.manual
                    target_edge.explanation = f"Override: {override.rationale} (curator: {override.curator or 'unknown'})"
                    logger.info(
                        f"Override {override.override_id}: Promoted edge {target_edge.edge_id} to confidence=1.0"
                    )
                    overridden[target_edge.edge_id] = (target_edge, "manual")

                elif override.action == OverrideAction.demote_edge:
                    target_edge.confidence = 0.0
                    target_edge.provenance = Provenance.manual
                    target_edge.explanation = f"Override: {override.rationale} (curator: {override.curator or 'unknown'})"
                    logger.info(
                        f"Override {override.override_id}: Demoted edge {target_edge.edge_id} to confidence=0.0"
                    )
                    overridden[target_edge.edge_id] = (target_edge, "manual")

        # Handle force_include and force_exclude
        # These are drug-level actions, so we need to find all edges involving that drug
        final_edges = []

        for edge in result_edges:
            include_edge = True

            # Check if edge has any overrides
            from_overrides = drug_overrides.get(edge.from_drug_id, [])
            to_overrides = drug_overrides.get(edge.to_drug_id, [])
            all_overrides = from_overrides + to_overrides

            for override in all_overrides:
                # Check precedence
                current_precedence = self.get_precedence_level(edge.provenance.value)
                new_precedence = self.get_precedence_level("manual")

                if edge.edge_id in overridden:
                    _, previous_provenance = overridden[edge.edge_id]
                    current_precedence = self.get_precedence_level(previous_provenance)

                if new_precedence <= current_precedence:
                    continue  # Skip lower precedence override

                # Apply force_include
                if override.action == OverrideAction.force_include:
                    if edge.confidence < confidence_threshold:
                        edge.provenance = Provenance.manual
                        edge.explanation = (
                            f"Override force_include: {override.rationale} "
                            f"(curator: {override.curator or 'unknown'})"
                        )
                        logger.info(
                            f"Override {override.override_id}: Force included edge {edge.edge_id} "
                            f"(confidence was {edge.confidence})"
                        )
                        overridden[edge.edge_id] = (edge, "manual")

                # Apply force_exclude
                elif override.action == OverrideAction.force_exclude:
                    include_edge = False
                    logger.info(
                        f"Override {override.override_id}: Force excluded edge {edge.edge_id} "
                        f"(confidence was {edge.confidence})"
                    )
                    break  # No need to check other overrides

            if include_edge:
                final_edges.append(edge)

        logger.info(
            f"Applied {len(overrides)} overrides: "
            f"{len(edges)} input edges -> {len(final_edges)} output edges"
        )

        return final_edges

    def get_override_statistics(self) -> Dict[str, int]:
        """
        Get statistics about loaded overrides.

        Returns:
            Dict with counts by action type
        """
        stats = {
            "total": len(self.overrides),
            "force_include": 0,
            "force_exclude": 0,
            "promote_edge": 0,
            "demote_edge": 0,
        }

        for override in self.overrides:
            action_key = override.action.value
            if action_key in stats:
                stats[action_key] += 1

        return stats
