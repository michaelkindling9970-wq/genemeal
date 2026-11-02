from urllib.parse import parse_qs, urlparse

from fdc import FdcClient
from mealplan import DISCLAIMER, build_meal_plan


def _summary(*tags_for_rsids):
    highlights = []
    for rsid, tags, label in tags_for_rsids:
        highlights.append(
            {
                "rsid": rsid,
                "gene": "GENE",
                "label": label,
                "confidence": "medium",
                "focus_tags": tags,
            }
        )
    return {"highlights": highlights, "marker_count": 10, "build": 37}


def _foods(plan):
    return [food for day in plan["days"] for meal in day["meals"] for food in meal["foods"]]


def test_plan_structure_and_disclaimer():
    plan = build_meal_plan({"highlights": []})
    assert plan["disclaimer"] == DISCLAIMER
    assert "not medical advice" in plan["disclaimer"].lower()
    assert [day["name"] for day in plan["days"]] == [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]
    for day in plan["days"]:
        assert [meal["name"] for meal in day["meals"]] == ["Breakfast", "Lunch", "Dinner", "Snack"]
        assert day["meals"][0]["foods"]
        assert day["totals"]["kcal"] > 0
        assert day["totals"]["protein_g"] > 0
    assert plan["nutrition_source"] == "offline-approximate"
    assert all(food["fdc_id"] is None for food in _foods(plan))


def test_toggles_change_targets_and_calories():
    plain = build_meal_plan({"highlights": []})
    loss = build_meal_plan({"highlights": []}, weight_loss=True)
    muscle = build_meal_plan({"highlights": []}, build_muscle=True)
    both = build_meal_plan({"highlights": []}, weight_loss=True, build_muscle=True)
    assert loss["targets"]["calories"] < plain["targets"]["calories"] < muscle["targets"]["calories"]
    assert plain["targets"]["protein_g"] < loss["targets"]["protein_g"]
    assert muscle["targets"]["protein_g"] > plain["targets"]["protein_g"]
    assert both["targets"]["weight_loss"] and both["targets"]["build_muscle"]
    assert loss["targets"]["calories"] == 1700
    assert muscle["targets"]["calories"] == 2500

    def avg(plan):
        return sum(day["totals"]["kcal"] for day in plan["days"]) / 7

    assert avg(loss) < avg(plain) < avg(muscle)
    for plan in (plain, loss, muscle, both):
        target = plan["targets"]["calories"]
        for day in plan["days"]:
            assert abs(day["totals"]["kcal"] - target) / target < 0.15


def test_trait_labels_change_the_menu():
    flagged = build_meal_plan(
        _summary(
            ("rs4988235", ["lactose_free"], "Lactase persistence (European-ancestry marker)"),
            ("rs1801133", ["folate"], "Folate metabolism (C677T)"),
        )
    )
    plain = build_meal_plan({"highlights": []})
    flagged_names = [food["name"].lower() for food in _foods(flagged)]
    plain_names = [food["name"].lower() for food in _foods(plain)]
    assert not any("yogurt" in name for name in flagged_names)
    assert any("yogurt" in name for name in plain_names)
    assert any(name == "spinach" for name in flagged_names)
    assert not any(name == "spinach" for name in plain_names)
    assert any("lactase" in line.lower() for line in flagged["adjustments"])
    assert flagged["trait_notes"][0]["rsid"] == "rs4988235"
    assert flagged["disclaimer"] == DISCLAIMER


def test_plan_uses_mocked_fdc_client():
    calls = []

    def transport(url):
        calls.append(url)
        query = parse_qs(urlparse(url).query)
        assert "api.nal.usda.gov" in url
        assert query["api_key"] == ["test-key"]
        name = query.get("query", ["food"])[0]
        return {
            "foods": [
                {
                    "fdcId": 4242,
                    "description": f"FDC {name}",
                    "foodNutrients": [
                        {"nutrientId": 1008, "nutrientName": "Energy", "value": 150, "unitName": "KCAL"},
                        {"nutrientId": 1003, "nutrientName": "Protein", "value": 8, "unitName": "G"},
                    ],
                }
            ]
        }

    client = FdcClient(api_key="test-key", transport=transport, min_interval=0)
    plan = build_meal_plan({"highlights": []}, fdc_client=client)
    assert calls
    assert plan["nutrition_source"] == "fdc"
    foods = _foods(plan)
    assert foods[0]["fdc_id"] == 4242
    assert foods[0]["description"].startswith("FDC ")
    assert plan["disclaimer"] == DISCLAIMER
