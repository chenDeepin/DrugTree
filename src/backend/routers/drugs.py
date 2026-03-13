"""
DrugTree - Drugs Router

REST API endpoints for drug data.
"""

from typing import List, Optional

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ..models.drug import Drug, DrugListResponse, DrugFilterParams

# Path to drug data
DATA_DIR = Path(__file__).parent.parent.parent / "frontend" / "data"
DRUGS_FILE = DATA_DIR / "drugs.json"


def load_drugs() -> List[Drug]:
    """Load drugs from JSON file"""
    try:
        with open(DRUGS_FILE, "r") as f:
            data = json.load(f)
            return [Drug(**drug) for drug in data.get("drugs", [])]
    except Exception as e:
        print(f"Error loading drugs: {e}")
        return []


def save_drugs(drugs: List[Drug]):
    """Save drugs to JSON file"""
    try:
        with open(DRUGS_FILE, "w") as f:
            json.dump({"drugs": [drug.model_dump() for drug in drugs]}, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving drugs: {e}")
        return False


from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/v1", tags=["drugs"])


@router.get("/drugs", response_model=DrugListResponse)
async def list_drugs(
    category: Optional[str] = None,
    search: Optional[str] = None,
    phase: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    """
    List all drugs with optional filtering.

    - **category**: Filter by ATC category (A-V)
    - **search**: Search in name, targets, class, synonyms
    - **phase**: Filter by clinical phase (I, II, III, IV)
    - **limit**: Max results to return (default 100)
    - **offset**: Pagination offset (default 0)
    """
    drugs = load_drugs()

    # Apply filters
    filtered_drugs = drugs

    if category:
        filtered_drugs = [
            d for d in filtered_drugs if d.atc_category == category.upper()
        ]

    if phase:
        filtered_drugs = [d for d in filtered_drugs if d.phase == phase]

    if search:
        search_lower = search.lower()
        filtered_drugs = [
            d
            for d in filtered_drugs
            if search_lower in d.name.lower()
            or any(search_lower in str(t).lower() for t in (d.targets or []))
            or (d.class_name and search_lower in d.class_name.lower())
            or any(search_lower in str(s).lower() for s in (d.synonyms or []))
        ]

    # Apply pagination
    total = len(filtered_drugs)
    paginated_drugs = filtered_drugs[offset : offset + limit]

    return DrugListResponse(total=total, drugs=paginated_drugs)


@router.get("/drugs/{drug_id}", response_model=Drug)
async def get_drug(drug_id: str):
    """
    Get a specific drug by ID.

    - **drug_id**: Unique drug identifier (e.g., 'atorvastatin')
    """
    drugs = load_drugs()

    for drug in drugs:
        if drug.id == drug_id:
            return drug

    raise HTTPException(status_code=404, detail=f"Drug '{drug_id}' not found")


@router.get("/drugs/category/{category}", response_model=DrugListResponse)
async def get_drugs_by_category(category: str):
    """
    Get all drugs in a specific ATC category.

    - **category**: ATC category code (A-V)
    """
    drugs = load_drugs()
    filtered = [d for d in drugs if d.atc_category == category.upper()]

    return DrugListResponse(total=len(filtered), drugs=filtered)


@router.get("/drugs/search/{query}", response_model=DrugListResponse)
async def search_drugs(query: str):
    """
    Search drugs by name, target, class, or synonyms.

    - **query**: Search query string
    """
    drugs = load_drugs()
    query_lower = query.lower()

    filtered = [
        d
        for d in drugs
        if query_lower in d.name.lower()
        or any(query_lower in str(t).lower() for t in (d.targets or []))
        or (d.class_name and query_lower in d.class_name.lower())
        or any(query_lower in str(s).lower() for s in (d.synonyms or []))
        or (d.indication and query_lower in d.indication.lower())
    ]

    return DrugListResponse(total=len(filtered), drugs=filtered)


@router.get("/categories")
async def list_categories():
    """
    List all ATC categories with drug counts.
    """
    drugs = load_drugs()

    categories = {}
    for drug in drugs:
        cat = drug.atc_category
        if cat:
            categories[cat] = categories.get(cat, 0) + 1

    return {
        "categories": [
            {"code": code, "count": count} for code, count in sorted(categories.items())
        ]
    }


@router.get("/stats")
async def get_statistics():
    """
    Get drug database statistics.
    """
    drugs = load_drugs()

    categories = {}
    phases = {}
    companies = set()
    targets = set()

    for drug in drugs:
        # Count by category
        if drug.atc_category:
            categories[drug.atc_category] = categories.get(drug.atc_category, 0) + 1

        # Count by phase
        if drug.phase:
            phases[drug.phase] = phases.get(drug.phase, 0) + 1

        # Unique companies
        if drug.company:
            companies.add(drug.company)

        # Unique targets
        if drug.targets:
            targets.update(drug.targets)

    return {
        "total_drugs": len(drugs),
        "categories": categories,
        "phases": phases,
        "unique_companies": len(companies),
        "unique_targets": len(targets),
    }
