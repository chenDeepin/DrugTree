"""
DrugTree - ChEMBL API Client

Async client for ChEMBL REST API with rate limiting, caching, and retry logic.
Only fetches clinical trial data (Phase I-IV), not preclinical compounds.
"""

import asyncio
import time
from typing import Any, Dict, List, Optional

import httpx

from cache.cache_manager import get_cache_manager

CHEMBL_API_BASE = "https://www.ebi.ac.uk/chembl/api/data"


class ChEMBLClient:
    """
    Async client for ChEMBL API with responsible use patterns.

    Rate limit: 1 req/sec (ChEMBL policy)
    Cache TTL: 24 hours
    Retry: 3 attempts with exponential backoff
    """

    def __init__(self, rate_limit_per_sec: float = 1.0, max_retries: int = 3):
        self.rate_limit = rate_limit_per_sec
        self.max_retries = max_retries
        self._last_request_time = 0.0
        self._cache = get_cache_manager()
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client with connection pooling."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=CHEMBL_API_BASE,
                timeout=30.0,
                headers={"Accept": "application/json"},
            )
        return self._client

    async def _rate_limit_wait(self) -> None:
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        wait_time = (1.0 / self.rate_limit) - elapsed
        if wait_time > 0:
            await asyncio.sleep(wait_time)
        self._last_request_time = time.time()

    async def _request_with_retry(
        self, endpoint: str, params: Optional[Dict] = None
    ) -> Dict:
        """
        Make API request with retry and exponential backoff.

        Args:
            endpoint: API endpoint path
            params: Query parameters

        Returns:
            JSON response dict

        Raises:
            httpx.HTTPError: After all retries exhausted
        """
        client = await self._get_client()
        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries):
            try:
                await self._rate_limit_wait()
                response = await client.get(endpoint, params=params)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                last_error = e
                if e.response.status_code == 404:
                    raise
                if e.response.status_code == 429:
                    wait = 60.0
                else:
                    wait = 2.0**attempt
                await asyncio.sleep(wait)
            except httpx.RequestError as e:
                last_error = e
                await asyncio.sleep(2.0**attempt)

        raise last_error or httpx.HTTPError("Max retries exceeded")

    async def get_drug_indications(self, chembl_id: str) -> List[Dict[str, Any]]:
        """
        Fetch drug-disease associations for a molecule.

        Args:
            chembl_id: ChEMBL molecule ID (e.g., "CHEMBL1485")

        Returns:
            List of indication dicts with keys:
            - disease_id: MeSH/ICD code
            - disease_name: Human-readable name
            - indication_type: Primary/secondary
            - phase: Clinical phase (1-4)
        """
        cache_key = f"chembl:indications:{chembl_id}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            data = await self._request_with_retry(
                f"/drug_indication",
                params={"molecule_chembl_id": chembl_id, "limit": 100},
            )

            indications = []
            for item in data.get("drug_indications", []):
                indications.append(
                    {
                        "disease_id": item.get("mesh_id") or item.get("efo_id"),
                        "disease_name": item.get("mesh_heading")
                        or item.get("efo_name"),
                        "indication_type": "primary"
                        if item.get("indications")
                        else "secondary",
                        "phase": item.get("max_phase_for_ind", 0),
                    }
                )

            self._cache.set(cache_key, indications)
            return indications
        except httpx.HTTPStatusError:
            return []

    async def get_clinical_candidates(
        self, target_chembl_id: str
    ) -> List[Dict[str, Any]]:
        """
        Get Phase I-IV molecules for a target.

        Args:
            target_chembl_id: ChEMBL target ID (e.g., "CHEMBL240")

        Returns:
            List of molecule dicts with keys:
            - chembl_id: Molecule ID
            - name: Preferred name
            - phase: Clinical phase (1-4)
            - mechanism: Mechanism of action
        """
        cache_key = f"chembl:candidates:{target_chembl_id}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            data = await self._request_with_retry(
                f"/mechanism",
                params={"target_chembl_id": target_chembl_id, "limit": 100},
            )

            candidates = []
            seen_ids = set()

            for item in data.get("mechanisms", []):
                mol_id = item.get("molecule_chembl_id")
                if not mol_id or mol_id in seen_ids:
                    continue

                max_phase = item.get("max_phase", 0)
                if max_phase < 1:
                    continue

                seen_ids.add(mol_id)
                candidates.append(
                    {
                        "chembl_id": mol_id,
                        "name": item.get("molecule_pref_name", ""),
                        "phase": max_phase,
                        "mechanism": item.get("mechanism_of_action", ""),
                    }
                )

            self._cache.set(cache_key, candidates)
            return candidates
        except httpx.HTTPStatusError:
            return []

    async def get_target_diseases(self, target_chembl_id: str) -> List[Dict[str, Any]]:
        """
        Fetch target-disease mappings from drug indications.

        Args:
            target_chembl_id: ChEMBL target ID

        Returns:
            List of disease dicts with keys:
            - disease_id: MeSH/ICD code
            - disease_name: Human-readable name
            - drug_count: Number of drugs for this disease
        """
        cache_key = f"chembl:target_diseases:{target_chembl_id}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        candidates = await self.get_clinical_candidates(target_chembl_id)

        disease_map: Dict[str, Dict] = {}
        for candidate in candidates:
            indications = await self.get_drug_indications(candidate["chembl_id"])
            for ind in indications:
                disease_id = ind.get("disease_id")
                if not disease_id:
                    continue
                if disease_id not in disease_map:
                    disease_map[disease_id] = {
                        "disease_id": disease_id,
                        "disease_name": ind.get("disease_name", ""),
                        "drug_count": 0,
                    }
                disease_map[disease_id]["drug_count"] += 1

        diseases = list(disease_map.values())
        self._cache.set(cache_key, diseases)
        return diseases

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None


_chembl_client: Optional[ChEMBLClient] = None


def get_chembl_client() -> ChEMBLClient:
    """Get or create singleton ChEMBL client."""
    global _chembl_client
    if _chembl_client is None:
        _chembl_client = ChEMBLClient()
    return _chembl_client
