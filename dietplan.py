"""Choosable daily diet plan: MyPlate pattern + genetic trait flags.

Data comes from reference/myplate.json (USDA MyPlate / Healthy U.S.-Style pattern,
source URLs inside the file). Targets: calorie level from age/sex/activity
(or the meal-plan goal), rounded to the nearest USDA pattern; then nudged by
trait flags (e.g. appetite -> +1 oz protein, fiber -> grains all whole).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

GROUP_ORDER = ["grains", "vegetables", "fruits", "dairy", "protein_foods", "oils"]
LABELS = {"grains": "Grains", "vegetables": "Vegetables", "fruits": "Fruits",
          "dairy": "Dairy", "protein_foods": "Protein foods", "oils": "Oils"}
MEALS = ["Breakfast", "Lunch", "Dinner", "Snack"]
ACTIVITY = ["sedentary", "moderately_active", "active"]


@lru_cache(maxsize=1)
def data() -> dict:
    return json.loads((Path(__file__).parent / "reference" / "myplate.json").read_text())


def age_band(age: int) -> str:
    for hi, band in ((3, "2-3"), (8, "4-8"), (13, "9-13"), (18, "14-18"), (30, "19-30"), (50, "31-50")):
        if age <= hi:
            return band
    return "51+"


def calorie_level(age: int, sex: str, activity: str) -> int:
    sex = sex if sex in ("male", "female") else "female"
    idx = ACTIVITY.index(activity) if activity in ACTIVITY else 0
    return data()["estimated_calorie_needs"][sex][age_band(max(2, age))][idx]


def nearest_level(kcal: int) -> int:
    levels = [int(k) for k in data()["daily_amounts_by_calorie_level"]]
    return min(levels, key=lambda k: abs(k - kcal))


def _flags(summary: dict | None) -> set[str]:
    found: set[str] = set()
    for row in (summary or {}).get("highlights") or []:
        found.update(row.get("focus_tags") or [])
    return found


def targets(kcal: int, summary: dict | None = None) -> dict:
    level = nearest_level(kcal)
    amounts = dict(data()["daily_amounts_by_calorie_level"][str(level)])
    flags = _flags(summary)
    notes = []
    if "appetite" in flags:
        amounts["protein_foods"] += 1
        notes.append("Protein +1 oz-eq because the FTO marker was flagged.")
    if "fiber" in flags:
        notes.append("Pick whole grains for all grain servings (TCF7L2 marker flagged).")
    if "lactose_free" in flags:
        notes.append("Dairy choices that contain lactose are flagged (lactase marker).")
    return {
        "calories": level,
        "groups": {g: amounts[g] for g in GROUP_ORDER},
        "protein_g": round(amounts["protein_foods"] * data()["protein_grams_per_oz_eq"]),
        "flags": sorted(flags),
        "notes": notes,
    }


def choices(summary: dict | None = None) -> dict:
    flags = _flags(summary)
    out = {}
    for g in GROUP_ORDER:
        rows = []
        for name, amount, tags in data()["foods"][g]:
            avoid = "lactose_free" in flags and g == "dairy" and "lactose_free" not in tags
            rows.append({"name": name, "amount": amount, "match": bool(flags & set(tags)), "avoid": bool(avoid)})
        out[g] = rows
    return out


def view(kcal: int, summary: dict | None = None) -> dict:
    d = data()
    return {
        "targets": targets(kcal, summary),
        "choices": choices(summary),
        "groups": [{"key": g, "label": LABELS[g], "unit": d["food_groups"][g]["unit"],
                    "tip": d["food_groups"][g]["tip"]} for g in GROUP_ORDER],
        "meals": MEALS,
        "sources": d["source"]["urls"],
    }
