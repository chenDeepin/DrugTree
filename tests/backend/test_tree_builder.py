import pytest
from typing import List

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from backend.services.tree_builder import (
    TreeBuilder,
    TreeNode,
    TreeLink,
    GenealogyTree,
)
from backend.models.lineage import LineageEdge, EdgeType, Provenance


def create_test_edge(
    from_drug: str,
    to_drug: str,
    confidence: float = 0.8,
    edge_type: EdgeType = EdgeType.generation_successor,
) -> LineageEdge:
    return LineageEdge(
        edge_id=f"{from_drug}_to_{to_drug}",
        from_drug_id=from_drug,
        to_drug_id=to_drug,
        edge_type=edge_type,
        confidence=confidence,
        generation_rationale=["sequential_generation"],
        score_breakdown={
            "chronology_score": confidence,
            "mechanism_score": confidence,
            "scaffold_score": confidence,
        },
        provenance=Provenance.auto,
    )


class TestTreeNode:
    def test_tree_node_creation(self):
        node = TreeNode(id="test", name="Test Drug", depth=0)

        assert node.id == "test"
        assert node.name == "Test Drug"
        assert node.depth == 0
        assert node.children == []
        assert node.parent_ids == []
        assert node.primary_parent_id is None

    def test_tree_node_with_children(self):
        child = TreeNode(id="child", name="Child", depth=1)
        parent = TreeNode(
            id="parent",
            name="Parent",
            depth=0,
            children=[child],
        )

        assert len(parent.children) == 1
        assert parent.children[0].id == "child"


class TestTreeLink:
    def test_tree_link_creation(self):
        link = TreeLink(
            source="parent",
            target="child",
            confidence=0.85,
            edge_type="generation_successor",
        )

        assert link.source == "parent"
        assert link.target == "child"
        assert link.confidence == 0.85
        assert link.edge_type == "generation_successor"
        assert link.is_cross_link is False

    def test_cross_link(self):
        link = TreeLink(
            source="parent2",
            target="child",
            confidence=0.75,
            edge_type="follow_on",
            is_cross_link=True,
        )

        assert link.is_cross_link is True


class TestGenealogyTree:
    def test_genealogy_tree_creation(self):
        root = TreeNode(id="root", name="Root Drug", depth=0)
        child = TreeNode(id="child", name="Child Drug", depth=1)
        root.children.append(child)

        link = TreeLink(
            source="child",
            target="root",
            confidence=0.9,
            edge_type="generation_successor",
        )

        tree = GenealogyTree(
            root=root,
            nodes=[root, child],
            links=[link],
            cross_links=[],
        )

        assert tree.root.id == "root"
        assert len(tree.nodes) == 2
        assert len(tree.links) == 1
        assert len(tree.cross_links) == 0


class TestTreeBuilder:
    def test_build_simple_linear_tree(self):
        builder = TreeBuilder()

        edges = [
            create_test_edge("drug_gen1", "drug_gen2", 0.9),
            create_test_edge("drug_gen2", "drug_gen3", 0.85),
        ]

        tree = builder.build_genealogy_tree("drug_gen3", edges)

        assert tree.root.id == "drug_gen3"
        assert len(tree.nodes) == 3
        assert tree.root.depth == 0

    def test_build_tree_with_confidence_threshold(self):
        builder = TreeBuilder()

        edges = [
            create_test_edge("parent1", "child", 0.9),
            create_test_edge("parent2", "child", 0.3),
        ]

        tree_high = builder.build_genealogy_tree("child", edges, threshold=0.5)
        assert len(tree_high.nodes) == 2

        tree_low = builder.build_genealogy_tree("child", edges, threshold=0.2)
        assert len(tree_low.nodes) == 3

    def test_build_tree_max_depth(self):
        builder = TreeBuilder()
        builder.MAX_DEPTH = 3

        edges = [create_test_edge(f"gen{i}", f"gen{i + 1}") for i in range(5)]

        tree = builder.build_genealogy_tree("gen5", edges)

        max_depth = max(node.depth for node in tree.nodes)
        assert max_depth <= builder.MAX_DEPTH

    def test_build_tree_handles_multi_parent(self):
        builder = TreeBuilder()

        edges = [
            create_test_edge("parent1", "child", 0.8),
            create_test_edge("parent2", "child", 0.7),
            create_test_edge("grandparent", "parent1", 0.9),
            create_test_edge("grandparent", "parent2", 0.85),
        ]

        tree = builder.build_genealogy_tree("child", edges)

        child_node = next((n for n in tree.nodes if n.id == "child"), None)
        assert child_node is not None

        assert len(tree.cross_links) > 0 or any(
            link.is_cross_link for link in tree.links
        )

    def test_validate_dag_no_cycles(self):
        builder = TreeBuilder()

        edges = [
            create_test_edge("a", "b"),
            create_test_edge("b", "c"),
            create_test_edge("c", "d"),
        ]

        assert builder.validate_dag(edges) is True

    def test_validate_dag_with_cycle(self):
        builder = TreeBuilder()

        edges = [
            create_test_edge("a", "b"),
            create_test_edge("b", "c"),
            create_test_edge("c", "a"),
        ]

        assert builder.validate_dag(edges) is False

    def test_get_tree_statistics(self):
        builder = TreeBuilder()

        edges = [
            create_test_edge("parent", "child", 0.85),
        ]

        tree = builder.build_genealogy_tree("child", edges)
        stats = builder.get_tree_statistics(tree)

        assert stats["total_nodes"] == 2
        assert stats["total_generations"] == 2
        assert stats["total_links"] == 1
        assert 0.0 <= stats["avg_confidence"] <= 1.0

    def test_build_tree_raises_for_unknown_drug(self):
        builder = TreeBuilder()

        edges = [
            create_test_edge("a", "b"),
        ]

        with pytest.raises(ValueError) as exc_info:
            builder.build_genealogy_tree("unknown", edges)

        assert "no lineage data" in str(exc_info.value).lower()

    def test_build_tree_empty_edges(self):
        builder = TreeBuilder()

        with pytest.raises(ValueError):
            builder.build_genealogy_tree("any_drug", [])

    def test_tree_node_depth_increases(self):
        builder = TreeBuilder()

        edges = [
            create_test_edge("gen1", "gen2"),
            create_test_edge("gen2", "gen3"),
            create_test_edge("gen3", "gen4"),
        ]

        tree = builder.build_genealogy_tree("gen4", edges)

        depths = sorted([node.depth for node in tree.nodes])
        assert depths == [0, 1, 2, 3]

    def test_build_tree_preserves_edge_types(self):
        builder = TreeBuilder()

        edges = [
            create_test_edge("parent", "child", 0.8, EdgeType.follow_on),
            create_test_edge(
                "grandparent", "parent", 0.9, EdgeType.generation_successor
            ),
        ]

        tree = builder.build_genealogy_tree("child", edges)

        assert len(tree.links) == 2
        edge_types = {link.edge_type for link in tree.links}
        assert "follow_on" in edge_types or "generation_successor" in edge_types
