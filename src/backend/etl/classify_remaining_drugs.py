#!/usr/bin/env python3
"""
Classify remaining drugs without ATC codes using body region mapping.

This script:
1. Finds drugs with placeholder ATC codes (V99XX99)
2. Classifies based on body region to ATC category mapping
3. Updates the drug records
4. Saves updated drugs.json

Usage:
    python classify_remaining_drugs.py
"""

import json
from pathlib import Path
from collections import Counter, defaultdict

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DRUGS_FILE = PROJECT_ROOT / "src/frontend/data/drugs-with-atc.json"
OUTPUT_FILE = PROJECT_ROOT / "src/frontend/data/drugs-classified.json"

BODY_TO_ATC = {
    "brain_cns": "N",
    "heart_vascular": "C",
    "lungs_respiratory": "R",
    "liver_metabolism": "A",
    "blood_immune": "B",
    "skin_dermatological": "D",
    "eyes_sensory": "S",
    "muscle_skeletal": "M",
    "kidney_urinary": "G",
    "endocrine_metabolic": "H",
    "infection": "J",
    "cancer_oncology": "L",
    "parasitic": "P",
    "systemic_multiorgan": "V",
    "reproductive_breast": "G",
    "lung_respiratory": "R",
    "bone_joint_muscle": "M",
    "eye_ear": "S",
}

INDICATION_KEYWORDS = {
    "antibiotic": "J",
    "antifungal": "J",
    "antiviral": "J",
    "antineoplastic": "L",
    "cancer": "L",
    "tumor": "L",
    "cardiovascular": "C",
    "hypertension": "C",
    "diabetes": "A",
    "antidiabetic": "A",
    "nervous": "N",
    "depression": "N",
    "anxiety": "N",
    "pain": "N",
    "analgesic": "N",
    "respiratory": "R",
    "asthma": "R",
    "hormone": "H",
    "immunosuppress": "L",
    "infection": "J",
    "parasite": "P",
    "malaria": "P",
    "dermatolog": "D",
    "skin": "D",
    "muscle": "M",
    "bone": "M",
    "kidney": "G",
    "urinary": "G",
    "eye": "S",
    "vision": "S",
}


def classify_by_body_region(drug):
    body_region = drug.get("body_region", "systemic_multiorgan")
    atc_category = BODY_TO_ATC.get(body_region, "V")
    atc_code = f"{atc_category}99XX99"
    return atc_code, atc_category


def classify_by_indication(drug):
    indication = drug.get("indication", "")
    if not indication:
        return None, None

    indication_lower = indication.lower()
    for keyword, atc_cat in INDICATION_KEYWORDS.items():
        if keyword in indication_lower:
            atc_code = f"{atc_cat}99XX99"
            return atc_code, atc_cat

    return None, None


def classify_by_name(drug):
    name_lower = drug["name"].lower()

    name_patterns = {
        "statin": "C",
        "cillin": "J",
        "mycin": "J",
        "azole": "J",
        "virus": "J",
        "cancer": "L",
        "nib": "L",
        "mab": "L",
        "olol": "C",
        "pril": "C",
        "sartan": "C",
        "pine": "C",
        "xetine": "N",
        "zepam": "N",
        "zolam": "N",
        "done": "N",
        "etine": "N",
        "ide": "A",
        "formin": "A",
        "gliptin": "A",
        "gliflozin": "A",
    }

    for pattern, atc_cat in name_patterns.items():
        if pattern in name_lower:
            atc_code = f"{atc_cat}99XX99"
            return atc_code, atc_cat

    return None, None


def classify_drug(drug):
    atc_code, atc_category = classify_by_indication(drug)
    if atc_code:
        return atc_code, atc_category

    atc_code, atc_category = classify_by_name(drug)
    if atc_code:
        return atc_code, atc_category

    return classify_by_body_region(drug)


def main():
    print("=" * 60)
    print("Drug Classification for DrugTree")
    print("=" * 60)

    print(f"\nLoading drugs from {DRUGS_FILE}...")
    with open(DRUGS_FILE) as f:
        drugs = json.load(f)

    print(f"Total drugs: {len(drugs)}")

    placeholder_drugs = [
        d
        for d in drugs
        if d["atc_code"].startswith("V99") or d["atc_code"].startswith("X")
    ]
    print(f"Drugs needing classification: {len(placeholder_drugs)}")

    print(f"\nClassifying drugs...")
    classification_methods = Counter()
    updated_count = 0

    for drug in drugs:
        if drug["atc_code"].startswith("V99") or drug["atc_code"].startswith("X"):
            old_atc = drug["atc_code"]
            new_atc, new_category = classify_drug(drug)

            if new_atc != old_atc:
                drug["atc_code"] = new_atc
                drug["atc_category"] = new_category
                updated_count += 1

                if new_atc[0] != "V":
                    classification_methods[new_atc[0]] += 1

    print(f"\nClassification results:")
    atc_names = {
        "A": "Alimentary & Metabolism",
        "B": "Blood & Blood-forming",
        "C": "Cardiovascular",
        "D": "Dermatological",
        "G": "Genito-urinary",
        "H": "Hormones",
        "J": "Anti-infectives",
        "L": "Antineoplastic",
        "M": "Musculo-skeletal",
        "N": "Nervous System",
        "P": "Antiparasitic",
        "R": "Respiratory",
        "S": "Sensory Organs",
        "V": "Various",
    }

    final_categories = Counter(d["atc_category"] for d in drugs)
    for cat, count in sorted(final_categories.items()):
        name = atc_names.get(cat, "Unknown")
        pct = count / len(drugs) * 100
        print(f"  {cat}: {count:4d} ({pct:5.1f}%) - {name}")

    valid_atc = len([d for d in drugs if not d["atc_code"].startswith("V99")])
    placeholder_atc = len([d for d in drugs if d["atc_code"].startswith("V99")])

    print(f"\nSummary:")
    print(f"  Total drugs: {len(drugs)}")
    print(f"  With specific ATC: {valid_atc}")
    print(f"  Still placeholder (V99): {placeholder_atc}")
    print(f"  Updated in this run: {updated_count}")

    print(f"\nSaving to {OUTPUT_FILE}...")
    output_data = drugs if isinstance(drugs, list) else drugs
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output_data, f, indent=2)

    with open(DRUGS_FILE, "w") as f:
        json.dump(output_data, f, indent=2)

    print(f"\n✅ Done!")


if __name__ == "__main__":
    main()
