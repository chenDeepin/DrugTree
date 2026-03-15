"""
DrugTree - DAG Validator

Validates drug lineage graph as a Directed Acyclic Graph (DAG):
1. No cycles (DFS cycle detection)
2. Time-directional (parent.year_approved <= child.year_approved)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Set

from ..models.drug import Drug
from ..models.lineage import LineageEdge


@dataclass
class ValidationResult:
    is_valid: bool
    cycles: List[List[str]] = field(default_factory=list)
    time_violations: List[str] = field(default_factory=list)


class DAGValidator:
    """
    Validates drug lineage graph as a proper DAG.

    Checks:
    1. Acyclicity - no drug can be its own ancestor
    2. Time-directionality - parents must be approved before children
    """

    def validate(
        self, edges: List[LineageEdge], drugs: Dict[str, Drug]
    ) -> ValidationResult:
        result = ValidationResult(is_valid=True)

        graph = self._build_adjacency_list(edges)
        cycles = self._detect_cycles(graph)
        if cycles:
            result.is_valid = False
            result.cycles = cycles

        violations = self._check_time_directionality(edges, drugs)
        if violations:
            result.is_valid = False
            result.time_violations = violations

        return result

    def _build_adjacency_list(self, edges: List[LineageEdge]) -> Dict[str, List[str]]:
        graph: Dict[str, List[str]] = {}
        for edge in edges:
            if edge.from_drug_id not in graph:
                graph[edge.from_drug_id] = []
            graph[edge.from_drug_id].append(edge.to_drug_id)

            if edge.to_drug_id not in graph:
                graph[edge.to_drug_id] = []
        return graph

    def _detect_cycles(self, graph: Dict[str, List[str]]) -> List[List[str]]:
        cycles: List[List[str]] = []
        visited: Set[str] = set()
        rec_stack: Set[str] = set()
        path: List[str] = []

        for node in graph:
            if node not in visited:
                cycle = self._dfs_cycle(node, graph, visited, rec_stack, path)
                if cycle:
                    cycles.append(cycle)

        return cycles

    def _dfs_cycle(
        self,
        node: str,
        graph: Dict[str, List[str]],
        visited: Set[str],
        rec_stack: Set[str],
        path: List[str],
    ) -> List[str]:
        visited.add(node)
        rec_stack.add(node)
        path.append(node)

        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                cycle = self._dfs_cycle(neighbor, graph, visited, rec_stack, path)
                if cycle:
                    return cycle
            elif neighbor in rec_stack:
                cycle_start = path.index(neighbor)
                return path[cycle_start:] + [neighbor]

        path.pop()
        rec_stack.remove(node)
        return []

    def _check_time_directionality(
        self, edges: List[LineageEdge], drugs: Dict[str, Drug]
    ) -> List[str]:
        violations: List[str] = []

        for edge in edges:
            parent = drugs.get(edge.from_drug_id)
            child = drugs.get(edge.to_drug_id)

            if parent and child:
                if parent.year_approved and child.year_approved:
                    if parent.year_approved > child.year_approved:
                        violations.append(edge.edge_id)

        return violations
