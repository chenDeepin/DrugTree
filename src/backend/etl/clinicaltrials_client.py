"""
DrugTree - ClinicalTrials.gov API Client

Async client for ClinicalTrials.gov API v2.0 with rate limiting and caching.
Searches clinical trials by condition and retrieves intervention data.
"""

import asyncio
import time
from typing import Any, Dict, List, Optional

import httpx

from ..cache.cache_manager import get_cache_manager

CTG_API_BASE = "https://clinicaltrials.gov/api/v2"


class ClinicalTrialsClient:
    """
    Async client for ClinicalTrials.gov API v2.0.

    Rate limit: 5 req/sec
    Cache TTL: 24 hours
    Retry: 3 attempts with exponential backoff
    """

    def __init__(self, rate_limit_per_sec: float = 5.0, max_retries: int = 3):
        self.rate_limit = rate_limit_per_sec
        self.max_retries = max_retries
        self._last_request_time = 0.0
        self._cache = get_cache_manager()
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client with connection pooling."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=CTG_API_BASE,
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

    async def search_studies(
        self, condition: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Search clinical trials by disease/condition.

        Args:
            condition: Disease name or MeSH term
            limit: Maximum results to return

        Returns:
            List of study dicts with keys:
            - nct_id: NCT identifier
            - title: Brief title
            - phase: Clinical phase
            - status: Recruitment status
            - sponsor: Lead sponsor name
            - interventions: List of intervention names
        """
        cache_key = f"ctg:studies:{condition}:{limit}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            data = await self._request_with_retry(
                "/studies",
                params={
                    "query.cond": condition,
                    "filter.overallStatus": "RECRUITING,NOT_YET_RECRUITING,ACTIVE_NOT_RECRUITING",
                    "pageSize": str(limit),
                    "format": "json",
                },
            )

            studies = []
            for study in data.get("studies", []):
                protocol = study.get("protocolSection", {})
                identification = protocol.get("identificationModule", {})
                status_module = protocol.get("statusModule", {})
                sponsor_module = protocol.get("sponsorCollaboratorsModule", {})
                design_module = protocol.get("designModule", {})
                arms_module = protocol.get("armsInterventionsModule", {})

                interventions = []
                for intervention in arms_module.get("interventions", []):
                    if name := intervention.get("name"):
                        interventions.append(name)

                phases = design_module.get("phases", [])
                phase = phases[0] if phases else "N/A"

                studies.append(
                    {
                        "nct_id": identification.get("nctId", ""),
                        "title": identification.get("briefTitle", ""),
                        "phase": phase,
                        "status": status_module.get("overallStatus", ""),
                        "sponsor": sponsor_module.get("leadSponsor", {}).get(
                            "name", ""
                        ),
                        "interventions": interventions[:10],
                    }
                )

            self._cache.set(cache_key, studies)
            return studies
        except httpx.HTTPStatusError:
            return []

    async def get_trial_interventions(self, nct_id: str) -> List[Dict[str, Any]]:
        """
        Get drug interventions for a specific trial.

        Args:
            nct_id: NCT identifier (e.g., "NCT04640170")

        Returns:
            List of intervention dicts with keys:
            - name: Intervention name
            - type: Intervention type (Drug, Biological, etc.)
            - description: Brief description
        """
        cache_key = f"ctg:interventions:{nct_id}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            data = await self._request_with_retry(
                f"/studies/{nct_id}",
                params={"format": "json"},
            )

            interventions = []
            protocol = data.get("protocolSection", {})
            arms_module = protocol.get("armsInterventionsModule", {})

            for intervention in arms_module.get("interventions", []):
                interventions.append(
                    {
                        "name": intervention.get("name", ""),
                        "type": intervention.get("type", ""),
                        "description": intervention.get("description", "")[:500]
                        if intervention.get("description")
                        else "",
                    }
                )

            self._cache.set(cache_key, interventions)
            return interventions
        except httpx.HTTPStatusError:
            return []

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None


_ctg_client: Optional[ClinicalTrialsClient] = None


def get_clinicaltrials_client() -> ClinicalTrialsClient:
    """Get or create singleton ClinicalTrials.gov client."""
    global _ctg_client
    if _ctg_client is None:
        _ctg_client = ClinicalTrialsClient()
    return _ctg_client
