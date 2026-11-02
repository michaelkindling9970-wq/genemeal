"""Shared US-state geo block for GeneMeal (genetics + meal-plan app).

Enable with GEO_BLOCK_ENABLED=1. Off by default.
IP→state uses ip-api.com (free, no key). Raw IPs are never logged — only the resolved state code on deny.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import Optional

# USPS codes — states with consumer genetic privacy / health-data genetic rules (research Nov 2026).
BLOCKED_STATES = frozenset({
    "AL",  # Alabama Genetic Data Privacy Act
    "AZ",  # Arizona HB 2069
    "CA",  # California Genetic Information Privacy Act
    "FL",  # Florida DNA / lab rules
    "IL",  # Illinois GIPA
    "IN",  # Indiana HEA 1521
    "KY",  # Kentucky Genetic Information Privacy Act
    "MD",  # Maryland SB 187
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

BLOCKED_FRIENDLY = (
    "This service isn't available in your state right now. "
    "If you think this is a mistake (for example you're on a VPN), try again without a VPN, "
    "or contact support from a location where the service is offered."
)

EXEMPT_PATH_PREFIXES = (
    "/robots.txt",
    "/favicon",
    "/og.png",
    "/sitemap.xml",
    # Stripe delivers webhooks from its own network, not the visitor's state.
    "/stripe/webhook",
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


def is_blocked_state(state: Optional[str]) -> bool:
    return bool(state) and state.upper() in BLOCKED_STATES


def path_exempt(path: str) -> bool:
    if not path:
        return False
    for p in EXEMPT_PATH_PREFIXES:
        if path == p or path.startswith(p):
            return True
    if path.endswith(".html") and path.count("/") == 1:
        return True
    return False


def should_block(request, *, fetch=None) -> tuple[bool, Optional[str]]:
    if not enabled():
        return False, None
    if path_exempt(request.path):
        return False, None
    state = resolve_state(client_ip(request), fetch=fetch)
    return is_blocked_state(state), state


def clear_cache() -> None:
    _cache.clear()
