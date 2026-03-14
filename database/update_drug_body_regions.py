#!/usr/bin/env python3
"""
Update drugs-full.json with body_regions field based on ATC category and indication.
This script adds the body_regions array to each drug for proper filtering.
"""

import json
from pathlib import Path

# ATC Category to Body Regions Mapping
# Based on the body-ontology.json visible regions
ATC_TO_BODY_REGIONS = {
    # A - Alimentary tract & metabolism: digestive system + metabolic
    "A": [
        "stomach_upper_gi",
        "intestine_colorectal",
        "liver_biliary_pancreas",
        "endocrine_metabolic",
    ],
    # B - Blood & blood-forming organs: blood system
    "B": ["blood_immune", "heart_vascular"],
    # C - Cardiovascular system: heart and vessels
    "C": [
        "heart_vascular",
        "blood_immune",
        "kidney_urinary",
    ],  # Many CV drugs also affect kidneys
    # D - Dermatologicals: skin
    "D": ["skin"],
    # G - Genito-urinary system and sex hormones
    "G": ["kidney_urinary", "reproductive_breast"],
    # H - Systemic hormonal preparations, excl. sex hormones and insulins
    "H": ["endocrine_metabolic", "systemic_multiorgan"],
    # J - Anti-infectives for systemic use: INFECTIONS OCCUR EVERYWHERE
    "J": [
        "brain_cns",
        "eye_ear",
        "lung_respiratory",
        "heart_vascular",
        "blood_immune",
        "stomach_upper_gi",
        "intestine_colorectal",
        "liver_biliary_pancreas",
        "kidney_urinary",
        "reproductive_breast",
        "bone_joint_muscle",
        "skin",
        "systemic_multiorgan",
    ],
    # L - Antineoplastic and immunomodulating agents: CANCERS OCCUR EVERYWHERE
    "L": [
        "brain_cns",
        "eye_ear",
        "lung_respiratory",
        "heart_vascular",
        "blood_immune",
        "stomach_upper_gi",
        "intestine_colorectal",
        "liver_biliary_pancreas",
        "endocrine_metabolic",
        "kidney_urinary",
        "reproductive_breast",
        "bone_joint_muscle",
        "skin",
        "systemic_multiorgan",
    ],
    # M - Musculo-skeletal system
    "M": ["bone_joint_muscle", "systemic_multiorgan"],
    # N - Nervous system
    "N": ["brain_cns", "systemic_multiorgan"],
    # P - Antiparasitic products, insecticides and repellents
    "P": ["intestine_colorectal", "blood_immune", "skin", "systemic_multiorgan"],
    # R - Respiratory system
    "R": ["lung_respiratory", "systemic_multiorgan"],
    # S - Sensory organs
    "S": ["eye_ear"],
    # V - Various
    "V": ["systemic_multiorgan"],
}

# Indication keywords to additional body regions mapping
# This adds specificity based on drug indication text
INDICATION_KEYWORDS = {
    "brain_cns": [
        "brain",
        "cns",
        "neural",
        "neurological",
        "seizure",
        "epilepsy",
        "alzheimer",
        "parkinson",
        "migraine",
    ],
    "eye_ear": ["eye", "retina", "glaucoma", "vision", "otic", "ear"],
    "lung_respiratory": [
        "lung",
        "respiratory",
        "asthma",
        "copd",
        "bronchitis",
        "pneumonia",
        "pulmonary",
    ],
    "heart_vascular": [
        "heart",
        "cardiac",
        "cardiovascular",
        "hypertension",
        "angina",
        "arrhythmia",
        "vascular",
        "cholesterol",
        "lipid",
    ],
    "blood_immune": [
        "blood",
        "anemia",
        "leukemia",
        "lymphoma",
        "clotting",
        "thromb",
        "immune",
        "infection",
    ],
    "stomach_upper_gi": ["stomach", "gastric", "gerd", "reflux", "ulcer", "esophag"],
    "intestine_colorectal": [
        "intestinal",
        "colorectal",
        "colon",
        "bowel",
        "crohn",
        "colitis",
        "diarrhea",
    ],
    "liver_biliary_pancreas": ["liver", "hepat", "biliary", "pancreas", "pancreatic"],
    "endocrine_metabolic": [
        "diabetes",
        "thyroid",
        "hormone",
        "metabolic",
        "glucose",
        "insulin",
        "obesity",
    ],
    "kidney_urinary": [
        "kidney",
        "renal",
        "urinary",
        "bladder",
        "uti",
        "prostate",
        "bph",
    ],
    "reproductive_breast": [
        "breast",
        "ovarian",
        "uterine",
        "prostate",
        "testicular",
        "fertility",
    ],
    "bone_joint_muscle": [
        "bone",
        "joint",
        "arthritis",
        "osteoporosis",
        "muscle",
        "rheumatoid",
        "gout",
    ],
    "skin": ["skin", "dermat", "psoriasis", "acne", "eczema", "rash"],
    "systemic_multiorgan": ["systemic", "general", "multiorgan", "autoimmune", "lupus"],
}


def get_body_regions_from_indication(indication: str) -> list:
    """Extract body regions from indication text based on keywords."""
    indication_lower = indication.lower()
    regions = set()

    for region, keywords in INDICATION_KEYWORDS.items():
        for keyword in keywords:
            if keyword in indication_lower:
                regions.add(region)
                break  # Only add region once even if multiple keywords match

    return list(regions)


def determine_body_regions(drug: dict) -> list:
    """
    Determine body regions for a drug based on ATC category and indication.

    Priority:
    1. If drug already has body_regions, keep it
    2. Use ATC category mapping as base
    3. Add regions from indication keywords
    4. Remove duplicates while preserving order
    """
    # If drug already has body_regions, return it
    if "body_regions" in drug and drug["body_regions"]:
        return drug["body_regions"]

    atc_category = drug.get("atc_category", "V")
    indication = drug.get("indication", "")

    # Start with ATC category mapping
    base_regions = ATC_TO_BODY_REGIONS.get(atc_category, ["systemic_multiorgan"])

    # For J and L categories (anti-infectives and antineoplastics),
    # we use ALL body regions as base, but indication can help narrow
    if atc_category in ["J", "L"]:
        # Get specific regions from indication
        indication_regions = get_body_regions_from_indication(indication)

        if indication_regions:
            # If we found specific regions from indication, use those
            # but keep systemic_multiorgan for systemic drugs
            if "systemic" in indication.lower() or len(indication_regions) > 3:
                return ["systemic_multiorgan"]
            return indication_regions
        else:
            # No specific indication found, use all regions
            return base_regions

    # For other categories, combine ATC mapping with indication regions
    indication_regions = get_body_regions_from_indication(indication)

    # Combine and deduplicate while preserving order
    all_regions = base_regions + [
        r for r in indication_regions if r not in base_regions
    ]

    return all_regions


def update_drugs_file():
    """Update the drugs-full.json file with body_regions."""
    # Paths
    project_root = Path(__file__).parent.parent
    drugs_file = project_root / "src/frontend/data/drugs-full.json"
    output_file = project_root / "database/drugs/drugs-with-body-regions.json"

    # Load existing drugs
    with open(drugs_file, "r") as f:
        data = json.load(f)

    drugs = data.get("drugs", data)  # Handle both formats

    # Update each drug
    updated_drugs = []
    for drug in drugs:
        drug_copy = drug.copy()
        drug_copy["body_regions"] = determine_body_regions(drug)
        updated_drugs.append(drug_copy)
        print(f"Updated {drug['name']}: {drug_copy['body_regions']}")

    # Create output
    output_data = {
        "version": "2.0.0",
        "description": "Drugs with body region mappings for filtering",
        "generated": "2026-03-14",
        "total_drugs": len(updated_drugs),
        "drugs": updated_drugs,
    }

    # Ensure output directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Save to output file
    with open(output_file, "w") as f:
        json.dump(output_data, f, indent=2)

    print(f"\nUpdated {len(updated_drugs)} drugs")
    print(f"Output saved to: {output_file}")

    return output_file


if __name__ == "__main__":
    update_drugs_file()
