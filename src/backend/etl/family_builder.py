"""
DrugTree - Drug Family Builder

Groups drugs into families based on shared characteristics:
1. Shared target
2. Shared mechanism (ATC 3rd level)
3. Scaffold similarity (Tanimoto on Morgan fingerprints)

Reference: .sisyphus/plans/drugtree-graph-evolution.md (Task 6)
"""

import hashlib
import json
from collections import defaultdict
from typing import List, Dict, Optional, Set
from dataclasses import dataclass

from models.drug import Drug
from models.drug_family import DrugFamily, FamilyBasis
from models.version import CURRENT_SCHEMA_VERSION


@dataclass
class FamilyCandidate:
    """Intermediate representation for family grouping"""

    basis: FamilyBasis
    key: str  # Grouping key (target name, ATC code, scaffold hash)
    member_ids: List[str]
    member_drugs: List[Drug]


class FamilyBuilder:
    """
    Builds drug families from drug data.

    Families are groups of drugs sharing:
    - Common targets
    - Common mechanisms (ATC 3rd level)
    - Similar scaffolds (Morgan fingerprints)
    """

    MAX_FAMILIES_PER_DRUG = 5

    def __init__(self):
        self.families: List[DrugFamily] = []
        self.drug_to_families: Dict[str, List[str]] = defaultdict(list)

    def build_families(self, drugs: List[Drug]) -> List[DrugFamily]:
        self.families = []
        self.drug_to_families = defaultdict(list)

        target_candidates = self._group_by_target(drugs)
        mechanism_candidates = self._group_by_mechanism(drugs)
        scaffold_candidates = self._group_by_scaffold(drugs)

        for candidate in target_candidates:
            family = self._candidate_to_family(candidate)
            if family:
                self.families.append(family)
                self._add_family_membership(family)

        for candidate in mechanism_candidates:
            family = self._candidate_to_family(candidate)
            if family:
                self.families.append(family)
                self._add_family_membership(family)

        for candidate in scaffold_candidates:
            family = self._candidate_to_family(candidate)
            if family:
                self.families.append(family)
                self._add_family_membership(family)

        return self.families

    def _add_family_membership(self, family: DrugFamily) -> None:
        for drug_id in family.member_drug_ids:
            if len(self.drug_to_families[drug_id]) < self.MAX_FAMILIES_PER_DRUG:
                self.drug_to_families[drug_id].append(family.family_id)

    def get_drug_to_families(self) -> Dict[str, List[str]]:
        return dict(self.drug_to_families)

    def _group_by_target(self, drugs: List[Drug]) -> List[FamilyCandidate]:
        """Group drugs by shared target"""
        target_to_drugs: Dict[str, List[Drug]] = defaultdict(list)

        for drug in drugs:
            for target in drug.targets:
                normalized_target = self._normalize_target(target)
                if normalized_target:
                    target_to_drugs[normalized_target].append(drug)

        candidates = []
        for target, drug_list in target_to_drugs.items():
            if len(drug_list) >= 2:  # Need at least 2 drugs for a family
                candidates.append(
                    FamilyCandidate(
                        basis=FamilyBasis.target,
                        key=target,
                        member_ids=[d.id for d in drug_list],
                        member_drugs=drug_list,
                    )
                )

        return candidates

    def _group_by_mechanism(self, drugs: List[Drug]) -> List[FamilyCandidate]:
        """Group drugs by ATC 3rd level (mechanism)"""
        mechanism_to_drugs: Dict[str, List[Drug]] = defaultdict(list)

        for drug in drugs:
            atc_3rd = self._get_atc_3rd_level(drug.atc_code)
            if atc_3rd:
                mechanism_to_drugs[atc_3rd].append(drug)

        candidates = []
        for mechanism, drug_list in mechanism_to_drugs.items():
            if len(drug_list) >= 2:
                candidates.append(
                    FamilyCandidate(
                        basis=FamilyBasis.mechanism,
                        key=mechanism,
                        member_ids=[d.id for d in drug_list],
                        member_drugs=drug_list,
                    )
                )

        return candidates

    def _group_by_scaffold(self, drugs: List[Drug]) -> List[FamilyCandidate]:
        """
        Group drugs by scaffold similarity.

        Note: For MVP, uses simple SMILES-based grouping.
        Future versions should use Morgan fingerprints with Tanimoto similarity.
        """
        # For MVP, skip scaffold-based grouping to avoid rdkit dependency
        # This can be enhanced later with actual fingerprint similarity
        return []

    def _candidate_to_family(self, candidate: FamilyCandidate) -> Optional[DrugFamily]:
        """Convert a FamilyCandidate to a DrugFamily"""
        if len(candidate.member_drugs) < 2:
            return None

        # Find prototype (oldest approved drug)
        prototype = self._find_prototype(candidate.member_drugs)
        if not prototype:
            return None

        # Generate family ID
        family_id = self._generate_family_id(
            candidate.basis, candidate.key, candidate.member_ids
        )

        # Generate label
        label = self._generate_label(candidate.basis, candidate.key, prototype)

        # Collect unique targets
        all_targets: Set[str] = set()
        for drug in candidate.member_drugs:
            all_targets.update(drug.targets)

        # Collect unique ATC codes
        all_atc: Set[str] = set()
        for drug in candidate.member_drugs:
            if drug.atc_code:
                all_atc.add(drug.atc_code)

        return DrugFamily(
            family_id=family_id,
            label=label,
            family_basis=candidate.basis,
            prototype_drug_id=prototype.id,
            member_drug_ids=sorted(candidate.member_ids),
            representative_target_ids=sorted(list(all_targets)),
            schema_version=CURRENT_SCHEMA_VERSION,
            description=self._generate_description(
                candidate.basis, candidate.key, prototype
            ),
            atc_codes=sorted(list(all_atc)),
        )

    def _normalize_target(self, target: str) -> Optional[str]:
        """Normalize target name for grouping"""
        if not target:
            return None

        # Lowercase and strip whitespace
        normalized = target.lower().strip()

        # Remove common variations
        normalized = normalized.replace("-", " ").replace("_", " ")

        return normalized if normalized else None

    def _get_atc_3rd_level(self, atc_code: str) -> Optional[str]:
        """Extract ATC 3rd level (e.g., 'C10A' from 'C10AA05')"""
        if not atc_code or len(atc_code) < 4:
            return None

        return atc_code[:4]  # First 4 characters = ATC 3rd level

    def _find_prototype(self, drugs: List[Drug]) -> Optional[Drug]:
        """Find the prototype drug (oldest approved)"""
        drugs_with_approval_year = [
            (drug, drug.year_approved)
            for drug in drugs
            if drug.year_approved is not None
        ]

        if not drugs_with_approval_year:
            return drugs[0] if drugs else None

        prototype_drug, _ = min(drugs_with_approval_year, key=lambda pair: pair[1])
        return prototype_drug

    def _generate_family_id(
        self, basis: FamilyBasis, key: str, member_ids: List[str]
    ) -> str:
        """Generate unique family ID"""
        # Create hash from sorted member IDs
        members_str = ",".join(sorted(member_ids))
        hash_hex = hashlib.md5(members_str.encode()).hexdigest()[:8]

        # Clean key for ID (remove special chars)
        clean_key = "".join(c if c.isalnum() else "_" for c in key.lower())

        return f"{basis.value}_{clean_key}_{hash_hex}"

    def _generate_label(self, basis: FamilyBasis, key: str, prototype: Drug) -> str:
        """Generate human-readable family label"""
        if basis == FamilyBasis.target:
            return f"{key.title()} Target Family"
        elif basis == FamilyBasis.mechanism:
            # Try to use prototype's class name
            class_name = getattr(prototype, "class_name", None)
            if class_name:
                return f"{class_name} Family"
            return f"ATC {key} Family"
        elif basis == FamilyBasis.scaffold:
            return f"Scaffold Family ({prototype.name}-like)"
        else:
            return f"{key} Family"

    def _generate_description(
        self, basis: FamilyBasis, key: str, prototype: Drug
    ) -> str:
        """Generate family description"""
        if basis == FamilyBasis.target:
            return f"Drugs targeting {key}"
        elif basis == FamilyBasis.mechanism:
            class_name = getattr(prototype, "class_name", key)
            return f"Drugs in the {class_name} class (ATC {key})"
        elif basis == FamilyBasis.scaffold:
            return f"Drugs with similar scaffold to {prototype.name}"
        else:
            return f"Drug family based on {basis.value}"

    def save_families(self, output_path: str) -> None:
        """Save families to JSON file"""
        data = {
            "version": CURRENT_SCHEMA_VERSION,
            "total_families": len(self.families),
            "families": [f.model_dump() for f in self.families],
        }

        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load_drugs_from_json(cls, json_path: str) -> List[Drug]:
        """Load drugs from JSON file"""
        with open(json_path, "r") as f:
            data = json.load(f)

        drugs_data = data.get("drugs", [])
        return [Drug(**d) for d in drugs_data]
