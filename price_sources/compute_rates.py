"""
Compute rate provider. MVP uses hardcoded FALLBACK_RATES.
v1.1 will activate fetch_live_rates() with PriceCache caching.

MVP Rates Table (March 2026):
  Source            | Rate                  | Where to verify
  ------------------|----------------------|---------------------------
  Anthropic         | $3.00 / 1M out tok   | anthropic.com/pricing
  OpenAI            | $5.00 / 1M out tok   | openai.com/pricing
  Community bench   | $0.10 / 1M tok       | electricitymaps.com/blog
  Lambda Cloud      | $2.49 / H100-hr      | lambdalabs.com/service/gpu-cloud
  vast.ai           | $0.35 / 4090-hr      | vast.ai (spot median)
  Derived           | $0.0015 / convo      | 500 tok * $3/1M
  Midjourney API    | $0.02 / image        | docs.midjourney.com
  GitHub Copilot    | $0.001 / completion  | github.com/features/copilot/plans
"""
import logging

logger = logging.getLogger(__name__)

FALLBACK_RATES: dict[str, float] = {
    "claude_sonnet_per_1m_tokens": 3.00,
    "gpt4o_per_1m_tokens":         5.00,
    "local_llama_per_1m_tokens":   0.10,
    "h100_per_hour":               2.49,
    "rtx4090_per_hour":            0.35,
    "ai_conversation":             0.0015,
    "ai_image_gen":                0.02,
    "ai_code_completion":          0.001,
}


def get_rates(live: bool = False) -> dict:
    """
    Returns compute rates dict.
    MVP always returns FALLBACK_RATES.
    Set live=True in v1.1 to enable scraping (see fetch_live_rates below).
    """
    if live:
        raise NotImplementedError(
            "Live rate fetching requires v1.1. Set GROUNDING_MODE=llm for MVP."
        )
    return FALLBACK_RATES.copy()


async def fetch_live_rates() -> dict:
    """
    v1.1 IMPLEMENTATION TARGET
    ──────────────────────────
    Scrape current rates from provider pricing pages and return a dict
    matching the FALLBACK_RATES schema.

    Suggested sources:
      - Anthropic : https://www.anthropic.com/pricing (parse table)
      - OpenAI    : https://openai.com/pricing
      - Lambda    : https://lambdalabs.com/service/gpu-cloud/pricing
      - vast.ai   : https://vast.ai/api/v0/bundles/?gpu_name=RTX_4090

    Cache result in PriceCache with TTL=7 days.

    Example skeleton:
        import httpx
        from price_sources.cache import PriceCache
        _cache = PriceCache()

        async def fetch_live_rates() -> dict:
            cached = _cache.get("compute_rates")
            if cached:
                return cached
            rates = FALLBACK_RATES.copy()
            async with httpx.AsyncClient() as c:
                # TODO: parse each pricing page
                pass
            _cache.set("compute_rates", rates, ttl=7*86400)
            return rates
    """
    raise NotImplementedError("See v1.1 roadmap — implement fetch_live_rates()")
