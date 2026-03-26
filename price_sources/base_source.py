"""Abstract base for all price data sources."""
from abc import ABC, abstractmethod
from datetime import timedelta


class BasePriceSource(ABC):
    source_name: str = "unknown"
    cache_ttl: timedelta = timedelta(days=7)

    @abstractmethod
    async def fetch(self, commodity: str) -> dict:
        """
        Fetch current price data for a commodity identifier.

        Returns dict with at minimum:
          { "value": float, "unit": str, "date": str, "source": str }

        Raises NotImplementedError in stubs.
        Raises httpx.HTTPError on network failures.
        """

    async def close(self) -> None:
        pass
