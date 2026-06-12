"""
DrugTree - Graph Index Service

In-memory index for fast lookups of drug families and lineage edges.
Provides O(1) access to nodes, edges, and families.

Reference: .sisyphus/plans/drugtree-graph-evolution.md (Task 17)
"""

import json
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

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


@dataclass(frozen=True)
class GraphSourceStat:
    """Lightweight source fingerprint used to detect ETL graph refreshes."""

    mtime_ns: int
    size: int


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
            drugs_path: Path to canonical drugs.json for node names
        """
        # Default paths relative to project root
        base_path = Path(__file__).parent.parent.parent.parent / "data"
        self.graph_dir = base_path / "graph"
        self.graph_meta_path = self.graph_dir / "graph-meta.json"

        self.families_path = (
            families_path or base_path / "processed" / "drug_families.json"
        )
        self.edges_path = edges_path or base_path / "processed" / "lineage_edges.json"
        self.drugs_path = drugs_path or base_path / "drugs.json"
        self.use_graph_artifacts = (
            families_path is None and edges_path is None and drugs_path is None
        )

        # Index structures
        self._nodes: Dict[str, DrugNode] = {}
        self._edges: Dict[str, LineageEdge] = {}
        self._families: Dict[str, DrugFamily] = {}

        # Edge index by drug ID (for fast lookups)
        self._edges_by_drug: Dict[str, List[str]] = {}
        self._adjacency: Dict[str, Set[str]] = {}

        # Loaded flag
        self._loaded = False
        self._source_signature: Optional[Dict[str, Optional[GraphSourceStat]]] = None

    def _graph_artifact_paths(self) -> Dict[str, Path]:
        return {
            "graph_meta": self.graph_meta_path,
            "graph_drugs": self.graph_dir / "nodes" / "drugs.json",
            "graph_clusters": self.graph_dir / "nodes" / "clusters.json",
            "graph_lineage": self.graph_dir / "edges" / "lineage.json",
        }

    def _fallback_source_paths(self) -> Dict[str, Path]:
        return {
            "families": self.families_path,
            "edges": self.edges_path,
            "drugs": self.drugs_path,
        }

    def _active_source_paths(self) -> Dict[str, Path]:
        graph_paths = self._graph_artifact_paths()
        if self.use_graph_artifacts and all(path.exists() for path in graph_paths.values()):
            return graph_paths
        return self._fallback_source_paths()

    def _collect_source_signature(self) -> Dict[str, Optional[GraphSourceStat]]:
        signature: Dict[str, Optional[GraphSourceStat]] = {}
        for name, path in self._active_source_paths().items():
            if not path.exists():
                signature[name] = None
                continue
            stat = path.stat()
            signature[name] = GraphSourceStat(
                mtime_ns=stat.st_mtime_ns,
                size=stat.st_size,
            )
        return signature

    def _source_changed(self) -> bool:
        if self._source_signature is None:
            return True
        return self._collect_source_signature() != self._source_signature

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()
            return
        if self._source_changed():
            self.refresh()

    def source_version(self) -> str:
        """Return a deterministic version string for the graph source files."""
        self._ensure_loaded()
        signature = self._source_signature or {}
        return "|".join(
            f"{name}:{stat.mtime_ns}:{stat.size}" if stat else f"{name}:missing"
            for name, stat in sorted(signature.items())
        )

    def load(self) -> None:
        """Load all data from JSON files into memory."""
        if self.use_graph_artifacts and self.graph_meta_path.exists():
            self._load_graph_artifacts()
            self._loaded = True
            self._source_signature = self._collect_source_signature()
            return

        self._load_families()
        self._load_edges()
        self._load_drug_names()
        self._loaded = True
        self._source_signature = self._collect_source_signature()

    def _load_graph_artifacts(self) -> None:
        drugs_path = self.graph_dir / "nodes" / "drugs.json"
        clusters_path = self.graph_dir / "nodes" / "clusters.json"
        lineage_path = self.graph_dir / "edges" / "lineage.json"

        if (
            not drugs_path.exists()
            or not clusters_path.exists()
            or not lineage_path.exists()
        ):
            self._load_families()
            self._load_edges()
            self._load_drug_names()
            return

        with open(drugs_path, "r") as f:
            drug_nodes = json.load(f).get("nodes", [])
        for node in drug_nodes:
            extra = node.get("extra", {})
            drug_id = extra.get("id") or node.get("node_id", "").split(":", 1)[-1]
            if not drug_id:
                continue
            self._nodes[str(drug_id)] = DrugNode(
                str(drug_id), str(node.get("label") or drug_id)
            )

        with open(clusters_path, "r") as f:
            cluster_nodes = json.load(f).get("nodes", [])
        for node in cluster_nodes:
            extra = node.get("extra", {})
            if not extra:
                continue
            family = DrugFamily(**extra)
            self._families[family.family_id] = family
            for drug_id in family.member_drug_ids:
                if drug_id not in self._nodes:
                    self._nodes[drug_id] = DrugNode(drug_id)
                self._nodes[drug_id].families.append(family.family_id)

        with open(lineage_path, "r") as f:
            lineage_edges = json.load(f).get("edges", [])
        for artifact in lineage_edges:
            extra = artifact.get("extra", {})
            edge_payload: Dict[str, Any] = (
                dict(extra)
                if isinstance(extra, dict) and extra
                else {
                    "edge_id": artifact["edge_id"],
                    "from_drug_id": artifact["source_id"].split(":", 1)[1],
                    "to_drug_id": artifact["target_id"].split(":", 1)[1],
                    "edge_type": artifact.get("edge_type", "follow_on"),
                    "confidence": artifact.get("confidence", 1.0),
                    "generation_rationale": [],
                    "score_breakdown": {},
                    "provenance": "auto",
                }
            )
            edge = LineageEdge(**edge_payload)
            self._edges[edge.edge_id] = edge

            if edge.from_drug_id not in self._nodes:
                self._nodes[edge.from_drug_id] = DrugNode(edge.from_drug_id)
            if edge.to_drug_id not in self._nodes:
                self._nodes[edge.to_drug_id] = DrugNode(edge.to_drug_id)

            self._nodes[edge.from_drug_id].outgoing_edges.append(edge.edge_id)
            self._nodes[edge.to_drug_id].incoming_edges.append(edge.edge_id)

            for drug_id in [edge.from_drug_id, edge.to_drug_id]:
                if drug_id not in self._edges_by_drug:
                    self._edges_by_drug[drug_id] = []
                if edge.edge_id not in self._edges_by_drug[drug_id]:
                    self._edges_by_drug[drug_id].append(edge.edge_id)

            if edge.from_drug_id not in self._adjacency:
                self._adjacency[edge.from_drug_id] = set()
            if edge.to_drug_id not in self._adjacency:
                self._adjacency[edge.to_drug_id] = set()
            self._adjacency[edge.from_drug_id].add(edge.to_drug_id)
            self._adjacency[edge.to_drug_id].add(edge.from_drug_id)

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

            if edge.from_drug_id not in self._adjacency:
                self._adjacency[edge.from_drug_id] = set()
            if edge.to_drug_id not in self._adjacency:
                self._adjacency[edge.to_drug_id] = set()

            self._adjacency[edge.from_drug_id].add(edge.to_drug_id)
            self._adjacency[edge.to_drug_id].add(edge.from_drug_id)

    def _load_drug_names(self) -> None:
        """Load drug names from canonical drugs.json for better display."""
        if not self.drugs_path.exists():
            # Non-fatal - just skip name enrichment
            return

        with open(self.drugs_path, "r") as f:
            payload = json.load(f)
            drugs = payload.get("drugs", []) if isinstance(payload, dict) else payload

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
        self._adjacency.clear()
        self._loaded = False
        self._source_signature = None
        self.load()

    def get_neighbors(self, drug_id: str) -> List[str]:
        self._ensure_loaded()
        return sorted(self._adjacency.get(drug_id, set()))

    def get_neighborhood(self, drug_id: str, max_hops: int = 1) -> Dict[str, List[str]]:
        self._ensure_loaded()

        if max_hops < 1 or drug_id not in self._nodes:
            return {}

        visited: Set[str] = {drug_id}
        queue = deque([(drug_id, 0)])

        while queue:
            current, depth = queue.popleft()
            if depth >= max_hops:
                continue

            for neighbor in self._adjacency.get(current, set()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, depth + 1))

        return {
            node_id: sorted(self._adjacency.get(node_id, set())) for node_id in visited
        }

    def get_edge_evidence(self, edge_id: str) -> List[Dict[str, Any]]:
        self._ensure_loaded()

        edge = self._edges.get(edge_id)
        if edge is None:
            return []

        return [
            {
                "source": edge.provenance.value,
                "source_type": "curated"
                if edge.provenance.value in {"manual", "curated"}
                else "inferred",
                "confidence": edge.confidence,
                "description": edge.explanation,
                "url": None,
            }
        ]

    def get_subgraph(self, node_ids: List[str]) -> Dict[str, List[str]]:
        self._ensure_loaded()

        node_set = {node_id for node_id in node_ids if node_id in self._nodes}
        return {
            node_id: sorted(
                neighbor
                for neighbor in self._adjacency.get(node_id, set())
                if neighbor in node_set
            )
            for node_id in node_set
        }

    def get_node(self, node_id: str) -> Optional[DrugNode]:
        """
        Get a drug node by ID.

        Args:
            node_id: Drug identifier (e.g., "atorvastatin")

        Returns:
            DrugNode if found, None otherwise
        """
        self._ensure_loaded()
        return self._nodes.get(node_id)

    def get_edges(self, drug_id: str) -> List[LineageEdge]:
        """
        Get all lineage edges for a drug.

        Args:
            drug_id: Drug identifier

        Returns:
            List of LineageEdge objects (both incoming and outgoing)
        """
        self._ensure_loaded()

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
        self._ensure_loaded()

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
        self._ensure_loaded()

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
        self._ensure_loaded()
        return self._families.get(family_id)

    def get_families_for_drug(self, drug_id: str) -> List[DrugFamily]:
        """
        Get all families containing a drug.

        Args:
            drug_id: Drug identifier

        Returns:
            List of DrugFamily objects
        """
        self._ensure_loaded()

        node = self._nodes.get(drug_id)
        if not node:
            return []

        return [self._families[fid] for fid in node.families if fid in self._families]

    def get_all_drugs(self) -> List[str]:
        """Get all drug IDs in the index."""
        self._ensure_loaded()
        return list(self._nodes.keys())

    def get_all_families(self) -> List[str]:
        """Get all family IDs in the index."""
        self._ensure_loaded()
        return list(self._families.keys())

    def get_all_edges(self) -> List[LineageEdge]:
        """Get all lineage edges."""
        self._ensure_loaded()
        return list(self._edges.values())

    @property
    def stats(self) -> Dict[str, int]:
        """Get index statistics."""
        self._ensure_loaded()
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
