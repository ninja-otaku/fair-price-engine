"""
engine/reporter.py — Format engine output for API consumers and sharing.

  to_response()       → full JSON dict served by /analyze
  to_share_summary()  → compact dict safe to base64-encode into a URL
  to_og_image_png()   → 1200x630 PNG for og:image Twitter/Discord preview

The share URL pattern:
  /?result=<base64(json.dumps(to_share_summary()))>

When a crawler fetches that URL, main.py injects:
  <meta property="og:image" content="/og-image?data=<same_base64>" />

/og-image calls to_og_image_png() → returns the PNG so Twitter renders
the token markup card directly in the preview.
"""
import io
import logging
from typing import Any

from engine.decomposer import CostBreakdown
from engine.compute_converter import DualConversion, _fmt_tokens

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# JSON response formatters
# ---------------------------------------------------------------------------

def to_response(breakdown: CostBreakdown, dual: DualConversion) -> dict:
    """Full response dict — consumed by the frontend results card."""
    return {
        "item":      breakdown.item.to_dict(),
        "breakdown": {
            "retail_price":    breakdown.retail_price,
            "fair_price_low":  breakdown.fair_price_low,
            "fair_price_mid":  breakdown.fair_price_mid,
            "fair_price_high": breakdown.fair_price_high,
            "overpay_amount":  breakdown.overpay_amount,
            "overpay_pct":     breakdown.overpay_pct,
            "margin_pct":      round(breakdown.margin_pct * 100, 1),
            "reasoning":       breakdown.reasoning,
            "data_source":     breakdown.data_source,
            "confidence":      breakdown.confidence,
            "bom": [
                {
                    "component":   b.component,
                    "cost":        b.cost,
                    "pct_of_cost": round(b.pct_of_cost * 100, 1),
                }
                for b in breakdown.bom
            ],
        },
        "dual": dual.to_dict(),
        "viral_quote": _viral_quote(breakdown, dual),
    }


def to_share_summary(breakdown: CostBreakdown, dual: DualConversion) -> dict:
    """
    Compact representation for base64 URL encoding.
    Keys are abbreviated to minimise URL length.
    Decompressed by the frontend on page load.
    """
    return {
        "n":   breakdown.item.name,
        "cat": breakdown.item.category,
        "r":   breakdown.retail_price,
        "f":   breakdown.fair_price_mid,
        "op":  breakdown.overpay_pct,
        "oa":  breakdown.overpay_amount,
        "bom": [[b.component, round(b.cost, 2), round(b.pct_of_cost * 100, 1)]
                for b in breakdown.bom],
        # Token counts — the viral numbers
        "rc":  dual.retail_equiv.claude_tokens,
        "fc":  dual.fair_equiv.claude_tokens,
        "mc":  dual.markup_equiv.claude_tokens,
        # Supporting equivalents
        "cv":  dual.retail_equiv.ai_conversations,
        "h":   dual.retail_equiv.h100_hours,
        "img": dual.retail_equiv.ai_image_gens,
        "ctx": dual.retail_equiv.context_str,
        "rd":  dual.retail_equiv.rates_date,
        "vq":  _viral_quote(breakdown, dual),
    }


def _viral_quote(breakdown: CostBreakdown, dual: DualConversion) -> str:
    """The shareable sentence — the most memorable number on the card."""
    mt = _fmt_tokens(dual.markup_equiv.claude_tokens)
    return (
        f"You’re being charged {mt} extra Claude tokens for this "
        f"{breakdown.item.name}."
    )


# ---------------------------------------------------------------------------
# og:image PNG generator (1200x630)
# ---------------------------------------------------------------------------

# BOM bar colors — cycles through this palette
_BAR_COLORS = ["#7ec8e3", "#a78bfa", "#fb923c", "#f87171", "#4ade80", "#facc15"]

def to_og_image_png(summary: dict) -> bytes:
    """
    Generate a 1200x630 PNG for og:image meta.
    Uses Pillow only — no external services.

    Gracefully degrades to a plain-text fallback card if fonts are unavailable.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
        return _draw_card(Image, ImageDraw, ImageFont, summary)
    except Exception as exc:
        logger.error("og:image generation failed: %s", exc)
        return _fallback_png(summary)


def _load_font(ImageFont, size: int, bold: bool = False):
    candidates = [
        # Windows
        (r"C:\Windows\Fontsrialbd.ttf" if bold else r"C:\Windows\Fontsrial.ttf"),
        (r"C:\Windows\Fonts\segoeuib.ttf" if bold else r"C:\Windows\Fonts\segoeui.ttf"),
        # Linux
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


def _draw_card(Image, ImageDraw, ImageFont, s: dict) -> bytes:
    W, H = 1200, 630
    img  = Image.new("RGB", (W, H), "#0d0d0d")
    d    = ImageDraw.Draw(img)

    # Fonts
    f_xs  = _load_font(ImageFont, 20)
    f_sm  = _load_font(ImageFont, 26)
    f_md  = _load_font(ImageFont, 34)
    f_lg  = _load_font(ImageFont, 48, bold=True)
    f_xl  = _load_font(ImageFont, 58, bold=True)

    # Colors
    BG      = "#0d0d0d"
    WHITE   = "#e2e2e2"
    MUTED   = "#666666"
    GREEN   = "#4ade80"
    RED     = "#f87171"
    YELLOW  = "#facc15"
    ACCENT  = "#7ec8e3"
    BORDER  = "#252525"

    # ── Brand header ──────────────────────────────────────────────
    d.text((60, 36), "fair-price-engine", fill=ACCENT, font=f_sm)
    d.text((60, 70), _trunc(s.get("n", "item"), 44), fill=WHITE, font=f_lg)

    # Separator
    d.line([(60, 138), (1140, 138)], fill=BORDER, width=2)

    # ── Three-row token table ─────────────────────────────────────
    retail = s.get("r", 0)
    fair   = s.get("f", 0)
    markup = retail - fair
    rc  = _fmt_tokens(s.get("rc", 0))
    fc  = _fmt_tokens(s.get("fc", 0))
    mc  = _fmt_tokens(s.get("mc", 0))

    col_label = 60
    col_price = 340
    col_arrow = 490
    col_token = 560

    # Row 1 — RETAIL
    d.text((col_label, 158), "RETAIL PRICE", fill=MUTED,  font=f_xs)
    d.text((col_price, 180), f"${retail:.0f}", fill=WHITE, font=f_md)
    d.text((col_arrow, 180), "→", fill=MUTED, font=f_md)
    d.text((col_token, 180), f"{rc} tokens", fill=WHITE, font=f_md)

    # Row 2 — FAIR
    d.text((col_label, 238), "FAIR PRICE",   fill=MUTED,  font=f_xs)
    d.text((col_price, 258), f"${fair:.0f}", fill=GREEN,  font=f_md)
    d.text((col_arrow, 258), "→", fill=MUTED, font=f_md)
    d.text((col_token, 258), f"{fc} tokens", fill=GREEN, font=f_md)

    # Row 3 — MARKUP (highlighted box)
    d.rectangle([(44, 318), (1156, 406)], fill="#1a0505")
    d.rectangle([(44, 318), (1156, 406)], outline="#4a1010", width=1)
    d.text((col_label, 324), "MARKUP",       fill=MUTED, font=f_xs)
    d.text((col_price, 340), f"${markup:.0f}", fill=RED, font=f_md)
    d.text((col_arrow, 340), "→", fill=MUTED, font=f_md)
    d.text((col_token, 340), f"{mc} tokens", fill=RED, font=f_md)

    # ── Viral quote ───────────────────────────────────────────────
    quote = s.get("vq", f"You're paying {mc} extra tokens for this item.")
    # Word-wrap at ~72 chars
    words, lines, line = quote.split(), [], ""
    for w in words:
        if len(line) + len(w) + 1 > 72:
            lines.append(line.strip()); line = ""
        line += w + " "
    if line:
        lines.append(line.strip())
    y_q = 422
    for ln in lines[:2]:
        d.text((60, y_q), ln, fill=WHITE, font=f_sm)
        y_q += 34

    # ── Bottom bar ────────────────────────────────────────────────
    d.line([(60, 548), (1140, 548)], fill=BORDER, width=1)
    op = s.get("op", 0)
    d.text((60, 566), f"overpaying {op:.0f}%", fill=YELLOW, font=f_md)
    d.text((700, 574), "github.com/ninja-otaku/fair-price-engine", fill=MUTED, font=f_xs)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _fallback_png(summary: dict) -> bytes:
    """Minimal white-on-dark PNG when fonts fail."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (1200, 630), "#0d0d0d")
    d   = ImageDraw.Draw(img)
    d.text((60, 60),  summary.get("n", "item"),              fill="#e2e2e2")
    d.text((60, 120), f"Retail: ${summary.get('r', 0):.0f}", fill="#e2e2e2")
    d.text((60, 160), f"Fair:   ${summary.get('f', 0):.0f}", fill="#4ade80")
    d.text((60, 200), f"You're overpaying {summary.get('op', 0):.0f}%", fill="#f87171")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _trunc(s: str, n: int) -> str:
    return s if len(s) <= n else s[:n - 1] + "…"
