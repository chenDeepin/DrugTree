#!/usr/bin/env python3
"""
Category V Re-classification Processor

Processes drugs in ATC Category V (Various) and attempts to re-classify them
into more specific ATC categories using indication analysis and results from
other batch processors.

Usage:
    python -m src.backend.etl.reclassify_category_v [--dry-run]

Features:
- Uses indication text analysis for classification
- Incorporates results from ChEMBL/KEGG/PubChem lookups
- Respects confidence thresholds (only moves with >= 0.7 confidence)
- Generates detailed re-classification report
- Does NOT modify the 61 curated drugs
"""

import argparse
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Paths
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DRUGS_FILE = DATA_DIR / "drugs.json"
CHECKPOINT_DIR = DATA_DIR / "checkpoints"
EVIDENCE_DIR = PROJECT_ROOT / ".sisyphus" / "evidence"
REPORTS_DIR = DATA_DIR / "reports"
CURATED_DRUGS_FILE = PROJECT_ROOT / "src" / "frontend" / "data" / "drugs-full.json"

# Curated drug IDs (from drugs-full.json) - DO NOT MODIFY THESE
CURATED_DRUG_IDS: set = set()

# ATC Category keywords for classification
ATC_KEYWORDS = {
    "A": {
        "name": "Alimentary tract & metabolism",
        "keywords": [
            "diabetes",
            "insulin",
            "glucose",
            "obesity",
            "weight",
            "gastric",
            "stomach",
            "ulcer",
            "acid",
            "reflux",
            "bowel",
            "constipation",
            "diarrhea",
            "laxative",
            "digestive",
            "gastrointestinal",
            "appetite",
            "cholesterol",
            "lipid",
            "statin",
            "fibrate",
            "vitamin",
            "mineral",
            "anemia",
            "iron",
            "b12",
            "folate",
        ],
    },
    "B": {
        "name": "Blood & blood-forming organs",
        "keywords": [
            "anticoagulant",
            "coagulation",
            "clotting",
            "thrombin",
            "platelet",
            "hemorrhage",
            "bleeding",
            "anemia",
            "hemoglobin",
            "blood",
            "plasma",
            "factor",
            "hemophilia",
            "thrombosis",
            "embolism",
            "dvt",
            "antithrombotic",
        ],
    },
    "C": {
        "name": "Cardiovascular system",
        "keywords": [
            "cardiac",
            "heart",
            "hypertension",
            "blood pressure",
            "angina",
            "arrhythmia",
            "atrial",
            "ventricular",
            "heart failure",
            "cardiomyopathy",
            "coronary",
            "beta blocker",
            "ace inhibitor",
            "diuretic",
            "vasodilator",
            "antianginal",
            "antiarrhythmic",
            "cardiotonic",
            "lipid lowering",
            "cholesterol",
            "triglyceride",
        ],
    },
    "D": {
        "name": "Dermatologicals",
        "keywords": [
            "skin",
            "dermatitis",
            "eczema",
            "psoriasis",
            "acne",
            "topical",
            "cream",
            "ointment",
            "lotion",
            "dermal",
            "cutaneous",
            "epidermal",
            "wart",
            "fungal skin",
            "alopecia",
            "hair",
            "nail",
            "sunscreen",
        ],
    },
    "G": {
        "name": "Genito-urinary system & sex hormones",
        "keywords": [
            "urinary",
            "bladder",
            "kidney",
            "renal",
            "urination",
            "incontinence",
            "diuretic",
            "gout",
            "uric acid",
            "contraceptive",
            "fertility",
            "erectile",
            "prostate",
            "testosterone",
            "estrogen",
            "hormone replacement",
            "menstrual",
            "menopause",
            "ovulation",
        ],
    },
    "H": {
        "name": "Systemic hormonal preparations",
        "keywords": [
            "thyroid",
            "cortisol",
            "steroid",
            "glucocorticoid",
            "adrenal",
            "pituitary",
            "growth hormone",
            "insulin",
            "hormone",
            "endocrine",
            "hormone replacement",
            "corticosteroid",
            "mineralocorticoid",
        ],
    },
    "J": {
        "name": "Antiinfectives for systemic use",
        "keywords": [
            "antibiotic",
            "antibacterial",
            "antimicrobial",
            "bacterial",
            "infection",
            "septic",
            "bacteremia",
            "penicillin",
            "cephalosporin",
            "macrolide",
            "quinolone",
            "tetracycline",
            "sulfonamide",
            "antiviral",
            "virus",
            "hiv",
            "influenza",
            "hepatitis",
            "herpes",
            "antifungal",
            "fungal",
            "candida",
            "yeast",
            "antiparasitic",
            "malaria",
            "antimycobacterial",
            "tb",
        ],
    },
    "L": {
        "name": "Antineoplastic & immunomodulating agents",
        "keywords": [
            "cancer",
            "tumor",
            "oncology",
            "chemotherapy",
            "antineoplastic",
            "cytotoxic",
            "leukemia",
            "lymphoma",
            "carcinoma",
            "melanoma",
            "sarcoma",
            "metastatic",
            "immunotherapy",
            "checkpoint inhibitor",
            "monoclonal",
            "immunomodulator",
            "immunosuppressant",
        ],
    },
    "M": {
        "name": "Musculo-skeletal system",
        "keywords": [
            "muscle",
            "bone",
            "joint",
            "arthritis",
            "rheumatoid",
            "osteoarthritis",
            "gout",
            "ostoporosis",
            "calcium",
            "musculoskeletal",
            "nsaid",
            "anti-inflammatory",
            "analgesic",
            "pain",
            "spasm",
            "relaxant",
        ],
    },
    "N": {
        "name": "Nervous system",
        "keywords": [
            "nervous",
            "neurological",
            "brain",
            "cerebral",
            "epilepsy",
            "seizure",
            "anticonvulsant",
            "antiepileptic",
            "parkinson",
            "alzheimer",
            "dementia",
            "neurodegenerative",
            "antidepressant",
            "anxiety",
            "antipsychotic",
            "schizophrenia",
            "mood stabilizer",
            "bipolar",
            "adhd",
            "narcolepsy",
            "analgesic",
            "opioid",
            "migraine",
            "headache",
            "anesthetic",
            "sedative",
            "hypnotic",
        ],
    },
    "P": {
        "name": "Antiparasitic products, insecticides & repellents",
        "keywords": [
            "parasite",
            "antiparasitic",
            "anthelmintic",
            "worm",
            "malaria",
            "antimalarial",
            "protozoal",
            "amebic",
            "insecticide",
            "repellent",
            "scabies",
            "lice",
            "antihelminthic",
            "nematode",
            "cestode",
        ],
    },
    "R": {
        "name": "Respiratory system",
        "keywords": [
            "respiratory",
            "lung",
            "pulmonary",
            "breathing",
            "asthma",
            "copd",
            "bronchitis",
            "bronchodilator",
            "cough",
            "expectorant",
            "mucolytic",
            "decongestant",
            "antihistamine",
            "allergy",
            "rhinitis",
            "sinus",
            "nasal",
            "throat",
            "pharyngeal",
        ],
    },
    "S": {
        "name": "Sensory organs",
        "keywords": [
            "eye",
            "ophthalmic",
            "ocular",
            "vision",
            "glaucoma",
            "conjunctivitis",
            "cataract",
            "retinal",
            "corneal",
            "ear",
            "otic",
            "hearing",
            "tinnitus",
            "vertigo",
        ],
    },
    "V": {
        "name": "Various",
        "keywords": [
            "various",
            "miscellaneous",
            "other",
            "general",
            "contrast media",
            "diagnostic",
            "imaging",
            "dialysis",
            "plasma substitute",
            "blood substitute",
        ],
    },
}


def load_curated_drug_ids() -> set:
    """Load the 61 curated drug IDs that should not be modified."""
    global CURATED_DRUG_IDS

    if CURATED_DRUG_IDS:
        return CURATED_DRUG_IDS

    if CURATED_DRUGS_FILE.exists():
        with open(CURATED_DRUGS_FILE, "r") as f:
            data = json.load(f)
            drugs = data.get("drugs", data) if isinstance(data, dict) else data
            CURATED_DRUG_IDS = {d.get("id") for d in drugs if d.get("id")}

    return CURATED_DRUG_IDS


class CategoryVReclassifier:
    """
    Re-classifies drugs in ATC Category V into more specific categories.

    Features:
    - Indication text analysis
    - Incorporates results from other batch processors
    - Confidence scoring
    - Preserves curated drugs
    """

    def __init__(self):
        self.curated_ids = load_curated_drug_ids()

        # Statistics
        self.stats = {
            "total_v_drugs": 0,
            "curated_skipped": 0,
            "reclassified": 0,
            "unchanged": 0,
            "low_confidence": 0,
        }

        # Results
        self.results: Dict[str, Dict] = {}

    def analyze_indication(self, indication: Optional[str]) -> List[Tuple[str, float]]:
        """
        Analyze indication text to determine best ATC category.

        Returns:
            List of (category, confidence) tuples sorted by confidence
        """
        if not indication:
            return []

        indication_lower = indication.lower()
        scores: Dict[str, float] = {}

        for category, data in ATC_KEYWORDS.items():
            score = 0.0
            matched_keywords = []

            for keyword in data["keywords"]:
                if keyword.lower() in indication_lower:
                    # Exact match scores higher
                    score += 0.3
                    matched_keywords.append(keyword)

            if score > 0:
                # Normalize score based on number of keyword hits
                scores[category] = min(score / 3.0, 1.0)

        # Sort by score
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_scores

    def reclassify_drug(
        self,
        drug: Dict,
        chembl_results: Optional[Dict] = None,
        kegg_results: Optional[Dict] = None,
        pubchem_results: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Re-classify a single drug from Category V.

        Args:
            drug: Drug dictionary
            chembl_results: Results from ChEMBL batch processor
            kegg_results: Results from KEGG batch processor
            pubchem_results: Results from PubChem batch processor

        Returns:
            Dict with re-classification details
        """
        drug_id = drug.get("id")
        drug_name = drug.get("name", "")

        result = {
            "drug_id": drug_id,
            "drug_name": drug_name,
            "old_atc": drug.get("atc_code"),
            "old_category": drug.get("atc_category"),
            "new_atc": None,
            "new_category": None,
            "confidence": None,
            "source": None,
            "reason": None,
            "is_curated": drug_id in self.curated_ids,
        }

        # Skip curated drugs
        if drug_id in self.curated_ids:
            result["reason"] = "Curated drug - not modified"
            self.stats["curated_skipped"] += 1
            return result

        # Priority 1: Use external API results if available with high confidence
        for source_name, source_results, source_conf in [
            ("kegg", kegg_results, 1.0),
            ("chembl", chembl_results, 0.9),
            ("pubchem", pubchem_results, 0.8),
        ]:
            if source_results and drug_id in source_results:
                source_data = source_results[drug_id]
                if (
                    source_data.get("atc_code")
                    and source_data.get("confidence", 0) >= 0.7
                ):
                    result["new_atc"] = source_data["atc_code"]
                    result["new_category"] = source_data["atc_category"]
                    result["confidence"] = source_data["confidence"]
                    result["source"] = source_name
                    result["reason"] = f"From {source_name} API lookup"
                    return result

        # Priority 2: Analyze indication text
        indication = drug.get("indication", "")
        category_scores = self.analyze_indication(indication)

        if category_scores:
            best_category, best_score = category_scores[0]

            # Only reclassify if confidence is >= 0.7
            if best_score >= 0.7:
                result["new_category"] = best_category
                # Generate a placeholder ATC code for new category
                result["new_atc"] = f"{best_category}99XX99"
                result["confidence"] = best_score
                result["source"] = "indication_analysis"
                result["reason"] = (
                    f"Based on indication analysis (score: {best_score:.2f})"
                )
                return result
            else:
                result["reason"] = (
                    f"Indication analysis too weak (best score: {best_score:.2f})"
                )
                self.stats["low_confidence"] += 1
        else:
            result["reason"] = "No indication or no keywords matched"
            self.stats["unchanged"] += 1

        return result

    def process_batch(
        self,
        drugs: List[Dict],
        chembl_results: Optional[Dict] = None,
        kegg_results: Optional[Dict] = None,
        pubchem_results: Optional[Dict] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Process all drugs in Category V for re-classification.

        Args:
            drugs: List of all drugs
            chembl_results: Results from ChEMBL batch processor
            kegg_results: Results from KEGG batch processor
            pubchem_results: Results from PubChem batch processor
            dry_run: If True, don't save results

        Returns:
            Statistics dictionary
        """
        print(f"\n{'=' * 60}")
        print("Category V Re-classification Processor")
        print(f"{'=' * 60}")
        print(f"Dry run: {dry_run}")

        # Filter to Category V drugs only
        v_drugs = [d for d in drugs if d.get("atc_category") == "V"]
        self.stats["total_v_drugs"] = len(v_drugs)
        print(f"Total Category V drugs: {len(v_drugs)}")
        print(f"Curated drugs to skip: {len(self.curated_ids)}")

        start_time = datetime.utcnow()

        for i, drug in enumerate(v_drugs):
            if (i + 1) % 100 == 0:
                print(f"  Progress: {i + 1}/{len(v_drugs)}")

            result = self.reclassify_drug(
                drug, chembl_results, kegg_results, pubchem_results
            )
            self.results[result["drug_id"]] = result

            if result["new_category"]:
                self.stats["reclassified"] += 1

        elapsed = (datetime.utcnow() - start_time).total_seconds()

        print(f"\n{'=' * 60}")
        print("Re-classification Complete")
        print(f"{'=' * 60}")
        print(f"Total V drugs: {self.stats['total_v_drugs']}")
        print(f"Curated (skipped): {self.stats['curated_skipped']}")
        print(f"Re-classified: {self.stats['reclassified']}")
        print(f"  - Low confidence: {self.stats['low_confidence']}")
        print(f"Unchanged: {self.stats['unchanged']}")
        print(f"Elapsed: {elapsed:.1f}s")

        # Calculate reduction percentage
        reclassifiable = self.stats["total_v_drugs"] - self.stats["curated_skipped"]
        if reclassifiable > 0:
            reduction_pct = (self.stats["reclassified"] / reclassifiable) * 100
            print(f"\nV Category Reduction: {reduction_pct:.1f}%")
            if reduction_pct >= 30:
                print("✅ Target achieved: ≥30% reduction")
            else:
                print(f"⚠️ Target not met: {30 - reduction_pct:.1f}% more needed")

        return self.stats

    def generate_report(self, drugs: List[Dict]) -> Dict[str, Any]:
        """Generate detailed re-classification report."""
        report = {
            "timestamp": datetime.utcnow().isoformat(),
            "summary": self.stats,
            "category_distribution": {},
            "confidence_distribution": {},
            "drugs_reclassified": [],
        }

        # Analyze results
        new_categories = Counter()
        confidences = Counter()
        reclassified_drugs = []

        for drug_id, result in self.results.items():
            if result.get("new_category"):
                new_categories[result["new_category"]] += 1
                conf = result.get("confidence", 0)
                conf_key = f"{conf:.1f}" if conf else "none"
                confidences[conf_key] += 1

                # Find drug details
                drug = next((d for d in drugs if d.get("id") == drug_id), None)
                if drug:
                    reclassified_drugs.append(
                        {
                            "id": drug_id,
                            "name": drug.get("name"),
                            "old_category": result["old_category"],
                            "new_category": result["new_category"],
                            "old_atc": result["old_atc"],
                            "new_atc": result["new_atc"],
                            "confidence": conf,
                            "source": result["source"],
                            "reason": result["reason"],
                            "indication": drug.get("indication"),
                        }
                    )

        report["category_distribution"] = dict(new_categories)
        report["confidence_distribution"] = dict(confidences)
        report["drugs_reclassified"] = sorted(
            reclassified_drugs, key=lambda x: x["confidence"] or 0, reverse=True
        )[:200]

        return report


def load_drugs() -> List[Dict]:
    """Load drugs from JSON file."""
    with open(DRUGS_FILE, "r") as f:
        data = json.load(f)
        if isinstance(data, dict) and "drugs" in data:
            return data["drugs"]
        elif isinstance(data, list):
            return data
        else:
            raise ValueError(f"Invalid drugs.json format")


def load_checkpoint_results(checkpoint_file: Path) -> Optional[Dict]:
    """Load results from a checkpoint file."""
    if checkpoint_file.exists():
        with open(checkpoint_file, "r") as f:
            data = json.load(f)
            return data.get("results", {})
    return None


def main():
    parser = argparse.ArgumentParser(description="Category V Re-classification")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print(f"Loading drugs from {DRUGS_FILE}...")
    drugs = load_drugs()
    print(f"Total drugs: {len(drugs)}")

    # Load curated drug IDs
    curated_ids = load_curated_drug_ids()
    print(f"Curated drugs: {len(curated_ids)}")

    # Count Category V drugs
    v_drugs = [d for d in drugs if d.get("atc_category") == "V"]
    print(f"Category V drugs: {len(v_drugs)}")

    # Load results from other batch processors
    print("\nLoading results from other batch processors...")
    chembl_results = load_checkpoint_results(
        CHECKPOINT_DIR / "atc_chembl_checkpoint.json"
    )
    kegg_results = load_checkpoint_results(CHECKPOINT_DIR / "atc_kegg_checkpoint.json")
    pubchem_results = load_checkpoint_results(
        CHECKPOINT_DIR / "atc_pubchem_checkpoint.json"
    )

    if chembl_results:
        print(f"  ChEMBL results: {len(chembl_results)} drugs")
    if kegg_results:
        print(f"  KEGG results: {len(kegg_results)} drugs")
    if pubchem_results:
        print(f"  PubChem results: {len(pubchem_results)} drugs")

    # Run re-classification
    reclassifier = CategoryVReclassifier()
    stats = reclassifier.process_batch(
        drugs, chembl_results, kegg_results, pubchem_results, dry_run=args.dry_run
    )

    if not args.dry_run:
        report = reclassifier.generate_report(drugs)
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        report_file = (
            REPORTS_DIR
            / f"category_v_reclassification_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        )
        with open(report_file, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\nReport saved to {report_file}")

        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        evidence_file = EVIDENCE_DIR / "task-15-category-v-reclassification.log"
        with open(evidence_file, "w") as f:
            f.write("Category V Re-classification Results\n")
            f.write(f"{'=' * 60}\n")
            f.write(f"Timestamp: {datetime.utcnow().isoformat()}\n")
            f.write(f"Total V drugs: {stats['total_v_drugs']}\n")
            f.write(f"Re-classified: {stats['reclassified']}\n")
            f.write(f"Low confidence: {stats['low_confidence']}\n")
            f.write(f"Unchanged: {stats['unchanged']}\n")
            f.write(f"Curated skipped: {stats['curated_skipped']}\n")
        print(f"Evidence saved to {evidence_file}")


if __name__ == "__main__":
    main()
