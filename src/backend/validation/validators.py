"""
DrugTree - Data Validation Utilities

Provides validation functions for drug data, including ATC codes, data quality checks, and migration comparison tools.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

# ATC Level 1 categories (14 total)
ATC_LEVEL1_CATEGORIES = {
    "A": "Alimentary tract and metabolism",
    "B": "Blood and blood forming organs",
    "C": "Cardiovascular system",
    "D": "Dermatologicals",
    "G": "Genito-urinary system and sex hormones",
    "H": "Systemic hormonal preparations, excluding sex hormones",
    "J": "Antiinfectives for systemic use",
    "L": "Antineoplastic and immunomodulating agents",
    "M": "Musculo-skeletal system",
    "N": "Nervous system",
    "P": "Antiparasitic products, insecticides and repellents",
    "R": "Respiratory system",
    "S": "Sensory organs",
    "V": "Various",
}


@dataclass
class ValidationResult:
    """Result of a validation check"""

    is_valid: bool
    errors: List[str]
    warnings: List[str]


def validate_atc_code(atc_code: str) -> Tuple[bool, str]:
    """
    Validate an ATC code against WHO format

    WHO ATC format: [A-Z]{2}[A-Z]{2}[A-Z]{2}[A-Z]{2}
    Example: C10AA05

    Args:
        atc_code: ATC code to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not atc_code:
        return False, "ATC code is empty"

    atc_code = atc_code.upper().strip()

    # Check length (1 or 7 characters)
    if len(atc_code) < 1 or len(atc_code) > 7:
        return (
            False,
            f"ATC code must be between 1-7 characters, got {len(atc_code)}",
        )

    # Check Level 1 (first character)
    level1 = atc_code[0]
    if level1 not in ATC_LEVEL1_CATEGORIES:
        return (
            False,
            f"Invalid Level 1 category: {level1}. Must be one of {list(ATC_LEVEL1_CATEGORIES.keys())}",
        )

        # If full code (7 characters)
    if len(atc_code) == 7:
        # Check format: Letter + 2 digits + letter + letter + letter + 2 digits
        import re

        pattern = r"^[A-Z]\d{2}[A-Z]{2}[A-Z]{2}$"
        if not re.match(pattern, atc_code):
            return (
                False,
                f"Invalid ATC format. Expected: C10AA05, got: {atc_code}",
            )

    return True, ""


def compare_drug_data(before_path: str, after_path: str) -> Dict[str, Any]:
    """
    Compare drug data before and after migration

    Args:
        before_path: Path to original JSON file
        after_path: Path to migrated data (or connection string)

    Returns:
        Dictionary with comparison results:
        - total_before: Number of drugs before
        - total_after: Number of drugs after
        - missing: Drugs that exist before but not after
        - added: Drugs that exist after but not before
        - changed: Drugs with different data
        - identical: Drugs with identical data
    """
    # Load original data
    with open(before_path, "r") as f:
        before_data = json.load(f)
    before_drugs = {d["id"]: d for d in before_data.get("drugs", [])}

    # Load migrated data (assuming JSON for now, DB would need different handling)
    try:
        with open(after_path, "r") as f:
            after_data = json.load(f)
        after_drugs = {d["id"]: d for d in after_data.get("drugs", [])}
    except FileNotFoundError:
        # If after file doesn't exist, assume DB connection
        after_drugs = {}

    before_ids = set(before_drugs.keys())
    after_ids = set(after_drugs.keys())

    result = {
        "total_before": len(before_drugs),
        "total_after": len(after_drugs),
        "missing": [],
        "added": [],
        "changed": [],
        "identical": [],
    }

    # Find missing drugs
    for drug_id in before_ids - after_ids:
        result["missing"].append(
            {"id": drug_id, "name": before_drugs[drug_id].get("name", "")}
        )

    # Find added drugs
    for drug_id in after_ids - before_ids:
        result["added"].append(
            {"id": drug_id, "name": after_drugs[drug_id].get("name", "")}
        )

    # Compare changed drugs
    for drug_id in before_ids & after_ids:
        before_drug = before_drugs[drug_id]
        after_drug = after_drugs[drug_id]

        # Compare key fields
        fields_to_compare = [
            "name",
            "smiles",
            "atc_code",
            "molecular_weight",
            "targets",
        ]
        changes = {}
        for field in fields_to_compare:
            before_val = before_drug.get(field)
            after_val = after_drug.get(field)

            if before_val != after_val:
                changes[field] = {"before": before_val, "after": after_val}

        if changes:
            result["changed"].append(
                {
                    "id": drug_id,
                    "name": before_drug.get("name", ""),
                    "changes": changes,
                }
            )
        else:
            result["identical"].append(drug_id)

    return result


def calculate_coverage(drugs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calculate ATC coverage statistics for a list of drugs

    Args:
        drugs: List of drug dictionaries

    Returns:
        Dictionary with coverage statistics:
        - total_drugs: Total number of drugs
        - drugs_with_atc: Drugs with ATC codes
        - drugs_without_atc: Drugs without ATC codes
        - coverage_percentage: Percentage with ATC codes
        - level1_distribution: Count per Level 1 category
        - valid_codes: Number of valid ATC codes
        - invalid_codes: Number of invalid ATC codes
    """
    total_drugs = len(drugs)
    drugs_with_atc = 0
    drugs_without_atc = 0
    level1_distribution = {cat: 0 for cat in ATC_LEVEL1_CATEGORIES.keys()}
    valid_codes = 0
    invalid_codes = 0

    for drug in drugs:
        atc_code = drug.get("atc_code", "")

        if not atc_code:
            drugs_without_atc += 1
            continue

        # Validate ATC code
        is_valid, error = validate_atc_code(atc_code)

        if is_valid:
            drugs_with_atc += 1
            valid_codes += 1

            # Track Level 1 category
            level1 = atc_code[0].upper()
            if level1 in level1_distribution:
                level1_distribution[level1] += 1
        else:
            invalid_codes += 1

    coverage_percentage = (drugs_with_atc / total_drugs * 100) if total_drugs > 0 else 0

    return {
        "total_drugs": total_drugs,
        "drugs_with_atc": drugs_with_atc,
        "drugs_without_atc": drugs_without_atc,
        "coverage_percentage": round(coverage_percentage, 2),
        "level1_distribution": level1_distribution,
        "valid_codes": valid_codes,
        "invalid_codes": invalid_codes,
    }


def validate_drug_data(drug: Dict[str, Any]) -> ValidationResult:
    """
    Validate a single drug's data quality

    Args:
        drug: Drug dictionary to validate

    Returns:
        ValidationResult with is_valid, errors, and warnings
    """
    errors = []
    warnings = []

    # Check required fields
    required_fields = ["id", "name", "atc_code"]
    for field in required_fields:
        if not drug.get(field):
            errors.append(f"Missing required field: {field}")

    # Check ID format
    drug_id = drug.get("id", "")
    if drug_id and not drug_id.replace("_", "").replace("-", "").isalnum():
        warnings.append(f"ID contains special characters: {drug_id}")

    # Check SMILES format
    smiles = drug.get("smiles", "")
    if smiles and len(smiles) < 5:
        warnings.append(f"SMILES string too short: {smiles}")

    # Check ATC code
    atc_code = drug.get("atc_code", "")
    if atc_code:
        is_valid, error = validate_atc_code(atc_code)
        if not is_valid:
            errors.append(error)

    # Check molecular weight
    mw = drug.get("molecular_weight")
    if mw and (mw < 0 or mw > 10000):
        warnings.append(f"Molecular weight out of range: {mw}")

    # Check year approved
    year = drug.get("year_approved")
    if year and (year < 1800 or year > 2100):
        warnings.append(f"Year approved out of range: {year}")

    return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings)


def generate_validation_report(
    drugs: List[Dict[str, Any]], output_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generate a comprehensive validation report for a drug dataset

    Args:
        drugs: List of drug dictionaries to validate
        output_path: Optional path to save report as JSON

    Returns:
        Dictionary with complete validation report
    """
    # Calculate coverage
    coverage = calculate_coverage(drugs)

    # Validate individual drugs
    validation_results = []
    error_count = 0
    warning_count = 0

    for drug in drugs:
        result = validate_drug_data(drug)
        if not result.is_valid or result.warnings:
            validation_results.append(
                {
                    "id": drug.get("id"),
                    "name": drug.get("name"),
                    "is_valid": result.is_valid,
                    "errors": result.errors,
                    "warnings": result.warnings,
                }
            )
        error_count += len(result.errors)
        warning_count += len(result.warnings)

    report = {
        "summary": {
            "total_drugs": len(drugs),
            "valid_drugs": len(drugs) - error_count,
            "drugs_with_errors": error_count,
            "drugs_with_warnings": warning_count,
        },
        "coverage": coverage,
        "validation_results": validation_results,
    }

    # Save report if path provided
    if output_path:
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)

    return report
