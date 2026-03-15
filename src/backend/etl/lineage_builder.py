import json
import hashlib
from typing import List, Dict, Optional, Tuple, Set
from pathlib import Path
from dataclasses import dataclass

try:
    from rdkit import Chem
    from rdkit.Chem import AllChem, DataStructs

    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False

from models.drug import Drug
from models.drug_family import DrugFamily
from models.lineage import LineageEdge, EdgeType, Provenance, RationaleTag


@dataclass
class ScoreBreakdown:
    chronology_score: float
    mechanism_score: float
    scaffold_score: float


class LineageBuilder:
    CONFIDENCE_THRESHOLD = 0.3
    CHRONOLOGY_WEIGHT = 0.3
    MECHANISM_WEIGHT = 0.4
    SCAFFOLD_WEIGHT = 0.3

    SCAFFOLD_SIMILAR_THRESHOLD = 0.7
    SCAFFOLD_DIFFERENT_THRESHOLD = 0.4
    ME_TOO_YEAR_GAP = 5

    def __init__(self):
        self.edges: List[LineageEdge] = []
        self._parent_counts: Dict[str, int] = {}

    def build_edges(
        self, drugs: List[Drug], families: List[DrugFamily]
    ) -> List[LineageEdge]:
        self.edges = []
        self._parent_counts = {}

        drug_by_id = {d.id: d for d in drugs}
        family_by_drug: Dict[str, List[DrugFamily]] = {}

        for family in families:
            for drug_id in family.member_drug_ids:
                if drug_id not in family_by_drug:
                    family_by_drug[drug_id] = []
                family_by_drug[drug_id].append(family)

        for family in families:
            if len(family.member_drug_ids) < 2:
                continue

            members = [
                drug_by_id[did] for did in family.member_drug_ids if did in drug_by_id
            ]
            members_with_year = [
                (m, m.year_approved) for m in members if m.year_approved is not None
            ]
            members_with_year.sort(key=lambda x: x[1])

            if len(members_with_year) < 2:
                continue

            first_drug = members_with_year[0][0] if members_with_year else None

            for i in range(len(members_with_year)):
                for j in range(i + 1, len(members_with_year)):
                    parent, parent_year = members_with_year[i]
                    child, child_year = members_with_year[j]

                    if parent_year == child_year:
                        continue

                    score_breakdown = self._compute_scores(parent, child, family)
                    total_confidence = (
                        score_breakdown.chronology_score * self.CHRONOLOGY_WEIGHT
                        + score_breakdown.mechanism_score * self.MECHANISM_WEIGHT
                        + score_breakdown.scaffold_score * self.SCAFFOLD_WEIGHT
                    )

                    if total_confidence < self.CONFIDENCE_THRESHOLD:
                        continue

                    edge_id = self._generate_edge_id(parent.id, child.id)
                    rationale_tags = self._assign_rationale_tags(
                        parent=parent,
                        child=child,
                        first_drug=first_drug,
                        parent_rank=i,
                        score_breakdown=score_breakdown,
                    )

                    explanation = self._generate_explanation(
                        parent, child, family, score_breakdown, total_confidence
                    )

                    self._parent_counts[child.id] = (
                        self._parent_counts.get(child.id, 0) + 1
                    )

                    edge = LineageEdge(
                        edge_id=edge_id,
                        from_drug_id=parent.id,
                        to_drug_id=child.id,
                        edge_type=EdgeType.follow_on,
                        confidence=round(total_confidence, 3),
                        generation_rationale=rationale_tags,
                        score_breakdown={
                            "chronology_score": round(
                                score_breakdown.chronology_score, 3
                            ),
                            "mechanism_score": round(
                                score_breakdown.mechanism_score, 3
                            ),
                            "scaffold_score": round(score_breakdown.scaffold_score, 3),
                        },
                        provenance=Provenance.auto,
                        explanation=explanation,
                    )

                    self.edges.append(edge)

        for edge in self.edges:
            if self._parent_counts.get(edge.to_drug_id, 0) > 1:
                if "combination" not in edge.generation_rationale:
                    edge.generation_rationale.append("combination")

        return self.edges

    def _assign_rationale_tags(
        self,
        parent: Drug,
        child: Drug,
        first_drug: Optional[Drug],
        parent_rank: int,
        score_breakdown: ScoreBreakdown,
    ) -> List[str]:
        tags: List[str] = []

        if first_drug and parent.id == first_drug.id and parent_rank == 0:
            tags.append("first_in_class")

        year_diff = abs((child.year_approved or 0) - (parent.year_approved or 0))
        same_target = self._check_same_target(parent, child)
        scaffold_similar = (
            score_breakdown.scaffold_score >= self.SCAFFOLD_SIMILAR_THRESHOLD
        )
        scaffold_different = (
            score_breakdown.scaffold_score < self.SCAFFOLD_DIFFERENT_THRESHOLD
        )

        if same_target and scaffold_similar and year_diff < self.ME_TOO_YEAR_GAP:
            if "first_in_class" not in tags:
                tags.append("me_too")
        elif same_target and scaffold_different:
            tags.append("improved_pk")

        if same_target:
            tags.append("same_target")

        if scaffold_similar:
            tags.append("similar_scaffold")

        if parent.year_approved is not None and child.year_approved is not None:
            tags.append("sequential_generation")

        if self._is_prodrug_relationship(parent, child):
            tags.append("prodrug")

        return list(set(tags))

    def _check_same_target(self, parent: Drug, child: Drug) -> bool:
        if not parent.targets or not child.targets:
            return False

        parent_targets = {t.lower() for t in parent.targets}
        child_targets = {t.lower() for t in child.targets}

        return bool(parent_targets & child_targets)

    def _is_prodrug_relationship(self, parent: Drug, child: Drug) -> bool:
        if not parent.name or not child.name:
            return False

        child_lower = child.name.lower()
        prodrug_suffixes = ["-p", " phosphate", " ester", " sodium"]
        for suffix in prodrug_suffixes:
            if suffix in child_lower:
                base_name = parent.name.lower().replace(" ", "")
                child_base = child_lower.split(suffix)[0].replace(" ", "")
                if base_name == child_base:
                    return True

        return False

    def _compute_scores(
        self, parent: Drug, child: Drug, family: DrugFamily
    ) -> ScoreBreakdown:
        chronology_score = self._compute_chronology_score(parent, child)
        mechanism_score = self._compute_mechanism_score(parent, child)
        scaffold_score = self._compute_scaffold_score(parent, child)

        return ScoreBreakdown(
            chronology_score=chronology_score,
            mechanism_score=mechanism_score,
            scaffold_score=scaffold_score,
        )

    def _compute_chronology_score(self, parent: Drug, child: Drug) -> float:
        if parent.year_approved is None or child.year_approved is None:
            return 0.0

        if parent.year_approved < child.year_approved:
            return 1.0
        return 0.0

    def _compute_mechanism_score(self, parent: Drug, child: Drug) -> float:
        if not parent.atc_code or not child.atc_code:
            return 0.0

        parent_atc = parent.atc_code.upper()
        child_atc = child.atc_code.upper()

        if len(parent_atc) >= 4 and len(child_atc) >= 4:
            if parent_atc[:4] == child_atc[:4]:
                return 1.0

        if len(parent_atc) >= 3 and len(child_atc) >= 3:
            if parent_atc[:3] == child_atc[:3]:
                return 0.5

        return 0.0

    def _compute_scaffold_score(self, parent: Drug, child: Drug) -> float:
        if not parent.smiles or not child.smiles:
            return 0.0

        if RDKIT_AVAILABLE:
            return self._compute_fingerprint_similarity(parent.smiles, child.smiles)
        else:
            return self._compute_smiles_similarity(parent.smiles, child.smiles)

    def _compute_fingerprint_similarity(self, smiles1: str, smiles2: str) -> float:
        try:
            mol1 = Chem.MolFromSmiles(smiles1)
            mol2 = Chem.MolFromSmiles(smiles2)

            if mol1 is None or mol2 is None:
                return 0.0

            fp1 = AllChem.GetMorganFingerprintAsBitVect(mol1, 2, nBits=2048)
            fp2 = AllChem.GetMorganFingerprintAsBitVect(mol2, 2, nBits=2048)

            return DataStructs.TanimotoSimilarity(fp1, fp2)
        except Exception:
            return 0.0

    def _compute_smiles_similarity(self, smiles1: str, smiles2: str) -> float:
        s1 = set(smiles1.upper())
        s2 = set(smiles2.upper())

        if not s1 or not s2:
            return 0.0

        intersection = len(s1 & s2)
        union = len(s1 | s2)

        if union == 0:
            return 0.0

        return intersection / union

    def _generate_edge_id(self, from_id: str, to_id: str) -> str:
        return f"{from_id}_to_{to_id}"

    def _generate_explanation(
        self,
        parent: Drug,
        child: Drug,
        family: DrugFamily,
        score_breakdown: ScoreBreakdown,
        total_confidence: float,
    ) -> str:
        parts = [
            f"{child.name} ({child.year_approved}) derived from {parent.name} ({parent.year_approved})",
            f"in {family.label}",
        ]

        score_parts = []
        if score_breakdown.chronology_score > 0:
            score_parts.append(f"chronology={score_breakdown.chronology_score:.1f}")
        if score_breakdown.mechanism_score > 0:
            score_parts.append(f"mechanism={score_breakdown.mechanism_score:.1f}")
        if score_breakdown.scaffold_score > 0:
            score_parts.append(f"scaffold={score_breakdown.scaffold_score:.2f}")

        if score_parts:
            parts.append(f"scores: {', '.join(score_parts)}")

        parts.append(f"confidence={total_confidence:.2f}")

        return " | ".join(parts)

    def save_edges(
        self, output_path: str, edges: Optional[List[LineageEdge]] = None
    ) -> None:
        if edges is None:
            edges = self.edges

        data = {
            "version": "1.0.0",
            "total_edges": len(edges),
            "edges": [e.model_dump() for e in edges],
        }

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load_drugs_from_json(cls, json_path: str) -> List[Drug]:
        with open(json_path, "r") as f:
            data = json.load(f)

        drugs_data = data.get("drugs", [])
        return [Drug(**d) for d in drugs_data]

    @classmethod
    def load_families_from_json(cls, json_path: str) -> List[DrugFamily]:
        with open(json_path, "r") as f:
            data = json.load(f)

        families_data = data.get("families", [])
        return [DrugFamily(**f) for f in families_data]
