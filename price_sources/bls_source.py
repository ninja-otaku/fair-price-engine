"""
BLS (Bureau of Labor Statistics) labor rate source — v1.1 STUB.

STUB: fetch() raises NotImplementedError. Documents the implementation path.

──────────────────────────────────────────────────────────────────
v1.1 IMPLEMENTATION GUIDE
──────────────────────────────────────────────────────────────────
1. Get a free API key: https://data.bls.gov/registrationEngine/
   Set: BLS_API_KEY=your_key_here in .env

2. Endpoint:
   POST https://api.bls.gov/publicAPI/v2/timeseries/data/
   Body: { "seriesid": [...], "startyear": "2025", "endyear": "2026",
           "registrationkey": api_key }

3. Useful series IDs for labor cost grounding:
   CEU2000000003  — Construction avg hourly earnings       → home_repair
   CEU3000000003  — Manufacturing avg hourly earnings      → furniture/appliances
   CEU6500000003  — Retail trade avg hourly earnings       → apparel
   CMU2000000000000D — Construction employment cost index  → overhead

4. Wire into decomposer.py (v1.1):
   When GROUNDING_MODE=live, decomposer substitutes BLS labor rates
   into the "manufacturing" BOM line item and sets data_source="live-bls".

──────────────────────────────────────────────────────────────────
"""
from datetime import timedelta
from price_sources.base_source import BasePriceSource

BLS_SERIES = {
    "construction_labor":  "CEU2000000003",
    "manufacturing_labor": "CEU3000000003",
    "retail_labor":        "CEU6500000003",
}


class BLSSource(BasePriceSource):
    source_name = "BLS"
    cache_ttl   = timedelta(days=1)

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def fetch(self, series: str) -> dict:
        """
        v1.1: call BLS API, return { value, unit, date, source }.

        Example implementation:
            import httpx
            series_id = BLS_SERIES[series]
            resp = await self._client.post(
                "https://api.bls.gov/publicAPI/v2/timeseries/data/",
                json={"seriesid": [series_id], "startyear": "2025",
                      "endyear": "2026", "registrationkey": self._api_key}
            )
            data = resp.json()["Results"]["series"][0]["data"][0]
            return { "value": float(data["value"]), "unit": "$/hr",
                     "date": f"{data['year']}-{data['periodName']}",
                     "source": "BLS" }
        """
        raise NotImplementedError(
            f"BLS source not yet activated. "
            f"See price_sources/bls_source.py for implementation guide. "
            f"Set GROUNDING_MODE=live in v1.1."
        )
