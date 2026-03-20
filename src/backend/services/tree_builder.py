"""
DrugTree - Tree Projection Service

Converts flat lineage edges into hierarchical tree structures for visualization.
Implements D3-hierarchy stratify pattern with multi-parent handling.

Reference: .sisyphus/plans/drugtree-graph-evolution.md (Task 13)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from ..models.lineage import LineageEdge


@dataclass
class TreeNode:
    """Node in the genealogy tree."""

    id: str
    name: str
    depth: int = 0
    children: List["TreeNode"] = field(default_factory=list)
    parent_ids: List[str] = field(default_factory=list)
    primary_parent_id: Optional[str] = None


@dataclass
class TreeLink:
    """Link between nodes in the tree."""

    source: str
    target: str
    confidence: float
    edge_type: str
    is_cross_link: bool = False  # True for multi-parent relationships


@dataclass
class GenealogyTree:
    """Complete genealogy tree structure."""

    root: TreeNode
    nodes: List[TreeNode]
    links: List[TreeLink]
    cross_links: List[TreeLink]


class TreeBuilder:
    """
    Build hierarchical tree structures from flat lineage edges.

    Uses D3-hierarchy stratify pattern:
    - Root node is the target drug
    - Children are predecessor drugs (drugs it was derived from)
    - Multi-parent drugs create cross_links (not nested)

    Attributes:
        DEFAULT_THRESHOLD: Default confidence threshold (0.5)
        MAX_DEPTH: Maximum tree depth (10 generations)
    """

    DEFAULT_THRESHOLD = 0.5
    MAX_DEPTH = 10

    def build_genealogy_tree(
        self,
        drug_id: str,
        edges: List[LineageEdge],
        threshold: float = DEFAULT_THRESHOLD,
    ) -> GenealogyTree:
        """
        Build a genealogy tree for a specific drug.

        The tree shows the evolutionary history of a drug, with:
        - Root = the target drug
        - Children = predecessor drugs (drugs it was derived from)
        - Cross-links = secondary parent relationships

        Args:
            drug_id: Target drug ID
            edges: List of all lineage edges
            threshold: Minimum confidence to include edge (default 0.5)

        Returns:
            GenealogyTree with root, nodes, links, cross_links

        Raises:
            ValueError: If drug has no lineage data (no edges)
        """
        # Filter edges by confidence threshold
        filtered_edges = [e for e in edges if e.confidence >= threshold]

        # Build adjacency graph
        graph = self._build_graph(filtered_edges)

        # Check if drug exists in graph
        if drug_id not in graph:
            # Check if drug exists at all
            all_drugs = set()
            for edge in filtered_edges:
                all_drugs.add(edge.from_drug_id)
                all_drugs.add(edge.to_drug_id)

            if drug_id not in all_drugs:
                raise ValueError(f"Drug '{drug_id}' has no lineage data")

        # Build tree using BFS from root
        root = self._build_tree(drug_id, graph, filtered_edges)

        # Collect all nodes
        nodes = self._collect_nodes(root)

        # Build links
        links, cross_links = self._build_links(root, filtered_edges)

        return GenealogyTree(
            root=root,
            nodes=nodes,
            links=links,
            cross_links=cross_links,
        )

    def _build_graph(self, edges: List[LineageEdge]) -> Dict[str, List[LineageEdge]]:
        """
        Build adjacency graph from edges.

        Maps each drug to its incoming edges (predecessors).
        """
        graph: Dict[str, List[LineageEdge]] = {}

        for edge in edges:
            # Add incoming edge for target drug
            if edge.to_drug_id not in graph:
                graph[edge.to_drug_id] = []
            graph[edge.to_drug_id].append(edge)

            # Ensure source drug exists in graph (may have no predecessors)
            if edge.from_drug_id not in graph:
                graph[edge.from_drug_id] = []

        return graph

    def _build_tree(
        self,
        root_id: str,
        graph: Dict[str, List[LineageEdge]],
        edges: List[LineageEdge],
    ) -> TreeNode:
        """
        Build tree structure from root using BFS.

        The tree grows "backwards" from the target drug to its predecessors.
        """
        # Track visited nodes to prevent cycles
        visited: Set[str] = set()

        # Create root node
        root = TreeNode(id=root_id, name=root_id, depth=0)

        # BFS queue
        queue: List[tuple[TreeNode, int]] = [(root, 0)]
        visited.add(root_id)

        # Edge lookup
        edge_map = {f"{e.from_drug_id}->{e.to_drug_id}": e for e in edges}

        while queue:
            current_node, depth = queue.pop(0)

            # Check depth limit
            if depth >= self.MAX_DEPTH:
                continue

            # Get predecessor edges (drugs this drug was derived FROM)
            predecessor_edges = graph.get(current_node.id, [])

            for edge in predecessor_edges:
                parent_id = edge.from_drug_id

                # Skip if already visited (prevents cycles and duplicates)
                if parent_id in visited:
                    # This is a multi-parent case - add as cross-link later
                    current_node.parent_ids.append(parent_id)
                    continue

                visited.add(parent_id)

                # Create child node (predecessor drug)
                child_node = TreeNode(
                    id=parent_id,
                    name=parent_id,
                    depth=depth + 1,
                    parent_ids=[current_node.id],
                    primary_parent_id=current_node.id,
                )

                current_node.children.append(child_node)
                queue.append((child_node, depth + 1))

        return root

    def _collect_nodes(self, root: TreeNode) -> List[TreeNode]:
        """Collect all nodes in tree using DFS."""
        nodes: List[TreeNode] = []

        def dfs(node: TreeNode):
            nodes.append(node)
            for child in node.children:
                dfs(child)

        dfs(root)
        return nodes

    def _build_links(
        self, root: TreeNode, edges: List[LineageEdge]
    ) -> tuple[List[TreeLink], List[TreeLink]]:
        """
        Build links between nodes.

        Returns:
            Tuple of (primary_links, cross_links)
        """
        links: List[TreeLink] = []
        cross_links: List[TreeLink] = []

        # Edge lookup by from->to
        edge_map = {(e.from_drug_id, e.to_drug_id): e for e in edges}

        def process_node(node: TreeNode):
            for child in node.children:
                # Find the edge for this relationship
                edge_key = (child.id, node.id)
                edge = edge_map.get(edge_key)

                if edge:
                    links.append(
                        TreeLink(
                            source=child.id,
                            target=node.id,
                            confidence=edge.confidence,
                            edge_type=edge.edge_type.value
                            if hasattr(edge.edge_type, "value")
                            else str(edge.edge_type),
                            is_cross_link=False,
                        )
                    )
                else:
                    # Create link without edge data
                    links.append(
                        TreeLink(
                            source=child.id,
                            target=node.id,
                            confidence=0.5,
                            edge_type="follow_on",
                            is_cross_link=False,
                        )
                    )

                for secondary_parent_id in child.parent_ids:
                    if secondary_parent_id != child.primary_parent_id:
                        cross_edge_key = (secondary_parent_id, child.id)
                        cross_edge = edge_map.get(cross_edge_key)

                        if cross_edge:
                            cross_links.append(
                                TreeLink(
                                    source=child.id,
                                    target=secondary_parent_id,
                                    confidence=cross_edge.confidence,
                                    edge_type=cross_edge.edge_type.value
                                    if hasattr(cross_edge.edge_type, "value")
                                    else str(cross_edge.edge_type),
                                    is_cross_link=True,
                                )
                            )

                # Recurse
                process_node(child)

        process_node(root)
        return links, cross_links

    def validate_dag(self, edges: List[LineageEdge]) -> bool:
        """
        Validate that edges form a DAG (no cycles).

        Uses Kahn's algorithm for topological sort.

        Args:
            edges: List of lineage edges

        Returns:
            True if DAG (valid), False if cycles exist
        """
        # Build graph and in-degree count
        in_degree: Dict[str, int] = {}
        graph: Dict[str, List[str]] = {}

        for edge in edges:
            # Initialize nodes
            if edge.from_drug_id not in in_degree:
                in_degree[edge.from_drug_id] = 0
            if edge.to_drug_id not in in_degree:
                in_degree[edge.to_drug_id] = 0

            # Add edge
            if edge.from_drug_id not in graph:
                graph[edge.from_drug_id] = []
            graph[edge.from_drug_id].append(edge.to_drug_id)

            # Increment in-degree
            in_degree[edge.to_drug_id] += 1

        # Find all nodes with in-degree 0
        queue = [node for node, degree in in_degree.items() if degree == 0]
        visited_count = 0

        while queue:
            node = queue.pop(0)
            visited_count += 1

            for neighbor in graph.get(node, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # If all nodes visited, it's a DAG
        return visited_count == len(in_degree)

    def get_tree_statistics(self, tree: GenealogyTree) -> Dict[str, any]:
        """
        Calculate statistics for a genealogy tree.

        Args:
            tree: GenealogyTree to analyze

        Returns:
            Dictionary with statistics
        """
        # Calculate max depth
        max_depth = max(node.depth for node in tree.nodes) if tree.nodes else 0

        # Calculate average confidence
        all_links = tree.links + tree.cross_links
        avg_confidence = (
            sum(link.confidence for link in all_links) / len(all_links)
            if all_links
            else 0.0
        )

        return {
            "total_nodes": len(tree.nodes),
            "total_generations": max_depth + 1,  # depth 0 = generation 1
            "total_links": len(tree.links),
            "total_cross_links": len(tree.cross_links),
            "avg_confidence": round(avg_confidence, 3),
        }
