"""
ATC Lookup Orchestrator for DrugTree
Orchestrates ATC code lookups from multiple sources with caching
"""

import asyncio
import aiohttp
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta
from dataclasses import dataclass


class ATCLookupError(Exception):
    pass


class ATCNotFoundError(ATCLookupError):
    pass


@dataclass
class ATCCode:
    code: str
    name: str
    level1: str
    level2: str
    level3: str
    level4: str
    level5: str
    level1_name: str
    level2_name: Optional[str] = None
    level3_name: Optional[str] = None
    level4_name: Optional[str] = None
    level5_name: Optional[str] = None
    who_url: Optional[str] = None
    chembl_id: Optional[str] = None
    source: str = "who"
    confidence: float = 1.0


class ATCOrchestrator:
    WHO_ATC_URL = "https://www.whocc.no/api/atc"
    WHO_ATC_SEARCH_URL = "https://www.whocc.no/api/atc/search"
    CHEMBL_URL = "https://www.ebi.ac.uk/chembl/api/data"
    CACHE_TTL_HOURS = 24
    RATE_LIMIT = 5
    RATE_WINDOW = 1.0

    def __init__(self, cache_dir: Optional[str] = None, request_timeout: float = 30.0):
        self.session: Optional[aiohttp.ClientSession] = None
        self.request_timeout = request_timeout
        self._cache: Dict[str, tuple[Any, datetime]] = {}
        self._cache_dir = cache_dir
        self._request_times: List[float] = []
        self._rate_limit_lock = asyncio.Lock()

        self._level1_categories: Dict[str, str] = {
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

    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=self.request_timeout)
        self.session = aiohttp.ClientSession(timeout=timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
            self.session = None

    async def _enforce_rate_limit(self):
        async with self._rate_limit_lock:
            import time

            now = time.time()
            self._request_times = [
                t for t in self._request_times if now - t < self.RATE_WINDOW
            ]
            if len(self._request_times) >= self.RATE_LIMIT:
                sleep_time = self.RATE_WINDOW - (now - self._request_times[0])
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
            self._request_times.append(time.time())

    def _get_cache_key(self, query_type: str, identifier: str) -> str:
        return f"atc:{query_type}:{identifier}"

    async def _get_cached(self, cache_key: str) -> Optional[Any]:
        if cache_key in self._cache:
            data, timestamp = self._cache[cache_key]
            if datetime.now() - timestamp < timedelta(hours=self.CACHE_TTL_HOURS):
                return data
            del self._cache[cache_key]
        return None

    async def _set_cache(self, cache_key: str, data: Any):
        self._cache[cache_key] = (data, datetime.now())

    def _parse_atc_code(self, code: str) -> ATCCode:
        if not code or len(code) < 1:
            raise ValueError(f"Invalid ATC code: {code}")

        code = code.upper().strip()
        level1 = code[0] if len(code) >= 1 else ""
        level2 = code[1:3] if len(code) >= 3 else ""
        level3 = code[1:4] if len(code) >= 4 else ""
        level4 = code[1:5] if len(code) >= 5 else ""
        level5 = code[1:7] if len(code) >= 7 else ""

        return ATCCode(
            code=code,
            name="",
            level1=level1,
            level2=level2,
            level3=level3,
            level4=level4,
            level5=level5,
            level1_name=self._level1_categories.get(level1, ""),
            source="who",
            confidence=1.0,
        )

    async def lookup(self, drug_name: str) -> Optional[ATCCode]:
        cache_key = self._get_cache_key("name", drug_name.lower())
        cached = await self._get_cached(cache_key)
        if cached:
            return cached

        await self._enforce_rate_limit()
        atc_code = await self._lookup_who(drug_name)

        if atc_code:
            await self._set_cache(cache_key, atc_code)
            return atc_code

        atc_code = await self._lookup_chembl(drug_name)
        if atc_code:
            atc_code.source = "chembl"
            atc_code.confidence = 0.0
            await self._set_cache(cache_key, atc_code)
            return atc_code

        return None

    async def lookup_by_class(
        self, drug_class: str, level1_hint: Optional[str] = None
    ) -> Optional[ATCCode]:
        cache_key = self._get_cache_key("class", f"{drug_class}:{level1_hint or ''}")
        cached = await self._get_cached(cache_key)
        if cached:
            return cached

        if not level1_hint:
            drug_class_lower = drug_class.lower()
            class_to_atc = {
                "statin": "C",
                "hmg-coa reductase inhibitor": "C",
                "beta blocker": "C",
                "ace inhibitor": "C",
                "arb": "C",
                "calcium channel blocker": "C",
                "diuretic": "C",
                "antibiotic": "J",
                "penicillin": "J",
                "cephalosporin": "J",
                "quinolone": "J",
                "proton pump inhibitor": "A",
                "ppi": "A",
                "nsaid": "M",
                "cox-2 inhibitor": "M",
                "opioid": "N",
                "benzodiazepine": "N",
                "ssri": "N",
                "antidepressant": "N",
                "antipsychotic": "N",
                "corticosteroid": "H",
                "insulin": "H",
                "antihistamine": "R",
                "bronchodilator": "R",
                "antineoplastic": "L",
                "chemotherapy": "L",
            }
            level1_hint = class_to_atc.get(drug_class_lower)

        if level1_hint:
            atc_code = ATCCode(
                code=level1_hint,
                name=drug_class,
                level1=level1_hint,
                level2="",
                level3="",
                level4="",
                level5="",
                level1_name=self._level1_categories.get(level1_hint, ""),
                source="inferred",
                confidence=0.5,
            )
            await self._set_cache(cache_key, atc_code)
            return atc_code

        return None

    async def search(self, query: str) -> List[ATCCode]:
        cache_key = self._get_cache_key("search", query.lower())
        cached = await self._get_cached(cache_key)
        if cached:
            return cached

        await self._enforce_rate_limit()
        results = await self._search_who(query)

        if results:
            await self._set_cache(cache_key, results)
            return results

        return []

    async def _lookup_who(self, drug_name: str) -> Optional[ATCCode]:
        if not self.session:
            raise RuntimeError("Session not initialized. Use async with.")

        try:
            url = self.WHO_ATC_SEARCH_URL
            params = {"q": drug_name, "limit": 5}

            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()

                    if "records" in data and len(data["records"]) > 0:
                        record = data["records"][0]
                        atc_code_str = record.get("code", record.get("atc_code", ""))

                        if atc_code_str:
                            atc_code = self._parse_atc_code(atc_code_str)
                            atc_code.name = drug_name
                            atc_code.who_url = f"https://www.whocc.no/atc_ddd_index/?code={atc_code_str}"
                            return atc_code

                    return None
                return None
        except aiohttp.ClientError:
            return None

    async def _lookup_chembl(self, drug_name: str) -> Optional[ATCCode]:
        if not self.session:
            raise RuntimeError("Session not initialized. Use async with.")

        try:
            url = f"{self.CHEMBL_URL}/molecule/search"
            params = {"q": drug_name, "limit": 1}

            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()

                    if "molecules" in data and len(data["molecules"]) > 0:
                        molecule = data["molecules"][0]
                        atc_classifications = molecule.get("atc_classifications", [])

                        if atc_classifications and len(atc_classifications) > 0:
                            atc_data = atc_classifications[0]
                            atc_code_str = atc_data.get(
                                "level5", atc_data.get("code", "")
                            )

                            if atc_code_str:
                                atc_code = self._parse_atc_code(atc_code_str)
                                atc_code.name = drug_name
                                atc_code.chembl_id = molecule.get("molecule_chembl_id")
                                return atc_code

                    return None
                return None
        except aiohttp.ClientError:
            return None

    async def _search_who(self, query: str) -> List[ATCCode]:
        if not self.session:
            raise RuntimeError("Session not initialized. Use async with.")

        try:
            url = self.WHO_ATC_SEARCH_URL
            params = {"q": query, "limit": 20}

            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    results = []

                    if "records" in data:
                        for record in data["records"]:
                            atc_code_str = record.get(
                                "code", record.get("atc_code", "")
                            )
                            if atc_code_str:
                                atc_code = self._parse_atc_code(atc_code_str)
                                atc_code.name = record.get("name", "")
                                atc_code.who_url = f"https://www.whocc.no/atc_ddd_index/?code={atc_code_str}"
                                results.append(atc_code)

                    return results
                return []
        except aiohttp.ClientError:
            return []

    async def validate_atc_code(self, code: str) -> tuple[bool, str]:
        try:
            atc_code = self._parse_atc_code(code)
            if atc_code.level1 not in self._level1_categories:
                return True, ""
            return False, f"Invalid level 1 code: {atc_code.level1}"
        except ValueError as e:
            return False, str(e)

    def get_level1_name(self, level1: str) -> str:
        return self._level1_categories.get(level1.upper(), "")

    def get_all_level1_categories(self) -> Dict[str, str]:
        return self._level1_categories.copy()


async def lookup_atc(drug_name: str) -> Optional[ATCCode]:
    async with ATCOrchestrator() as orchestrator:
        return await orchestrator.lookup(drug_name)


async def lookup_atc_by_class(
    drug_class: str, level1_hint: Optional[str] = None
) -> Optional[ATCCode]:
    async with ATCOrchestrator() as orchestrator:
        return await orchestrator.lookup_by_class(drug_class, level1_hint)


async def search_atc(query: str) -> List[ATCCode]:
    async with ATCOrchestrator() as orchestrator:
        return await orchestrator.search(query)


async def validate_atc(code: str) -> tuple[bool, str]:
    async with ATCOrchestrator() as orchestrator:
        return await orchestrator.validate_atc_code(code)
