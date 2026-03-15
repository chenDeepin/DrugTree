"""
DrugTree - FDA openFDA API Client

Async client for FDA openFDA API with rate limiting and caching.
Retrieves drug approval status and adverse event data.
"""

import asyncio
import time
from typing import Any, Dict, List, Optional

import httpx

from cache.cache_manager import get_cache_manager

FDA_API_BASE = "https://api.fda.gov"


class FDAClient:
    """
    Async client for FDA openFDA API.

    Rate limit: 240 req/min (120K/day)
    Cache TTL: 24 hours
    Retry: 3 attempts with exponential backoff
    """

    def __init__(self, rate_limit_per_sec: float = 4.0, max_retries: int = 3):
        self.rate_limit = rate_limit_per_sec
        self.max_retries = max_retries
        self._last_request_time = 0.0
        self._cache = get_cache_manager()
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client with connection pooling."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=FDA_API_BASE,
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
                    return {"results": [], "error": {"code": "NOT_FOUND"}}
                if e.response.status_code == 429:
                    wait = 60.0
                else:
                    wait = 2.0**attempt
                await asyncio.sleep(wait)
            except httpx.RequestError as e:
                last_error = e
                await asyncio.sleep(2.0**attempt)

        raise last_error or httpx.HTTPError("Max retries exceeded")

    async def get_drug_approvals(self, drug_name: str) -> List[Dict[str, Any]]:
        """
        Get FDA approval status for a drug.

        Args:
            drug_name: Generic or brand name

        Returns:
            List of approval dicts with keys:
            - application_number: FDA application ID
            - product_name: Drug product name
            - approval_date: Initial approval date
            - sponsor: Manufacturer name
            - status: Approval status (Approved, etc.)
        """
        cache_key = f"fda:approvals:{drug_name.lower()}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            data = await self._request_with_retry(
                "/drug/drugsfda.json",
                params={
                    "search": f'openfda.generic_name:"{drug_name}" OR openfda.brand_name:"{drug_name}"',
                    "limit": 20,
                },
            )

            approvals = []
            seen_apps = set()

            for result in data.get("results", []):
                app_num = result.get("application_number", "")
                if app_num in seen_apps:
                    continue
                seen_apps.add(app_num)

                openfda = result.get("openfda", {})
                products = result.get("products", [])

                for product in products:
                    approvals.append(
                        {
                            "application_number": app_num,
                            "product_name": product.get("brand_name", "")
                            or openfda.get("brand_name", [""])[0],
                            "approval_date": result.get("submission_status_date", ""),
                            "sponsor": openfda.get("manufacturer_name", [""])[0]
                            if openfda.get("manufacturer_name")
                            else "",
                            "status": product.get("marketing_status", ""),
                        }
                    )

            self._cache.set(cache_key, approvals)
            return approvals
        except httpx.HTTPStatusError:
            return []

    async def get_adverse_events(
        self, drug_name: str, limit: int = 25
    ) -> List[Dict[str, Any]]:
        """
        Get adverse event reports for a drug.

        Args:
            drug_name: Generic or brand name
            limit: Maximum results to return

        Returns:
            List of event dicts with keys:
            - event_id: Report ID
            - event_date: Date of report
            - reactions: List of reported reactions
            - seriousness: Serious/non-serious flag
            - outcomes: Patient outcomes
        """
        cache_key = f"fda:events:{drug_name.lower()}:{limit}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            data = await self._request_with_retry(
                "/drug/event.json",
                params={
                    "search": f'patient.drug.medicinalproduct:"{drug_name}"',
                    "limit": str(limit),
                },
            )

            events = []
            for result in data.get("results", []):
                patient = result.get("patient", {})

                reactions = []
                for reaction in patient.get("reaction", []):
                    if term := reaction.get("reactionmeddrapt"):
                        reactions.append(term)

                outcomes = []
                for outcome in patient.get("summary", {}).get("patientoutcome", []):
                    outcomes.append(outcome)

                events.append(
                    {
                        "event_id": result.get("safetyreportid", ""),
                        "event_date": result.get("receivedate", ""),
                        "reactions": reactions[:10],
                        "seriousness": "serious"
                        if result.get("serious") == "1"
                        else "non-serious",
                        "outcomes": outcomes,
                    }
                )

            self._cache.set(cache_key, events)
            return events
        except httpx.HTTPStatusError:
            return []

    async def get_drug_label(self, drug_name: str) -> Dict[str, Any]:
        """
        Get drug labeling information.

        Args:
            drug_name: Generic or brand name

        Returns:
            Label dict with keys:
            - indications: Approved indications
            - contraindications: Contraindications
            - warnings: Major warnings
        """
        cache_key = f"fda:label:{drug_name.lower()}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            data = await self._request_with_retry(
                "/drug/label.json",
                params={
                    "search": f'openfda.generic_name:"{drug_name}" OR openfda.brand_name:"{drug_name}"',
                    "limit": 1,
                },
            )

            results = data.get("results", [])
            if not results:
                return {"indications": [], "contraindications": [], "warnings": []}

            label = results[0]
            label_info = {
                "indications": label.get("indications_and_usage", [])[:3],
                "contraindications": label.get("contraindications", [])[:3],
                "warnings": label.get("warnings_and_cautions", [])[:3],
            }

            self._cache.set(cache_key, label_info)
            return label_info
        except httpx.HTTPStatusError:
            return {"indications": [], "contraindications": [], "warnings": []}

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None


_fda_client: Optional[FDAClient] = None


def get_fda_client() -> FDAClient:
    """Get or create singleton FDA client."""
    global _fda_client
    if _fda_client is None:
        _fda_client = FDAClient()
    return _fda_client
