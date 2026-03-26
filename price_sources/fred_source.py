"""
FRED (Federal Reserve Economic Data) price source — v1.1 STUB.

STUB: fetch() raises NotImplementedError. This file defines the interface
and documents exactly how to implement it. Activate via GROUNDING_MODE=live.

──────────────────────────────────────────────────────────────────
v1.1 IMPLEMENTATION GUIDE
──────────────────────────────────────────────────────────────────
1. Get a free API key: https://fred.stlouisfed.org/docs/api/api_key.html
   Set: FRED_API_KEY=your_key_here in .env

2. Endpoint:
   GET https://api.stlouisfed.org/fred/series/observations
   Params: series_id, api_key, sort_order=desc, limit=1, file_type=json

3. Useful series IDs for BOM cost grounding:
   WPU0811    — Wood products (softwood lumber)        → furniture
   WPU101     — Iron and steel mill products           → appliances
   WPU1021    — Copper and brass                      → plumbing
   WPU0561    — Cotton                                → apparel
   PCUOMFGOMFG — Manufacturing overhead               → general

4. Wire into decomposer.py (v1.1):
   When GROUNDING_MODE=live, decomposer fetches commodity prices from
   FRED, substitutes them into the BOM "materials" cost calculation,
   and sets data_source="live-fred".

──────────────────────────────────────────────────────────────────
"""
from datetime import timedelta
from price_sources.base_source import BasePriceSource

# Series → human label map (documents what this source covers)
FRED_SERIES = {
    "lumber":     "WPU0811",
    "steel":      "WPU101",
    "copper":     "WPU1021",
    "cotton":     "WPU0561",
}


class FREDSource(BasePriceSource):
    source_name = "FRED"
    cache_ttl   = timedelta(days=1)   # commodity prices change daily

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        # import httpx here in v1.1

    async def fetch(self, commodity: str) -> dict:
        """
        v1.1: call FRED API, return { value, unit, date, source }.

        Example implementation:
            series_id = FRED_SERIES[commodity]
            url = (
                "https://api.stlouisfed.org/fred/series/observations"
                f"?series_id={series_id}&api_key={self._api_key}"
                "&sort_order=desc&limit=1&file_type=json"
            )
            resp = await self._client.get(url)
            obs  = resp.json()["observations"][0]
            return { "value": float(obs["value"]), "unit": "index",
                     "date": obs["date"], "source": "FRED" }
        """
        raise NotImplementedError(
            f"FRED source not yet activated. "
            f"See price_sources/fred_source.py for implementation guide. "
            f"Set GROUNDING_MODE=live in v1.1."
        )
