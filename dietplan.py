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
        notes.append("Dairy choices that contain lactose are hidden (lactase marker).")
    return {
        "calories": level,
        "groups": {g: amounts[g] for g in GROUP_ORDER},
        "protein_g": round(amounts["protein_foods"] * data()["protein_grams_per_oz_eq"]),
        "flags": sorted(flags),
        "notes": notes,
    }


# Genotype filter rules. A highlighted marker (traits.py focus tag) hides
# every food portion that breaks the rule; nothing is hidden without one.
SODIUM_LIMIT_MG = 460   # FDA "high" = 20% DV per serving
SAT_FAT_LIMIT_G = 4     # per portion
RULES = [
    {"flag": "lactose_free", "gene": "MCM6/LCT",
     "why": "regular dairy hidden (lactase-persistence marker); lactose-free and fortified soy kept",
     "hide": lambda o: "lactose" in o["tags"]},
    {"flag": "gluten_free", "gene": "HLA-DQ2.5",
     "why": "wheat, barley and rye foods hidden (celiac-associated HLA marker); gluten-free grains kept",
     "hide": lambda o: "gluten" in o["tags"]},
    {"flag": "sat_fat", "gene": "APOA2",
     "why": f"portions with {SAT_FAT_LIMIT_G} g+ saturated fat and solid fats hidden (saturated-fat-sensitivity marker)",
     "hide": lambda o: o["sat_fat_g"] >= SAT_FAT_LIMIT_G or o["subgroup"].startswith("solid fat")},
    {"flag": "apoe", "gene": "APOE e4",
     "why": "portions with 3 g+ saturated fat and solid fats hidden (APOE e4 carrier); unsaturated, low-sat-fat choices starred",
     "hide": lambda o: o["sat_fat_g"] >= 3 or o["subgroup"].startswith("solid fat")},
    {"flag": "no_alcohol", "gene": "ALDH2/ADH1B",
     "why": "alcohol-containing items hidden (the menu has none today)",
     "hide": lambda o: "alcohol" in o["tags"]},
    {"flag": "sodium", "gene": "AGT",
     "why": f"portions with {SODIUM_LIMIT_MG} mg+ sodium hidden (salt-sensitivity marker)",
     "hide": lambda o: o["sodium_mg"] >= SODIUM_LIMIT_MG},
]


# Star/flag-only rules: they never hide anything.
NOTES = [
    {"flag": "bitter_taster", "gene": "TAS2R38",
     "why": "milder vegetables starred; bitter greens (kale, arugula, Brussels sprouts...) are often easier roasted or seasoned"},
    {"flag": "sugar_pref", "gene": "SLC2A2",
     "why": "100% juice and dried fruit portions flagged ⚠; whole fruit starred"},
    {"flag": "satiety", "gene": "MC4R/LEPR/GLP1R",
     "why": "filling high-fiber (3 g+) and high-protein (10 g+) portions starred"},
    {"flag": "unsat_fat", "gene": "PPARG",
     "why": "unsaturated, low-saturated-fat choices starred"},
    {"flag": "protein_note", "gene": "ACTN3",
     "why": "higher-protein portions starred"},
    {"flag": "folate", "gene": "MTHFR",
     "why": "folate-rich leafy greens, legumes and fortified grains starred"},
    {"flag": "omega3", "gene": "FADS",
     "why": "omega-3-rich fish, walnuts, chia and flax starred"},
]
BITTER = ("Kale", "Arugula", "Brussels", "Broccoli rabe", "Mustard greens", "Turnip greens",
          "Watercress", "Collard", "Cabbage", "Red cabbage", "Radishes", "Broccoli")


def foods() -> dict:
    return json.loads((Path(__file__).parent / "reference" / "foods.json").read_text())


def _amount(x: float) -> str:
    whole, frac = int(x), round(x - int(x), 3)
    part = {0: "", 0.125: "1/8", 0.25: "1/4", 0.333: "1/3", 0.375: "3/8", 0.5: "1/2",
            0.666: "2/3", 0.667: "2/3", 0.75: "3/4", 0.999: "1"}.get(frac)
    if part is None:
        return f"{x:g}"
    if part == "1":
        return str(whole + 1)
    return f"{whole} {part}".strip() if whole else (part or "0")


def _serving(qty: float, unit: str) -> str:
    if unit in ("cup", "cups"):
        unit = "cups" if qty > 1 else "cup"
    return f"{_amount(qty)} {unit}"


def pool() -> dict:
    """Every food x portion option, before genotype filtering."""
    f = foods()
    out = {}
    for g in GROUP_ORDER:
        rows = []
        for food in f["foods"][g]:
            for m in f["portions"][g]:
                amt = round(food["eq"] * m, 2)
                rows.append({
                    "name": f'{food["name"]} ({_serving(food["qty"] * m, food["unit"])})',
                    "food": food["name"], "group": g, "subgroup": food["subgroup"], "amount": amt,
                    "protein_g": round(food["protein_g"] * m, 1), "fiber_g": round(food["fiber_g"] * m, 1),
                    "sat_fat_g": round(food["sat_fat_g"] * m, 1), "sodium_mg": round(food["sodium_mg"] * m),
                    "tags": food["tags"],
                })
        out[g] = rows
    return out


def _star(o: dict, flags: set[str]) -> bool:
    tags = set(o["tags"])
    if o["fiber_g"] >= 3:
        tags.add("fiber")
    if o["sat_fat_g"] <= 1 and "solid fat" not in o["subgroup"]:
        tags.update({"sat_fat", "apoe", "unsat_fat"})
    if o["fiber_g"] >= 3 or o["protein_g"] >= 10:
        tags.add("satiety")
    if o["subgroup"] in ("dark green", "red & orange", "starchy", "other") and not o["food"].startswith(BITTER):
        tags.add("bitter_taster")
    if o["subgroup"] in ("whole", "canned", "frozen") and o.get("group") == "fruits":
        tags.add("sugar_pref")
    if o["protein_g"] >= 10:
        tags.update({"appetite", "protein_note"})
    return bool(flags & tags)


def choices(summary: dict | None = None, flags: set[str] | None = None) -> dict:
    flags = _flags(summary) if flags is None else set(flags)
    active = [r for r in RULES if r["flag"] in flags]
    out = {}
    for g, rows in pool().items():
        keep = []
        for o in rows:
            if any(r["hide"](o) for r in active):
                continue
            flag = "sugar_pref" in flags and o["subgroup"] in ("juice", "dried")
            keep.append({**o, "match": _star(o, flags), "avoid": flag})
        out[g] = keep
    return out


def tailoring(summary: dict | None = None) -> dict:
    flags = _flags(summary)
    full = {g: len(v) for g, v in pool().items()}
    kept = {g: len(v) for g, v in choices(summary).items()}
    return {"rules": [{"gene": r["gene"], "why": r["why"]} for r in RULES if r["flag"] in flags],
            "stars": [{"gene": r["gene"], "why": r["why"]} for r in NOTES if r["flag"] in flags],
            "hidden": sum(full.values()) - sum(kept.values()), "kept": kept}


def view(kcal: int, summary: dict | None = None) -> dict:
    d = data()
    return {
        "targets": targets(kcal, summary),
        "choices": choices(summary),
        "tailoring": tailoring(summary),
        "groups": [{"key": g, "label": LABELS[g], "unit": d["food_groups"][g]["unit"],
                    "tip": d["food_groups"][g]["tip"]} for g in GROUP_ORDER],
        "meals": MEALS,
        "sources": d["source"]["urls"] + [u for u in foods()["sources"] if u not in d["source"]["urls"]],
    }
