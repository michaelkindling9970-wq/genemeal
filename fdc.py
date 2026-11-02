"""USDA FoodData Central client.

Reads FDC_API_KEY from the environment. No key is baked in. Search and food
detail responses are cached in memory and, optionally, on disk. Live calls are
paced. Tests pass a transport callable and never touch the network.

Set GENEMEAL_FORBID_NETWORK=1 to refuse live HTTP even if a key is present.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable
from urllib.parse import urlencode

BASE = "https://api.nal.usda.gov/fdc/v1"
USER_AGENT = "GeneMeal/0.1 (educational local app)"

# nutrientId 1008 is Energy (kcal). 1003 is Protein.
_KCAL_IDS = {1008}
_PROTEIN_IDS = {1003}


class FdcError(RuntimeError):
    pass


def _nutrient_id(item: dict) -> int | None:
    if "nutrientId" in item:
        try:
            return int(item["nutrientId"])
        except (TypeError, ValueError):
            return None
    nested = item.get("nutrient") or {}
    if "id" in nested:
        try:
            return int(nested["id"])
        except (TypeError, ValueError):
            return None
    return None


def _nutrient_value(item: dict) -> float | None:
    raw = item.get("value", item.get("amount"))
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _unit(item: dict) -> str:
    unit = item.get("unitName")
    if not unit:
        unit = (item.get("nutrient") or {}).get("unitName", "")
    return str(unit or "").lower()


def extract_macros(food: dict) -> tuple[float | None, float | None]:
    """Return (kcal per 100 g, protein grams per 100 g) when the payload has them."""
    kcal = None
    protein = None
    for item in food.get("foodNutrients") or []:
        nid = _nutrient_id(item)
        value = _nutrient_value(item)
        if value is None:
            continue
        name = str(item.get("nutrientName") or (item.get("nutrient") or {}).get("name") or "").lower()
        unit = _unit(item)
        if nid in _KCAL_IDS or (name == "energy" and "kcal" in unit):
            kcal = value
        elif nid in _PROTEIN_IDS or name == "protein":
            protein = value
    return kcal, protein


class FdcClient:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        cache_path: str | Path | None = None,
        transport: Callable[[str], dict] | None = None,
        min_interval: float = 0.35,
        now: Callable[[], float] | None = None,
        sleep: Callable[[float], None] | None = None,
        cache_limit: int = 400,
    ):
        if api_key is None:
            api_key = os.environ.get("FDC_API_KEY", "")
        self.api_key = (api_key or "").strip()
        self.transport = transport
        self.min_interval = float(min_interval)
        self._now = now or time.monotonic
        self._sleep = sleep or time.sleep
        self._lock = threading.Lock()
        self._last: float | None = None
        self._cache: dict[str, dict] = {}
        self._cache_limit = cache_limit
        self.cache_path = Path(cache_path) if cache_path else None
        self._load_disk_cache()

    def search(self, query: str, page_size: int = 5) -> dict:
        url = f"{BASE}/foods/search?{urlencode({'api_key': self.api_key, 'query': query, 'pageSize': int(page_size)})}"
        return self._cached(url)

    def food(self, fdc_id: int) -> dict:
        url = f"{BASE}/food/{int(fdc_id)}?{urlencode({'api_key': self.api_key})}"
        return self._cached(url)

    def lookup(self, query: str) -> dict | None:
        """First search hit with kcal, fetching detail when search omits nutrients.

        Returns None when there is no key and no test transport, or when FDC
        has nothing usable. Callers then use their offline table.
        """
        if not self.api_key and self.transport is None:
            return None
        try:
            payload = self.search(query, page_size=5)
        except FdcError:
            return None
        for food in payload.get("foods") or []:
            kcal, protein = extract_macros(food)
            chosen = food
            if kcal is None and food.get("fdcId"):
                try:
                    chosen = self.food(int(food["fdcId"]))
                except FdcError:
                    continue
                kcal, protein = extract_macros(chosen)
            if kcal is None:
                continue
            return {
                "fdc_id": chosen.get("fdcId", food.get("fdcId")),
                "description": chosen.get("description") or food.get("description") or query,
                "kcal_per_100g": float(kcal),
                "protein_per_100g": float(protein or 0),
            }
        return None

    def _cached(self, url: str) -> dict:
        with self._lock:
            hit = self._cache.get(url)
        if hit is not None:
            return hit
        if not self.api_key and self.transport is None:
            raise FdcError("FDC_API_KEY is not set")
        payload = self._request(url)
        if not isinstance(payload, dict):
            raise FdcError("FDC returned a non-object response")
        with self._lock:
            self._cache[url] = payload
            if len(self._cache) > self._cache_limit:
                for key in list(self._cache)[:100]:
                    self._cache.pop(key, None)
            self._save_disk_cache()
        return payload

    def _request(self, url: str) -> dict:
        self._throttle()
        if self.transport is not None:
            return self.transport(url)
        if os.environ.get("GENEMEAL_FORBID_NETWORK") == "1":
            raise FdcError("live FoodData Central calls are disabled")
        request = urllib.request.Request(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                body = response.read().decode("utf-8", "replace")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise FdcError("FoodData Central request failed") from exc
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise FdcError("FoodData Central returned invalid JSON") from exc

    def _throttle(self) -> None:
        if self.min_interval <= 0:
            return
        with self._lock:
            now = self._now()
            if self._last is not None:
                wait = self.min_interval - (now - self._last)
                if wait > 0:
                    self._sleep(wait)
                    now = self._now()
                    if now < self._last + wait:
                        now = self._last + wait
            self._last = now

    def _load_disk_cache(self) -> None:
        if not self.cache_path or not self.cache_path.exists():
            return
        try:
            data = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if isinstance(data, dict):
            self._cache = {str(k): v for k, v in data.items() if isinstance(v, dict)}

    def _save_disk_cache(self) -> None:
        if not self.cache_path:
            return
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps(self._cache), encoding="utf-8")
        except OSError:
            return
