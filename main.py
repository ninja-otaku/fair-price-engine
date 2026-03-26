import base64
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, File, Form, Query, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request

from config import settings
from engine.compute_converter import dual_convert
from engine.decomposer import CostDecomposer
from engine.identifier import ItemIdentification, ItemIdentifier
from engine import reporter

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Singletons
# ---------------------------------------------------------------------------

_identifier:  Optional[ItemIdentifier]  = None
_decomposer:  Optional[CostDecomposer]  = None

# In-memory leaderboard — stateless (resets on restart), capped at 100 entries.
# Entries sorted descending by markup_tokens.
# Client submits anonymously after each successful analysis.
_leaderboard: list[dict] = []
_LEADERBOARD_CAP = 100
_LEADERBOARD_TOP = 20


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _identifier, _decomposer
    _identifier = ItemIdentifier(host=settings.OLLAMA_HOST, model=settings.IDENTIFIER_MODEL)
    _decomposer = CostDecomposer(
        host=settings.OLLAMA_HOST,
        model=settings.DECOMPOSER_MODEL,
        grounding_mode=settings.GROUNDING_MODE,
    )
    yield
    await _identifier.close()
    await _decomposer.close()


app = FastAPI(title="Fair Price Engine", version="1.0.0", lifespan=lifespan)
_STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")


# ---------------------------------------------------------------------------
# GET / — serve index.html with dynamic og:image injection
#
# When ?result=BASE64 is present, inject og:image meta tags pointing to
# /og-image?data=BASE64 so Twitter/Discord crawlers render the card.
# Crawlers don't run JS, so this server-side injection is required.
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
async def index(request: Request, result: Optional[str] = Query(default=None)) -> HTMLResponse:
    html = (_STATIC / "index.html").read_text(encoding="utf-8")
    if result:
        og_url  = f"{str(request.base_url).rstrip('/')}//og-image?data={result}"
        og_meta = (
            f'  <meta property="og:type"        content="website" />\n'
            f'  <meta property="og:title"       content="Fair Price Engine" />\n'
            f'  <meta property="og:description" content="See any product price in Claude tokens. The markup number will surprise you." />\n'
            f'  <meta property="og:image"       content="{og_url}" />\n'
            f'  <meta name="twitter:card"       content="summary_large_image" />\n'
            f'  <meta name="twitter:image"      content="{og_url}" />\n'
        )
        html = html.replace("</head>", og_meta + "  </head>")
    return HTMLResponse(html)


# ---------------------------------------------------------------------------
# POST /analyze — main pipeline endpoint
#
# Confidence gate logic:
#   1. Identify image → ItemIdentification (with confidence 0–1)
#   2. If confidence < CONFIDENCE_THRESHOLD AND NOT autoconfirm AND NOT item_json:
#      → return HTTP 202 { gate: true, item: {...} }
#      → frontend shows "Looks like X. Confirm?" interstitial
#      → user confirms (or edits name) → frontend resubmits with item_json
#   3. Full pipeline: decompose → dual_convert → reporter.to_response()
#
# ?autoconfirm=1 bypasses step 2 entirely (e.g. programmatic use).
# ---------------------------------------------------------------------------

@app.post("/analyze")
async def analyze(
    image:        UploadFile          = File(default=None),
    retail_price: float               = Form(...),
    item_json:    Optional[str]       = Form(default=None),   # pre-confirmed ItemIdentification
    autoconfirm:  bool                = Query(default=False),
) -> JSONResponse:

    # ── 1. Identification ─────────────────────────────────────────────────
    if item_json:
        # User confirmed (possibly with edited name) — trust it
        item = ItemIdentification(**json.loads(item_json))
    elif image:
        image_bytes = await image.read()
        assert _identifier is not None
        item = await _identifier.identify(image_bytes)
    else:
        return JSONResponse({"error": "Provide image or item_json"}, status_code=422)

    # ── 2. Confidence gate ────────────────────────────────────────────────
    if (
        item.confidence < settings.CONFIDENCE_THRESHOLD
        and not autoconfirm
        and not item_json
    ):
        logger.info(
            "Confidence gate triggered: %s (conf=%.2f < threshold=%.2f)",
            item.name, item.confidence, settings.CONFIDENCE_THRESHOLD,
        )
        return JSONResponse(
            status_code=202,
            content={
                "gate":    True,
                "item":    item.to_dict(),
                "message": f"Looks like a {item.name}. Please confirm before we run the analysis.",
            },
        )

    # ── 3. Full pipeline ──────────────────────────────────────────────────
    assert _decomposer is not None
    breakdown = await _decomposer.decompose(item, retail_price)
    dual      = dual_convert(retail_price, breakdown.fair_price_mid)
    response  = reporter.to_response(breakdown, dual)
    summary   = reporter.to_share_summary(breakdown, dual)

    # Encode share URL
    share_b64  = base64.b64encode(json.dumps(summary).encode()).decode()
    response["share_b64"]  = share_b64
    response["share_url"]  = f"/?result={share_b64}"
    response["og_image_url"] = f"/og-image?data={share_b64}"

    logger.info(
        "Analysis complete: %s | retail=$%.0f fair=$%.0f overpay=%.1f%%",
        item.name, retail_price, breakdown.fair_price_mid, breakdown.overpay_pct,
    )
    return JSONResponse(response)


# ---------------------------------------------------------------------------
# GET /og-image?data=BASE64 — serve PNG for Twitter/Discord og:image
# ---------------------------------------------------------------------------

@app.get("/og-image")
async def og_image(data: str = Query(...)) -> Response:
    try:
        summary = json.loads(base64.b64decode(data.encode()).decode())
        png     = reporter.to_og_image_png(summary)
        return Response(content=png, media_type="image/png",
                        headers={"Cache-Control": "public, max-age=86400"})
    except Exception as exc:
        logger.error("og-image error: %s", exc)
        return Response(status_code=400)


# ---------------------------------------------------------------------------
# Leaderboard — in-memory, stateless, client-contributed
#
# After each successful analysis, the frontend anonymously POSTs the key
# numbers. No PII, no session tracking. Resets on server restart.
# "Hall of shame" for the most overpriced items scanned.
# ---------------------------------------------------------------------------

@app.get("/leaderboard")
async def get_leaderboard() -> JSONResponse:
    top = sorted(_leaderboard, key=lambda x: x["markup_tokens"], reverse=True)
    return JSONResponse({
        "entries":       top[:_LEADERBOARD_TOP],
        "total_scanned": len(_leaderboard),
    })


@app.post("/leaderboard")
async def add_leaderboard(entry: dict) -> JSONResponse:
    required = {"item_name", "retail_price", "markup_tokens", "overpay_pct"}
    if not required.issubset(entry):
        return JSONResponse({"error": "Missing required fields"}, status_code=422)

    _leaderboard.append({
        "item_name":    str(entry["item_name"])[:80],
        "retail_price": float(entry["retail_price"]),
        "markup_tokens": int(entry["markup_tokens"]),
        "overpay_pct":  float(entry["overpay_pct"]),
    })

    # Cap size — keep the highest-markup entries
    if len(_leaderboard) > _LEADERBOARD_CAP:
        _leaderboard.sort(key=lambda x: x["markup_tokens"], reverse=True)
        del _leaderboard[_LEADERBOARD_CAP:]

    return JSONResponse({"ok": True, "total": len(_leaderboard)})


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({
        "status":         "ok",
        "grounding_mode": settings.GROUNDING_MODE,
        "identifier":     settings.IDENTIFIER_MODEL,
        "decomposer":     settings.DECOMPOSER_MODEL,
        "leaderboard_entries": len(_leaderboard),
    })


# ---------------------------------------------------------------------------
# Entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    ssl_kwargs: dict = {}
    if settings.TLS_ENABLED:
        ssl_kwargs = {"ssl_certfile": settings.TLS_CERT_PATH, "ssl_keyfile": settings.TLS_KEY_PATH}
    uvicorn.run("main:app", host="0.0.0.0", port=settings.PORT, reload=False, **ssl_kwargs)
