"""Shared US-state geo block for GeneMeal (genetics + meal-plan app).

Enable with GEO_BLOCK_ENABLED=1. Off by default.
The block applies only to genome upload, results, and billing routes.
Content pages, robots.txt, sitemap.xml, and static assets stay available in every state.
IP→state uses ip-api.com (free, no key). Raw IPs are never logged — only the resolved state code on deny.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path
from typing import Optional

import site_meta

# USPS codes — states with consumer genetic privacy / health-data genetic rules (research Nov 2026).
BLOCKED_STATES = frozenset({
    "AL",  # Alabama Genetic Data Privacy Act
    "AZ",  # Arizona HB 2069
    "CA",  # California Genetic Information Privacy Act
    "CT",  # Connecticut genetic / DTC genetic privacy (SB 4 / P.A. 26-64)
    "FL",  # Florida DNA / lab rules
    "IL",  # Illinois GIPA
    "IN",  # Indiana HEA 1521
    "KY",  # Kentucky Genetic Information Privacy Act
    "MD",  # Maryland SB 187
    "MN",  # Minnesota Genetic Information Privacy Act (§325F.995)
    "MT",  # Montana Genetic Information Privacy Act
    "NE",  # Nebraska LB 308
    "RI",  # Rhode Island Genetic Information Privacy Act
    "SD",  # South Dakota SB 49
    "TN",  # Tennessee Genetic Information Privacy Act
    "TX",  # Texas DTC + HB 130
    "UT",  # Utah Genetic Information Privacy Act
    "VA",  # Virginia genetic privacy
    "VT",  # Vermont Act 135
    "WA",  # Washington My Health My Data (includes genetic)
    "WY",  # Wyoming HB 86
})


# Display names + statute citations + public text links for the 451 alert page.
# URLs point at official or primary bill/statute pages (not legal advice).
STATE_LAWS: dict[str, dict[str, str]] = {
    "AL": {
        "name": "Alabama",
        "statute": "Genetic Data Privacy Act",
        "url": "https://legiscan.com/AL/bill/HB226/2024",
    },
    "AZ": {
        "name": "Arizona",
        "statute": "Genetic testing privacy law (HB 2069)",
        "url": "https://legiscan.com/AZ/bill/HB2069/2024",
    },
    "CA": {
        "name": "California",
        "statute": "Genetic Information Privacy Act (Cal. Civ. Code §§ 56.18 et seq.)",
        "url": "https://leginfo.legislature.ca.gov/faces/codes_displayText.xhtml?lawCode=CIV&division=1.&title=1.81.48.&part=2.6.&chapter=&article=",
    },
    "CT": {
        "name": "Connecticut",
        "statute": "Genetic privacy / DTC genetic testing law (P.A. 23-167 / related acts)",
        "url": "https://www.cga.ct.gov/",
    },
    "FL": {
        "name": "Florida",
        "statute": "DNA privacy and genetic specimen protections",
        "url": "http://www.leg.state.fl.us/statutes/",
    },
    "IL": {
        "name": "Illinois",
        "statute": "Genetic Information Privacy Act (410 ILCS 513)",
        "url": "https://www.ilga.gov/legislation/ilcs/ilcs3.asp?ActID=1456&ChapterID=35",
    },
    "IN": {
        "name": "Indiana",
        "statute": "Genetic privacy law (HEA 1521)",
        "url": "https://legiscan.com/IN/bill/HB1521/2023",
    },
    "KY": {
        "name": "Kentucky",
        "statute": "Genetic Information Privacy Act",
        "url": "https://legiscan.com/KY/bill/HB502/2023",
    },
    "MD": {
        "name": "Maryland",
        "statute": "Genetic privacy law (SB 187 / related)",
        "url": "https://mgaleg.maryland.gov/",
    },
    "MN": {
        "name": "Minnesota",
        "statute": "Genetic Information Privacy Act (Minn. Stat. § 325F.995)",
        "url": "https://www.revisor.mn.gov/statutes/cite/325F.995",
    },
    "MT": {
        "name": "Montana",
        "statute": "Genetic Information Privacy Act",
        "url": "https://legiscan.com/MT/bill/HB868/2023",
    },
    "NE": {
        "name": "Nebraska",
        "statute": "Genetic Information Privacy Act (LB 308)",
        "url": "https://nebraskalegislature.gov/bills/view_bill.php?DocumentID=50428",
    },
    "RI": {
        "name": "Rhode Island",
        "statute": "Genetic Information Privacy Act",
        "url": "https://legiscan.com/RI/bill/H7123/2024",
    },
    "SD": {
        "name": "South Dakota",
        "statute": "Genetic information privacy law (SB 49)",
        "url": "https://legiscan.com/SD/bill/SB49/2023",
    },
    "TN": {
        "name": "Tennessee",
        "statute": "Genetic Information Privacy Act",
        "url": "https://legiscan.com/TN/bill/HB0880/2023",
    },
    "TX": {
        "name": "Texas",
        "statute": "Genetic privacy / DTC genetic testing law (HB 130 and related)",
        "url": "https://legiscan.com/TX/bill/HB130/2023",
    },
    "UT": {
        "name": "Utah",
        "statute": "Genetic Information Privacy Act",
        "url": "https://le.utah.gov/xcode/Title13/Chapter60/13-60.html",
    },
    "VA": {
        "name": "Virginia",
        "statute": "Genetic privacy protections",
        "url": "https://law.lis.virginia.gov/",
    },
    "VT": {
        "name": "Vermont",
        "statute": "Genetic Information Privacy Act (Act 135)",
        "url": "https://legislature.vermont.gov/bill/status/2024/H.121",
    },
    "WA": {
        "name": "Washington",
        "statute": "My Health My Data Act (includes genetic data)",
        "url": "https://app.leg.wa.gov/RCW/default.aspx?cite=19.373",
    },
    "WY": {
        "name": "Wyoming",
        "statute": "Genetic Information Privacy Act (HB 86)",
        "url": "https://legiscan.com/WY/bill/HB0086/2024",
    },
    # Pending watch target — used once PA HB 1530 is detected as enacted.
    "PA": {
        "name": "Pennsylvania",
        "statute": "Genetic Information Privacy Act (HB 1530)",
        "url": "https://www.palegis.us/legislation/bills/2025/hb1530",
    },
}


def law_for_state(state: str | None) -> dict[str, str] | None:
    if not state:
        return None
    return STATE_LAWS.get(state.upper())


def alert_copy(state: str | None) -> dict[str, str]:
    """Plain-language alert naming the state and statute (for the block page)."""
    code = (state or "").upper()
    law = law_for_state(code) or {
        "name": code or "your state",
        "statute": "applicable genetic privacy law",
        "url": "https://www.congress.gov/",
    }
    name = law["name"]
    statute = law["statute"]
    return {
        "state_code": code,
        "state_name": name,
        "statute": statute,
        "url": law["url"],
        "headline": f"Not available in {name}",
        "message": (
            f"{name} state statute {statute} prevents you from using this service."
        ),
        "billing_message": (
            f"We cannot charge or start a subscription from {name}. "
            f"{name} state statute {statute} prevents you from using this service."
        ),
    }


BLOCKED_FRIENDLY = (
    "This service isn't available in your state right now. "
    "If you think this is a mistake (for example you're on a VPN), try again without a VPN, "
    "or contact support from a location where the service is offered."
)


# Pending genetic-privacy bills: when a watch reports "enacted", that state joins the block
# automatically (persisted under data/auto_blocked_states.json so a later lookup failure
# does not drop the block). Fail-open on network errors unless already persisted.
PENDING_WATCHES = (
    {
        "state": "PA",
        "label": "PA HB 1530 — Genetic Information Privacy Act (2025-2026)",
        "status_url": "https://legiscan.com/PA/bill/HB1530/2025",
        # Markers that mean the bill became law (not merely passed one chamber).
        "enacted_markers": (
            "Became Law",
            "became law",
            "Approved by the Governor",
            "approved by the Governor",
            "Signed by the Governor",
            "signed by the Governor",
            "Chaptered",
            "chaptered",
        ),
    },
)

_WATCH_TTL = 6 * 3600  # seconds between live bill checks
_watch_cache: dict[str, tuple[float, bool]] = {}
_AUTO_BLOCK_PATH = Path(__file__).resolve().parent / "data" / "auto_blocked_states.json"


def _load_auto_blocked() -> set[str]:
    try:
        if _AUTO_BLOCK_PATH.is_file():
            raw = json.loads(_AUTO_BLOCK_PATH.read_text(encoding="utf-8"))
            states = raw.get("states") if isinstance(raw, dict) else raw
            return {str(s).upper() for s in (states or []) if str(s).strip()}
    except Exception:
        pass
    return set()


def _save_auto_blocked(states: set[str]) -> None:
    try:
        _AUTO_BLOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "states": sorted(states),
            "updated_at": int(time.time()),
            "source": "pending_bill_watch",
        }
        _AUTO_BLOCK_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except Exception:
        pass


def _force_enacted_from_env() -> set[str]:
    """Ops override: GEO_BLOCK_FORCE_ENACTED=PA,CT (comma-separated)."""
    raw = (os.environ.get("GEO_BLOCK_FORCE_ENACTED") or "").strip()
    if not raw:
        return set()
    return {p.strip().upper() for p in raw.split(",") if p.strip()}


def _fetch_bill_page(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "GeneMealBillWatch/1.0 (+geo-compliance)"},
    )
    with urllib.request.urlopen(req, timeout=4.0) as resp:
        return resp.read().decode("utf-8", "replace")


def bill_looks_enacted(page_text: str, markers: tuple[str, ...]) -> bool:
    if not page_text:
        return False
    # Explicit law markers only — chamber passage ("Engrossed", "Passed House") is not enough.
    for m in markers:
        if m in page_text:
            return True
    return False


def check_watch_enacted(watch: dict, *, fetch=None, now: float | None = None) -> bool:
    """Return True if the watched bill appears enacted. Uses TTL cache; injectable fetch for tests."""
    state = watch["state"].upper()
    now = time.time() if now is None else now
    # Skip TTL cache when a fetch injector is provided (tests / forced refresh).
    if fetch is None:
        hit = _watch_cache.get(state)
        if hit and now - hit[0] < _WATCH_TTL:
            return hit[1]
    enacted = False
    try:
        if fetch is not None:
            text = fetch(watch)
        else:
            text = _fetch_bill_page(watch["status_url"])
        enacted = bill_looks_enacted(text, tuple(watch.get("enacted_markers") or ()))
    except Exception:
        enacted = False
    _watch_cache[state] = (now, enacted)
    if enacted:
        auto = _load_auto_blocked()
        if state not in auto:
            auto.add(state)
            _save_auto_blocked(auto)
    return enacted


def refresh_pending_watches(*, fetch=None) -> frozenset[str]:
    """Check all pending watches; return states newly/currently auto-blocked from watches."""
    found: set[str] = set()
    for watch in PENDING_WATCHES:
        if check_watch_enacted(watch, fetch=fetch):
            found.add(watch["state"].upper())
    # Keep any previously persisted enactments even if this refresh failed open.
    found |= _load_auto_blocked()
    found |= _force_enacted_from_env()
    return frozenset(found)


def effective_blocked_states(*, fetch=None, refresh: bool = True) -> frozenset[str]:
    """Hard-coded blocked set plus states whose watched bills are (or were) enacted."""
    extra = refresh_pending_watches(fetch=fetch) if refresh else (
        frozenset(_load_auto_blocked() | _force_enacted_from_env())
    )
    return frozenset(BLOCKED_STATES | extra)


EXEMPT_PATH_PREFIXES = (
    "/robots.txt",
    "/favicon",
    "/og.png",
    "/sitemap.xml",
    "/static",
    # PayPal and Stripe deliver webhooks from their own networks, not the visitor's state.
    "/paypal/webhook",
    "/PayPal/webhook",
    "/stripe/webhook",
)

# Visitor-facing routes that handle genetic data or payment. The state block
# applies only to these. Webhooks under the same prefixes stay exempt above.
BLOCKED_PATH_PREFIXES = (
    "/upload",
    "/parse",
    "/results",
    "/plan",
    "/diet",
    "/billing",
    "/stripe",
    "/paypal",
    "/PayPal",
    "/account",
    "/preview-login",
)

_cache: dict[str, tuple[float, Optional[str]]] = {}
_CACHE_TTL = 3600


def enabled() -> bool:
    return os.environ.get("GEO_BLOCK_ENABLED", "0") == "1"


def client_ip(req) -> str:
    """Best-effort client IP behind Render / proxies. Do not log the return value."""
    xff = (req.headers.get("X-Forwarded-For") or "").strip()
    if xff:
        return xff.split(",")[0].strip()
    xri = (req.headers.get("X-Real-IP") or "").strip()
    if xri:
        return xri
    return req.remote_addr or ""


def resolve_state(ip: str, *, fetch=None) -> Optional[str]:
    """Return two-letter US state code, or None if unknown / non-US / lookup failed."""
    if not ip or ip in ("127.0.0.1", "::1") or ip.startswith("10.") or ip.startswith("192.168."):
        return None
    now = time.time()
    hit = _cache.get(ip)
    if hit and now - hit[0] < _CACHE_TTL:
        return hit[1]
    try:
        if fetch is not None:
            data = fetch(ip)
        else:
            url = f"http://ip-api.com/json/{ip}?fields=status,countryCode,region"
            with urllib.request.urlopen(url, timeout=2.5) as resp:
                data = json.loads(resp.read().decode("utf-8", "replace"))
        if data.get("status") != "success" or data.get("countryCode") != "US":
            state = None
        else:
            region = (data.get("region") or "").upper().strip()
            state = region if len(region) == 2 else None
    except Exception:
        state = None
    _cache[ip] = (now, state)
    if len(_cache) > 5000:
        for k, _ in sorted(_cache.items(), key=lambda kv: kv[1][0])[:1000]:
            _cache.pop(k, None)
    return state


def is_blocked_state(state: Optional[str], *, fetch=None, refresh: bool = True) -> bool:
    if not state:
        return False
    return state.upper() in effective_blocked_states(fetch=fetch, refresh=refresh)


def path_exempt(path: str) -> bool:
    if not path:
        return False
    for p in EXEMPT_PATH_PREFIXES:
        if path == p or path.startswith(p):
            return True
    if path.endswith(".html") and path.count("/") == 1:
        return True
    return False


def path_is_blocked_scope(path: str) -> bool:
    """True for genome upload, results, and billing routes.

    Content pages are not in scope. Provider webhooks and static/crawl files
    stay exempt even when their URL sits under a billing prefix.
    """
    if not path or path_exempt(path):
        return False
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/") or "/"
    for prefix in BLOCKED_PATH_PREFIXES:
        if path == prefix or path.startswith(prefix + "/"):
            return True
    return False



def visitor_state(request, *, fetch=None) -> Optional[str]:
    return resolve_state(client_ip(request), fetch=fetch)


def billing_blocked(request, *, fetch=None, bill_fetch=None) -> tuple[bool, Optional[str]]:
    """True when the visitor's state is on the effective block list.

    Independent of GEO_BLOCK_ENABLED — blocked-state users must never be charged,
    even if browsing is still allowed. Unknown / failed lookups are not blocked.
    """
    if path_exempt(request.path):
        return False, None
    state = visitor_state(request, fetch=fetch)
    if not state:
        return False, None
    if state.upper() in effective_blocked_states(fetch=bill_fetch):
        return True, state.upper()
    return False, state.upper() if state else None


def render_unavailable_html(state: Optional[str]) -> str:
    """Clean 451 page naming the state and statute, with a link to the full text.

    The visible body stays state-specific. The <head> uses the same default title,
    description, share image, and Twitter card as templates/base.html so link
    previews do not show the "Not available in <State>" headline.
    """
    info = alert_copy(state)
    # Escape via simple replace for attributes/text we control from our catalog.
    def esc(s: str) -> str:
        return (
            s.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    headline = esc(info["headline"])
    message = esc(info["message"])
    statute = esc(info["statute"])
    name = esc(info["state_name"])
    url = esc(info["url"])
    # Preview tags mirror templates/base.html defaults. og:url is the canonical home.
    preview_title = esc(site_meta.SITE_TITLE)
    preview_description = esc(site_meta.SITE_DESCRIPTION)
    preview_url = esc(site_meta.SITE_HOME_URL)
    preview_image = esc(site_meta.OG_IMAGE_URL)
    preview_image_alt = esc(site_meta.OG_IMAGE_ALT)
    preview_image_w = esc(str(site_meta.OG_IMAGE_WIDTH))
    preview_image_h = esc(str(site_meta.OG_IMAGE_HEIGHT))
    preview_twitter = esc(site_meta.TWITTER_CARD)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{preview_title}</title>
<meta name="description" content="{preview_description}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="GeneMeal">
<meta property="og:title" content="{preview_title}">
<meta property="og:description" content="{preview_description}">
<meta property="og:url" content="{preview_url}">
<meta property="og:image" content="{preview_image}">
<meta property="og:image:width" content="{preview_image_w}">
<meta property="og:image:height" content="{preview_image_h}">
<meta property="og:image:alt" content="{preview_image_alt}">
<meta name="twitter:card" content="{preview_twitter}">
<meta name="twitter:image" content="{preview_image}">
<style>
  :root {{ color-scheme: light; }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; min-height: 100vh; display: grid; place-items: center;
    padding: 2rem 1.25rem;
    font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
    background: linear-gradient(180deg, #f3ecdf 0%, #e7dcc8 100%);
    color: #1c2822;
  }}
  main {{
    width: min(34rem, 100%);
    background: linear-gradient(160deg, #fffaf3 0%, #fbf3e6 100%);
    border: 1px solid #ddcbb3;
    border-radius: 1rem;
    padding: 1.75rem 1.6rem 1.5rem;
    box-shadow: 0 10px 30px rgba(28,40,34,.10);
  }}
  .badge {{
    display: inline-block; font-size: .72rem; letter-spacing: .06em; text-transform: uppercase;
    color: #8a4e12; background: #f8ead4; border: 1px solid #e1b15a;
    border-radius: 999px; padding: .25rem .65rem; margin-bottom: .9rem;
  }}
  h1 {{ font-size: 1.35rem; line-height: 1.25; margin: 0 0 .85rem; font-weight: 650; }}
  p {{ margin: 0 0 .85rem; color: #4d5e55; line-height: 1.55; font-size: 1.02rem; }}
  .statute {{
    margin: 1rem 0 1.15rem; padding: .9rem 1rem;
    background: #f8ead4; border-radius: .75rem;
    border-left: 3px solid #1f6a4e;
  }}
  .statute strong {{ display: block; color: #143d2e; font-size: .78rem; letter-spacing: .04em;
    text-transform: uppercase; margin-bottom: .35rem; font-weight: 600; }}
  .statute span {{ color: #1c2822; line-height: 1.45; }}
  a.statute-link {{
    display: inline-flex; align-items: center; gap: .4rem;
    color: #143d2e; text-decoration: none; font-weight: 600;
    border-bottom: 1px solid rgba(31,106,78,.45); padding-bottom: 1px;
  }}
  a.statute-link:hover {{ color: #1f6a4e; border-bottom-color: #1f6a4e; }}
  .fine {{ margin: 1.15rem 0 0; font-size: .88rem; color: #4d5e55; }}
</style>
</head>
<body>
<main>
  <div class="badge">Service unavailable</div>
  <h1>{headline}</h1>
  <p>{message}</p>
  <div class="statute">
    <strong>{name} statute</strong>
    <span>{statute}</span>
  </div>
  <p><a class="statute-link" href="{url}" target="_blank" rel="noopener noreferrer">Read the full statute text</a></p>
  <p class="fine">If you think this is a mistake (for example you are on a VPN), try again without a VPN from a location where GeneMeal is offered.</p>
</main>
</body>
</html>
"""


def should_block(request, *, fetch=None, bill_fetch=None) -> tuple[bool, Optional[str]]:
    if not enabled():
        return False, None
    if not path_is_blocked_scope(request.path):
        return False, None
    state = resolve_state(client_ip(request), fetch=fetch)
    return is_blocked_state(state, fetch=bill_fetch), state


def clear_cache() -> None:
    _cache.clear()
    _watch_cache.clear()


def clear_auto_blocked() -> None:
    """Test helper: drop persisted auto-blocks from pending watches."""
    try:
        if _AUTO_BLOCK_PATH.is_file():
            _AUTO_BLOCK_PATH.unlink()
    except Exception:
        pass
    _watch_cache.clear()
