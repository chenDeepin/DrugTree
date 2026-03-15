"""
DrugTree - PubChem API Client

Async client for PubChem PUG REST API with rate limiting, caching, and retry logic.
Fetches compound data and ATC classifications.
"""

import asyncio
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

PUBCHEM_API_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"


class PubChemClient:
    """
    Async client for PubChem API with responsible use patterns.

    Rate limit: 5 req/sec (PubChem policy)
    Cache TTL: 24 hours
    Retry: 3 attempts with exponential backoff
    """

    def __init__(
        self,
        rate_limit_per_sec: float = 5.0,
        max_retries: int = 3,
        cache_dir: Optional[Path] = None,
        request_timeout: float = 30.0,
    ):
        """
        Initialize PubChem client.

        Args:
            rate_limit_per_sec: Maximum requests per second (default: 5)
            max_retries: Maximum retry attempts (default: 3)
            cache_dir: Directory for caching responses (default: temp dir)
            request_timeout: HTTP request timeout in seconds (default: 30)
        """
        self.rate_limit = rate_limit_per_sec
        self.max_retries = max_retries
        self._last_request_time = 0.0
        self._client: Optional[httpx.AsyncClient] = None
        self.request_timeout = request_timeout

        # Setup cache directory
        if cache_dir is None:
            cache_dir = Path.home() / ".drugtree" / "cache" / "pubchem"
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client with connection pooling."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=PUBCHEM_API_BASE,
                timeout=self.request_timeout,
                headers={"Accept": "application/json"},
            )
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "PubChemClient":
        """Context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        await self.close()

    async def _rate_limit_wait(self) -> None:
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        wait_time = (1.0 / self.rate_limit) - elapsed
        if wait_time > 0:
            await asyncio.sleep(wait_time)
        self._last_request_time = time.time()

    def _get_cache_key(self, query: str, identifier: str) -> Path:
        """
        Generate cache key based on query and identifier.

        Args:
            query: Query type (e.g., "compound", "synonym")
            identifier: Query identifier (e.g., InChIKey, SMILES)

        Returns:
            Path to cache file
        """
        key_hash = hashlib.md5(f"{query}:{identifier}".encode()).hexdigest()
        return self.cache_dir / f"{key_hash}.json"

    async def _get_cached(self, cache_key: Path) -> Optional[Dict]:
        """
        Retrieve cached result if available and fresh.

        Args:
            cache_key: Path to cache file

        Returns:
            Cached data if available and fresh, None otherwise
        """
        if not cache_key.exists():
            return None

        # Check age (24 hour TTL)
        age_hours = (time.time() - cache_key.stat().st_mtime) / 3600
        if age_hours > 24:
            return None

        try:
            with open(cache_key, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

    async def _set_cached(self, cache_key: Path, data: Dict) -> None:
        """
        Cache result to file.

        Args:
            cache_key: Path to cache file
            data: Data to cache
        """
        try:
            with open(cache_key, "w") as f:
                json.dump(data, f)
        except IOError as e:
            # Non-fatal: cache write failure
            pass

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
            PubChemAPIError: After all retries exhausted
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
                    # Rate limited - wait longer
                    wait = 60.0
                else:
                    wait = 2.0**attempt
                await asyncio.sleep(wait)
            except httpx.RequestError as e:
                last_error = e
                await asyncio.sleep(2.0**attempt)

        raise PubChemAPIError(f"Max retries exceeded: {last_error}") from last_error

    async def get_compound_by_inchikey(self, inchikey: str) -> Optional[Dict]:
        """
        Retrieve compound data by InChIKey.

        Args:
            inchikey: InChIKey identifier

        Returns:
            Compound data dict or None if not found
        """
        cache_key = self._get_cache_key("inchikey", inchikey)

        # Check cache
        cached = await self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            endpoint = f"/compound/inchikey/{inchikey}/JSON"
            data = await self._request_with_retry(endpoint)

            # Cache result
            await self._set_cached(cache_key, data)

            return data
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    async def get_compound_by_smiles(self, smiles: str) -> Optional[Dict]:
        """
        Retrieve compound data by SMILES string.

        Args:
            smiles: SMILES string

        Returns:
            Compound data dict or None if not found
        """
        cache_key = self._get_cache_key("smiles", smiles)

        # Check cache
        cached = await self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            # URL encode SMILES
            endpoint = f"/compound/smiles/{httpx.URL(smiles).path}"
            data = await self._request_with_retry(endpoint)

            # Cache result
            await self._set_cached(cache_key, data)

            return data
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    async def get_compound_by_name(self, name: str) -> Optional[Dict]:
        """
        Retrieve compound data by name.

        Args:
            name: Drug name

        Returns:
            Compound data dict or None if not found
        """
        cache_key = self._get_cache_key("name", name)

        # Check cache
        cached = await self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            endpoint = f"/compound/name/{name}/JSON"
            data = await self._request_with_retry(endpoint)

            # Cache result
            await self._set_cached(cache_key, data)

            return data
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    async def get_compound_cid(
        self, identifier: str, id_type: str = "name"
    ) -> Optional[int]:
        """
        Get PubChem CID for a compound.

        Args:
            identifier: Compound identifier (name, InChIKey, SMILES)
            id_type: Type of identifier ("name", "inchikey", "smiles")

        Returns:
            PubChem CID or None if not found
        """
        try:
            endpoint = f"/compound/{id_type}/{identifier}/cids/JSON"
            data = await self._request_with_retry(endpoint)

            cids = data.get("IdentifierList", {}).get("CID", [])
            return cids[0] if cids else None
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    async def get_atc_cross_references(self, cid: int) -> List[str]:
        """
        Get ATC classification cross-references for a compound.

        PubChem stores ATC codes in the xrefs section.

        Args:
            cid: PubChem Compound ID

        Returns:
            List of ATC codes (may be empty)
        """
        cache_key = self._get_cache_key("atc", str(cid))

        # Check cache
        cached = await self._get_cached(cache_key)
        if cached is not None:
            return cached.get("atc_codes", [])

        try:
            # Get synonym data which includes ATC codes
            endpoint = f"/compound/cid/{cid}/synonyms/JSON"
            data = await self._request_with_retry(endpoint)

            # Extract ATC codes from synonyms
            # ATC codes follow pattern: Letter + 2 digits + 2 letters + 2 letters + 2 digits
            atc_codes = []
            synonyms = data.get("InformationList", {}).get("Information", [{}])

            for syn_info in synonyms:
                synonyms_list = syn_info.get("Synonym", [])
                for syn in synonyms_list:
                    syn_str = str(syn).upper().strip()
                    # Check if it matches ATC pattern (e.g., C10AA05)
                    if len(syn_str) == 7 and syn_str[0].isalpha():
                        if syn_str[1:3].isdigit() and syn_str[3:5].isalpha():
                            if (
                                syn_str[5:7].isalpha() and syn_str[7:9].isdigit()
                                if len(syn_str) > 7
                                else True
                            ):
                                # Potential ATC code
                                if syn_str not in atc_codes:
                                    atc_codes.append(syn_str)

            # Also check for explicit ATC: prefix
            for syn_info in synonyms:
                synonyms_list = syn_info.get("Synonym", [])
                for syn in synonyms_list:
                    syn_str = str(syn)
                    if syn_str.startswith("ATC:"):
                        code = syn_str.replace("ATC:", "").strip().upper()
                        if code and code not in atc_codes:
                            atc_codes.append(code)

            # Cache result
            result = {"atc_codes": atc_codes}
            await self._set_cached(cache_key, result)

            return atc_codes
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return []
            raise

    async def get_compound_properties(
        self, cid: int, properties: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Get compound properties.

        Args:
            cid: PubChem Compound ID
            properties: List of property names to fetch
                       (default: common properties)

        Returns:
            Dictionary of property name -> value
        """
        if properties is None:
            properties = [
                "MolecularFormula",
                "MolecularWeight",
                "InChI",
                "InChIKey",
                "SMILES",
                "CanonicalSMILES",
                "IsomericSMILES",
            ]

        cache_key = self._get_cache_key("props", f"{cid}_{','.join(properties)}")

        # Check cache
        cached = await self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            props_str = ",".join(properties)
            endpoint = f"/compound/cid/{cid}/property/{props_str}/JSON"
            data = await self._request_with_retry(endpoint)

            # Extract properties
            props = {}
            prop_list = data.get("PropertyTable", {}).get("Properties", [])
            if prop_list:
                props = prop_list[0]

            # Cache result
            await self._set_cached(cache_key, props)

            return props
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return {}
            raise


class PubChemAPIError(Exception):
    """Exception raised for PubChem API errors."""

    pass
