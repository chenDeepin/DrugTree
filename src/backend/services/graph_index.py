"""
DrugTree - Graph Index Service

In-memory index for fast lookups of drug families and lineage edges.
Provides O(1) access to nodes, edges, and families.

Reference: .sisyphus/plans/drugtree-graph-evolution.md (Task 17)
"""

import json
from pathlib import Path
from typing import Dict, List, Optional

from ..models.drug_family import DrugFamily
from ..models.lineage import LineageEdge


class DrugNode:
    """Represents a drug node in the graph."""

    def __init__(self, drug_id: str, name: Optional[str] = None):
        self.drug_id = drug_id
        self.name = name or drug_id
        self.families: List[str] = []
        self.outgoing_edges: List[str] = []  # Edge IDs where this drug is the source
        self.incoming_edges: List[str] = []  # Edge IDs where this drug is the target


class GraphIndex:
    """
    In-memory graph index for drug lineage data.

    Loads families and edges from JSON files and provides fast lookups.
    Uses dictionary-based indexing for O(1) access.

    Usage:
        index = GraphIndex()
        index.load()

        # Get a drug node
        node = index.get_node("atorvastatin")

        # Get all edges for a drug
        edges = index.get_edges("atorvastatin")

        # Get a family
        family = index.get_family("statins")

        # Refresh data from files
        index.refresh()
    """

    def __init__(
        self,
        families_path: Optional[Path] = None,
        edges_path: Optional[Path] = None,
        drugs_path: Optional[Path] = None,
    ):
        """
        Initialize GraphIndex with optional custom paths.

        Args:
            families_path: Path to drug_families.json
            edges_path: Path to lineage_edges.json
            drugs_path: Path to drugs-full.json for node names
        """
        # Default paths relative to project root
        base_path = Path(__file__).parent.parent.parent.parent / "data"

        self.families_path = (
            families_path or base_path / "processed" / "drug_families.json"
        )
        self.edges_path = edges_path or base_path / "processed" / "lineage_edges.json"
        self.drugs_path = (
            drugs_path or base_path / "frontend" / "data" / "drugs-full.json"
        )

        # Index structures
        self._nodes: Dict[str, DrugNode] = {}
        self._edges: Dict[str, LineageEdge] = {}
        self._families: Dict[str, DrugFamily] = {}

        # Edge index by drug ID (for fast lookups)
        self._edges_by_drug: Dict[str, List[str]] = {}

        # Loaded flag
        self._loaded = False

    def load(self) -> None:
        """Load all data from JSON files into memory."""
        self._load_families()
        self._load_edges()
        self._load_drug_names()
        self._loaded = True

    def _load_families(self) -> None:
        """Load drug families from JSON file."""
        if not self.families_path.exists():
            raise FileNotFoundError(f"Families file not found: {self.families_path}")

        with open(self.families_path, "r") as f:
            data = json.load(f)

        families = data.get("families", [])

        for family_data in families:
            family = DrugFamily(**family_data)
            self._families[family.family_id] = family

            # Create/update nodes for member drugs
            for drug_id in family.member_drug_ids:
                if drug_id not in self._nodes:
                    self._nodes[drug_id] = DrugNode(drug_id)
                self._nodes[drug_id].families.append(family.family_id)

    def _load_edges(self) -> None:
        """Load lineage edges from JSON file."""
        if not self.edges_path.exists():
            raise FileNotFoundError(f"Edges file not found: {self.edges_path}")

        with open(self.edges_path, "r") as f:
            data = json.load(f)

        edges = data.get("edges", [])

        for edge_data in edges:
            edge = LineageEdge(**edge_data)
            self._edges[edge.edge_id] = edge

            # Create/update nodes for from and to drugs
            if edge.from_drug_id not in self._nodes:
                self._nodes[edge.from_drug_id] = DrugNode(edge.from_drug_id)
            if edge.to_drug_id not in self._nodes:
                self._nodes[edge.to_drug_id] = DrugNode(edge.to_drug_id)

            # Add edge references to nodes
            self._nodes[edge.from_drug_id].outgoing_edges.append(edge.edge_id)
            self._nodes[edge.to_drug_id].incoming_edges.append(edge.edge_id)

            # Update drug edge index
            for drug_id in [edge.from_drug_id, edge.to_drug_id]:
                if drug_id not in self._edges_by_drug:
                    self._edges_by_drug[drug_id] = []
                if edge.edge_id not in self._edges_by_drug[drug_id]:
                    self._edges_by_drug[drug_id].append(edge.edge_id)

    def _load_drug_names(self) -> None:
        """Load drug names from drugs-full.json for better display."""
        if not self.drugs_path.exists():
            # Non-fatal - just skip name enrichment
            return

        with open(self.drugs_path, "r") as f:
            drugs = json.load(f)

        for drug_data in drugs:
            drug_id = drug_data.get("id")
            drug_name = drug_data.get("name")
            if drug_id and drug_name and drug_id in self._nodes:
                self._nodes[drug_id].name = drug_name

    def refresh(self) -> None:
        """Clear all data and reload from files."""
        self._nodes.clear()
        self._edges.clear()
        self._families.clear()
        self._edges_by_drug.clear()
        self._loaded = False
        self.load()

    def get_node(self, node_id: str) -> Optional[DrugNode]:
        """
        Get a drug node by ID.

        Args:
            node_id: Drug identifier (e.g., "atorvastatin")

        Returns:
            DrugNode if found, None otherwise
        """
        if not self._loaded:
            self.load()
        return self._nodes.get(node_id)

    def get_edges(self, drug_id: str) -> List[LineageEdge]:
        """
        Get all lineage edges for a drug.

        Args:
            drug_id: Drug identifier

        Returns:
            List of LineageEdge objects (both incoming and outgoing)
        """
        if not self._loaded:
            self.load()

        edge_ids = self._edges_by_drug.get(drug_id, [])
        return [self._edges[eid] for eid in edge_ids if eid in self._edges]

    def get_outgoing_edges(self, drug_id: str) -> List[LineageEdge]:
        """
        Get outgoing edges (drugs derived from this drug).

        Args:
            drug_id: Drug identifier

        Returns:
            List of LineageEdge where drug_id is the predecessor
        """
        if not self._loaded:
            self.load()

        node = self._nodes.get(drug_id)
        if not node:
            return []

        return [self._edges[eid] for eid in node.outgoing_edges if eid in self._edges]

    def get_incoming_edges(self, drug_id: str) -> List[LineageEdge]:
        """
        Get incoming edges (predecessor drugs).

        Args:
            drug_id: Drug identifier

        Returns:
            List of LineageEdge where drug_id is the successor
        """
        if not self._loaded:
            self.load()

        node = self._nodes.get(drug_id)
        if not node:
            return []

        return [self._edges[eid] for eid in node.incoming_edges if eid in self._edges]

    def get_family(self, family_id: str) -> Optional[DrugFamily]:
        """
        Get a drug family by ID.

        Args:
            family_id: Family identifier

        Returns:
            DrugFamily if found, None otherwise
        """
        if not self._loaded:
            self.load()
        return self._families.get(family_id)

    def get_families_for_drug(self, drug_id: str) -> List[DrugFamily]:
        """
        Get all families containing a drug.

        Args:
            drug_id: Drug identifier

        Returns:
            List of DrugFamily objects
        """
        if not self._loaded:
            self.load()

        node = self._nodes.get(drug_id)
        if not node:
            return []

        return [self._families[fid] for fid in node.families if fid in self._families]

    def get_all_drugs(self) -> List[str]:
        """Get all drug IDs in the index."""
        if not self._loaded:
            self.load()
        return list(self._nodes.keys())

    def get_all_families(self) -> List[str]:
        """Get all family IDs in the index."""
        if not self._loaded:
            self.load()
        return list(self._families.keys())

    def get_all_edges(self) -> List[LineageEdge]:
        """Get all lineage edges."""
        if not self._loaded:
            self.load()
        return list(self._edges.values())

    @property
    def stats(self) -> Dict[str, int]:
        """Get index statistics."""
        if not self._loaded:
            self.load()
        return {
            "total_nodes": len(self._nodes),
            "total_edges": len(self._edges),
            "total_families": len(self._families),
        }


# Singleton instance for app-wide use
_index_instance: Optional[GraphIndex] = None


def get_graph_index() -> GraphIndex:
    """Get or create the singleton GraphIndex instance."""
    global _index_instance
    if _index_instance is None:
        _index_instance = GraphIndex()
    return _index_instance
