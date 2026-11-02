import json
from pathlib import Path

import dietplan


def test_myplate_data_has_all_levels_and_sources():
    d = json.loads((Path(__file__).resolve().parents[1] / "data" / "myplate.json").read_text())
    assert sorted(int(k) for k in d["daily_amounts_by_calorie_level"]) == list(range(1000, 3201, 200))
    assert d["daily_amounts_by_calorie_level"]["2000"]["vegetables"] == 2.5
    assert d["daily_amounts_by_calorie_level"]["2000"]["grains"] == 6
    assert any("myplate.gov" in u for u in d["source"]["urls"])
    assert set(d["food_groups"]) == set(dietplan.GROUP_ORDER)


def test_calorie_level_varies_by_age_sex_activity():
    assert dietplan.calorie_level(25, "male", "active") == 3000
    assert dietplan.calorie_level(60, "female", "sedentary") == 1600
    assert dietplan.nearest_level(2050) == 2000


def test_trait_flags_adjust_targets_and_choices():
    summary = {"highlights": [{"focus_tags": ["appetite", "lactose_free"]}]}
    t = dietplan.targets(2000, summary)
    assert t["groups"]["protein_foods"] == 6.5
    dairy = {c["name"]: c for c in dietplan.choices(summary)["dairy"]}
    assert dairy["Low-fat milk (1 cup)"]["avoid"]
    assert dairy["Fortified soy milk (1 cup)"]["match"]


def test_diet_page_renders_dropdowns(client):
    body = client.get("/diet?age=40&sex=male&activity=active").get_data(as_text=True)
    assert body.count('class="pulse-select" name="') == 24
    assert "target 7 oz-eq" in body  # 2800 kcal protein
    assert "myplate.gov" in body
    assert "@keyframes" not in body  # styles live in style.css


def test_pulse_css_respects_reduced_motion():
    css = (Path(__file__).resolve().parents[1] / "static" / "style.css").read_text()
    assert "@keyframes gm-pulse" in css
    assert "prefers-reduced-motion: reduce" in css
