"""Seven-day educational menus from trait labels and two toggles.

Foods are resolved through a FoodData Central client when one is supplied and
a key or test transport is available. Otherwise portions use an approximate
offline table labeled as such. Calorie and protein numbers are generic adult
placeholders, not a prescription.
"""
from __future__ import annotations

from fdc import FdcClient, FdcError

DISCLAIMER = (
    "Not medical advice. This 7-day menu is an educational sketch built from 11 "
    "genetic public nutrition markers and genetic calorie and protein placeholders. It does "
    "not diagnose, treat, or prevent any condition, and it is not a prescription for "
    "you. Genotype effects are usually small. Talk with a clinician or registered "
    "dietitian before changing how you eat, especially if you are pregnant, managing "
    "an illness, or considering supplements."
)

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# Offline macros are typical USDA-style per-100 g figures, used only when FDC
# is not configured. They are approximate.
FOODS: dict[str, dict] = {
    "oats": {"name": "Rolled oats", "query": "oats, raw", "kcal": 389, "protein": 16.9, "role": "starch"},
    "berries": {"name": "Blueberries", "query": "blueberries, raw", "kcal": 57, "protein": 0.7, "role": "fruit"},
    "eggs": {"name": "Eggs", "query": "egg, whole, raw", "kcal": 143, "protein": 12.6, "role": "protein"},
    "yogurt": {
        "name": "Plain nonfat Greek yogurt",
        "query": "yogurt, greek, plain, nonfat",
        "kcal": 59,
        "protein": 10.3,
        "role": "protein",
        "dairy": True,
    },
    "soy_milk": {
        "name": "Fortified unsweetened soy milk",
        "query": "soy milk, unsweetened, fortified",
        "kcal": 33,
        "protein": 3.3,
        "role": "protein",
    },
    "chicken": {"name": "Chicken breast", "query": "chicken, broiler, breast, raw", "kcal": 120, "protein": 22.5, "role": "protein"},
    "salmon": {
        "name": "Salmon",
        "query": "fish, salmon, atlantic, farmed, raw",
        "kcal": 208,
        "protein": 20.4,
        "role": "protein",
        "fish": True,
    },
    "sardines": {
        "name": "Sardines",
        "query": "fish, sardine, canned in oil, drained",
        "kcal": 208,
        "protein": 24.6,
        "role": "protein",
        "fish": True,
    },
    "lentils": {"name": "Lentils", "query": "lentils, mature seeds, cooked", "kcal": 116, "protein": 9.0, "role": "protein", "legume": True},
    "black_beans": {
        "name": "Black beans",
        "query": "beans, black, mature seeds, cooked",
        "kcal": 132,
        "protein": 8.9,
        "role": "protein",
        "legume": True,
    },
    "chickpeas": {"name": "Chickpeas", "query": "chickpeas, mature seeds, cooked", "kcal": 164, "protein": 8.9, "role": "protein", "legume": True},
    "tofu": {"name": "Firm tofu", "query": "tofu, firm, prepared with calcium sulfate", "kcal": 144, "protein": 17.3, "role": "protein"},
    "brown_rice": {"name": "Brown rice", "query": "rice, brown, cooked", "kcal": 123, "protein": 2.7, "role": "starch"},
    "quinoa": {"name": "Quinoa", "query": "quinoa, cooked", "kcal": 120, "protein": 4.4, "role": "starch"},
    "sweet_potato": {"name": "Sweet potato", "query": "sweet potato, cooked, baked", "kcal": 90, "protein": 2.0, "role": "starch"},
    "broccoli": {"name": "Broccoli", "query": "broccoli, raw", "kcal": 34, "protein": 2.8, "role": "veg"},
    "spinach": {"name": "Spinach", "query": "spinach, raw", "kcal": 23, "protein": 2.9, "role": "veg"},
    "kale": {"name": "Kale", "query": "kale, raw", "kcal": 35, "protein": 2.9, "role": "veg"},
    "bell_pepper": {"name": "Red bell pepper", "query": "peppers, sweet, red, raw", "kcal": 31, "protein": 1.0, "role": "veg"},
    "olive_oil": {"name": "Olive oil", "query": "oil, olive, salad or cooking", "kcal": 884, "protein": 0.0, "role": "fat"},
    "walnuts": {"name": "Walnuts", "query": "nuts, walnuts, english", "kcal": 654, "protein": 15.2, "role": "fat"},
}

_CAPS = {
    "oats": (35, 110),
    "berries": (40, 150),
    "eggs": (50, 200),
    "yogurt": (80, 250),
    "soy_milk": (150, 400),
    "chicken": (80, 240),
    "salmon": (80, 220),
    "sardines": (50, 140),
    "lentils": (80, 260),
    "black_beans": (80, 240),
    "chickpeas": (80, 240),
    "tofu": (80, 240),
    "brown_rice": (60, 320),
    "quinoa": (60, 320),
    "sweet_potato": (70, 320),
    "broccoli": (50, 220),
    "spinach": (40, 160),
    "kale": (40, 160),
    "bell_pepper": (40, 160),
    "olive_oil": (4, 18),
    "walnuts": (8, 32),
}

# Lunch protein, dinner protein. Fish shows up across the week.
_ROTATION = [
    ("chicken", "salmon"),
    ("lentils", "sardines"),
    ("tofu", "chicken"),
    ("chickpeas", "salmon"),
    ("black_beans", "sardines"),
    ("chicken", "tofu"),
    ("salmon", "lentils"),
]


def targets_for(*, weight_loss: bool, build_muscle: bool) -> dict:
    if weight_loss and build_muscle:
        kcal, protein, label = 2100, 145, "higher-protein maintenance (illustrative)"
    elif weight_loss:
        kcal, protein, label = 1700, 115, "lower-calorie, higher-protein (illustrative)"
    elif build_muscle:
        kcal, protein, label = 2500, 150, "higher-calorie, higher-protein (illustrative)"
    else:
        kcal, protein, label = 2000, 90, "general illustrative target"
    return {
        "calories": kcal,
        "protein_g": protein,
        "weight_loss": bool(weight_loss),
        "build_muscle": bool(build_muscle),
        "note": (
            f"{label}. These are round numbers for a generic adult menu, "
            "not a calculation from your body."
        ),
    }


def _flags(summary: dict | None) -> set[str]:
    found: set[str] = set()
    for row in (summary or {}).get("highlights") or []:
        found.update(row.get("focus_tags") or [])
    return found


def _adjustments(flags: set[str]) -> list[str]:
    notes = []
    if "lactose_free" in flags:
        notes.append(
            "Cow's-milk yogurt is left out because the lactase marker was flagged. Fortified soy milk is used instead."
        )
    if "folate" in flags:
        notes.append("Spinach is in the week because a folate-metabolism marker was flagged.")
    if "sat_fat" in flags:
        notes.append(
            "Olive oil, fish, and beans stand in for a high-saturated-fat pattern because the APOA2 marker was flagged."
        )
    if "fiber" in flags:
        notes.append("Oats and legumes are in the week because the TCF7L2 marker was flagged.")
    if "omega3" in flags:
        notes.append("Fish and walnuts are in the week because the FADS1 marker was flagged.")
    if "vitamin_d" in flags:
        notes.append(
            "Salmon, sardines, or fortified soy milk are in the week because the vitamin D marker was flagged."
        )
    if "carotenoid" in flags:
        notes.append("Sweet potato and dark greens are in the week because a beta-carotene marker was flagged.")
    if "appetite" in flags:
        notes.append("Portions lean toward protein and vegetables because the FTO marker was flagged.")
    if not notes:
        notes.append("No mapped marker was in a highlighted group. The week is a plain balanced sketch.")
    return notes


def _trait_notes(summary: dict | None) -> list[dict]:
    rows = []
    for row in (summary or {}).get("highlights") or []:
        rows.append(
            {
                "rsid": row.get("rsid"),
                "gene": row.get("gene"),
                "label": row.get("label"),
                "confidence": row.get("confidence"),
            }
        )
    return rows


class _Resolver:
    def __init__(self, client: FdcClient | None):
        self.client = client
        self._memo: dict[str, dict] = {}
        self.sources: set[str] = set()

    def get(self, key: str) -> dict:
        if key in self._memo:
            return self._memo[key]
        spec = FOODS[key]
        resolved = {
            "key": key,
            "name": spec["name"],
            "description": spec["name"],
            "query": spec["query"],
            "kcal_per_100g": spec["kcal"],
            "protein_per_100g": spec["protein"],
            "fdc_id": None,
            "source": "offline-approximate",
            "role": spec["role"],
        }
        if self.client is not None:
            try:
                found = self.client.lookup(spec["query"])
            except FdcError:
                found = None
            if found:
                resolved.update(
                    {
                        "description": found["description"],
                        "kcal_per_100g": found["kcal_per_100g"],
                        "protein_per_100g": found["protein_per_100g"],
                        "fdc_id": found.get("fdc_id"),
                        "source": "fdc",
                    }
                )
        self.sources.add(resolved["source"])
        self._memo[key] = resolved
        return resolved


def _add(bucket: list[dict], resolver: _Resolver, meal: str, key: str, grams: float) -> None:
    food = resolver.get(key)
    lo, hi = _CAPS[key]
    bucket.append(
        {
            "meal": meal,
            "key": key,
            "name": food["name"],
            "description": food["description"],
            "grams": max(lo, min(hi, grams)),
            "kcal_per_100g": food["kcal_per_100g"],
            "protein_per_100g": food["protein_per_100g"],
            "fdc_id": food["fdc_id"],
            "source": food["source"],
            "role": food["role"],
        }
    )


def _compose(day_index: int, flags: set[str], resolver: _Resolver, *, weight_loss: bool, build_muscle: bool) -> list[dict]:
    lunch_key, dinner_key = _ROTATION[day_index]
    starch_scale = 1.0
    protein_scale = 1.0
    veg_scale = 1.0
    if weight_loss:
        starch_scale *= 0.8
        protein_scale *= 1.08
        veg_scale *= 1.2
    if build_muscle:
        starch_scale *= 1.15
        protein_scale *= 1.2
    if "appetite" in flags and not weight_loss:
        veg_scale *= 1.15
        protein_scale *= 1.08
    items: list[dict] = []
    _add(items, resolver, "Breakfast", "oats", 55 * starch_scale)
    _add(items, resolver, "Breakfast", "berries", 80)
    _add(items, resolver, "Breakfast", "eggs", 90 * protein_scale)
    if "lactose_free" in flags:
        _add(items, resolver, "Breakfast", "soy_milk", 240)
    else:
        _add(items, resolver, "Breakfast", "yogurt", 140 * protein_scale)
    _add(items, resolver, "Lunch", lunch_key, 130 * protein_scale)
    if "folate" in flags:
        lunch_veg = "spinach" if day_index % 2 == 0 else "kale"
    elif "carotenoid" in flags:
        lunch_veg = "kale" if day_index % 2 == 0 else "bell_pepper"
    else:
        lunch_veg = "broccoli"
    _add(items, resolver, "Lunch", lunch_veg, 110 * veg_scale)
    lunch_starch = "sweet_potato" if "carotenoid" in flags and day_index % 2 == 0 else ("quinoa" if day_index % 2 else "brown_rice")
    _add(items, resolver, "Lunch", lunch_starch, 150 * starch_scale)
    _add(items, resolver, "Lunch", "olive_oil", 7)
    _add(items, resolver, "Dinner", dinner_key, 130 * protein_scale)
    dinner_veg = "spinach" if "folate" in flags and day_index % 2 else "broccoli"
    _add(items, resolver, "Dinner", dinner_veg, 110 * veg_scale)
    if "carotenoid" in flags:
        dinner_starch = "sweet_potato"
    else:
        dinner_starch = "brown_rice" if day_index % 2 == 0 else "quinoa"
    _add(items, resolver, "Dinner", dinner_starch, 160 * starch_scale)
    _add(items, resolver, "Dinner", "olive_oil", 7)
    _add(items, resolver, "Snack", "walnuts", 14 if not weight_loss else 10)
    legume_keys = {"lentils", "black_beans", "chickpeas"}
    if "fiber" in flags and lunch_key not in legume_keys and dinner_key not in legume_keys:
        _add(items, resolver, "Lunch", "lentils", 90)
    has_fish = any(FOODS[item["key"]].get("fish") for item in items)
    has_soy = any(item["key"] == "soy_milk" for item in items)
    if "vitamin_d" in flags and not has_fish and not has_soy:
        _add(items, resolver, "Snack", "sardines", 70)
    return items


def _totals_raw(items: list[dict]) -> tuple[float, float]:
    kcal = sum(item["grams"] * item["kcal_per_100g"] / 100 for item in items)
    protein = sum(item["grams"] * item["protein_per_100g"] / 100 for item in items)
    return kcal, protein


def _nudge(items: list[dict], role: str, factor: float) -> None:
    for item in items:
        if item["role"] != role:
            continue
        lo, hi = _CAPS[item["key"]]
        item["grams"] = min(hi, max(lo, item["grams"] * factor))


def _fit(items: list[dict], kcal_target: float, protein_target: float) -> None:
    for _ in range(14):
        kcal, protein = _totals_raw(items)
        if kcal < kcal_target * 0.94:
            _nudge(items, "starch", 1.10)
            _nudge(items, "fat", 1.06)
        elif kcal > kcal_target * 1.06:
            _nudge(items, "starch", 0.90)
            _nudge(items, "fat", 0.92)
        if protein < protein_target * 0.90:
            _nudge(items, "protein", 1.10)
        elif protein > protein_target * 1.18 and kcal >= kcal_target * 0.90:
            _nudge(items, "protein", 0.92)


def _finalize_day(name: str, items: list[dict]) -> dict:
    meals: dict[str, list] = {"Breakfast": [], "Lunch": [], "Dinner": [], "Snack": []}
    kcal_sum = 0
    protein_sum = 0.0
    for item in items:
        grams = int(round(item["grams"]))
        kcal = int(round(item["kcal_per_100g"] * grams / 100))
        protein = round(item["protein_per_100g"] * grams / 100, 1)
        kcal_sum += kcal
        protein_sum += protein
        meals[item["meal"]].append(
            {
                "key": item["key"],
                "name": item["name"],
                "description": item["description"],
                "grams": grams,
                "kcal": kcal,
                "protein_g": protein,
                "fdc_id": item["fdc_id"],
                "source": item["source"],
            }
        )
    return {
        "name": name,
        "meals": [{"name": meal, "foods": meals[meal]} for meal in ("Breakfast", "Lunch", "Dinner", "Snack")],
        "totals": {"kcal": kcal_sum, "protein_g": round(protein_sum, 1)},
    }


def build_meal_plan(
    summary: dict | None,
    *,
    weight_loss: bool = False,
    build_muscle: bool = False,
    fdc_client: FdcClient | None = None,
) -> dict:
    flags = _flags(summary)
    goals = targets_for(weight_loss=weight_loss, build_muscle=build_muscle)
    resolver = _Resolver(fdc_client if fdc_client is not None else FdcClient(min_interval=0.35))
    days = []
    for index, name in enumerate(DAYS):
        items = _compose(
            index,
            flags,
            resolver,
            weight_loss=weight_loss,
            build_muscle=build_muscle,
        )
        _fit(items, goals["calories"], goals["protein_g"])
        days.append(_finalize_day(name, items))
    sources = resolver.sources or {"offline-approximate"}
    if sources == {"fdc"}:
        nutrition_source = "fdc"
    elif "fdc" in sources:
        nutrition_source = "mixed"
    else:
        nutrition_source = "offline-approximate"
    return {
        "disclaimer": DISCLAIMER,
        "targets": goals,
        "adjustments": _adjustments(flags),
        "trait_notes": _trait_notes(summary),
        "nutrition_source": nutrition_source,
        "days": days,
    }
