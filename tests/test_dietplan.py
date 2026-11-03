import json
from pathlib import Path

import dietplan


def test_myplate_data_has_all_levels_and_sources():
    d = json.loads((Path(__file__).resolve().parents[1] / "reference" / "myplate.json").read_text())
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
    assert "Low-fat milk (1 cup)" not in dairy
    assert dairy["Fortified soy milk (1 cup)"]["match"]
    assert "Low-fat milk (1 cup)" in {c["name"] for c in dietplan.pool()["dairy"]}


def _paid(client):
    import storage
    client.get("/")
    with client.session_transaction() as sess:
        uid = sess["uid"]
    storage.set_billing(uid, status="active")
    return uid


def test_unpaid_user_is_redirected_and_has_no_nav_link(client):
    resp = client.get("/diet")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/pricing")
    assert 'href="/diet"' not in client.get("/").get_data(as_text=True)


def test_canceled_user_is_redirected(client):
    import storage
    uid = _paid(client)
    storage.set_billing(uid, status="canceled")
    assert client.get("/diet").status_code == 302


def test_paid_user_sees_nav_link(client):
    _paid(client)
    assert 'href="/diet"' in client.get("/").get_data(as_text=True)


def test_preview_login_off_by_default(client, monkeypatch):
    monkeypatch.delenv("PREVIEW_MODE", raising=False)
    monkeypatch.setenv("PREVIEW_TOKEN", "tok")
    assert client.get("/preview-login?token=tok").status_code == 404
    assert client.get("/diet").status_code == 302


def test_preview_login_needs_mode_and_token(client, monkeypatch):
    monkeypatch.setenv("PREVIEW_MODE", "1")
    monkeypatch.setenv("PREVIEW_TOKEN", "tok")
    assert client.get("/preview-login?token=bad").status_code == 404
    assert client.get("/diet").status_code == 302
    assert client.get("/preview-login?token=tok").status_code == 302
    assert client.get("/diet").status_code == 200


def test_render_config_has_no_preview_mode():
    root = Path(__file__).resolve().parents[1]
    for name in ("Procfile",):
        assert "PREVIEW" not in (root / name).read_text()


def test_diet_page_renders_dropdowns(client):
    _paid(client)
    body = client.get("/diet?age=40&sex=male&activity=active").get_data(as_text=True)
    assert body.count('class="pulse-select" name="') == 24
    assert "target 7 oz-eq" in body  # 2800 kcal protein
    assert "myplate.gov" in body
    assert "@keyframes" not in body  # styles live in style.css


def test_pulse_css_respects_reduced_motion():
    css = (Path(__file__).resolve().parents[1] / "static" / "style.css").read_text()
    assert "@keyframes gm-pulse" in css
    assert "prefers-reduced-motion: reduce" in css


import itertools

FILTER_FLAGS = [r["flag"] for r in dietplan.RULES]


def test_full_pool_is_comprehensive_and_sourced():
    f = dietplan.foods()
    assert any("myplate.gov" in u for u in f["sources"]) and any("fdc.nal.usda.gov" in u for u in f["sources"])
    for g in dietplan.GROUP_ORDER:
        assert len(f["foods"][g]) >= 30
        assert len(dietplan.pool()[g]) >= 90
    subs = {x["subgroup"] for x in f["foods"]["vegetables"]}
    assert {"dark green", "red & orange", "beans, peas, lentils", "starchy", "other"} <= subs


def test_every_trait_combo_keeps_50_per_list():
    for n in range(len(FILTER_FLAGS) + 1):
        for combo in itertools.combinations(FILTER_FLAGS, n):
            for g, rows in dietplan.choices(flags=set(combo) | {"appetite", "fiber"}).items():
                assert len(rows) >= 50, (combo, g, len(rows))


def test_filters_hide_what_they_promise():
    c = dietplan.choices(flags=set(FILTER_FLAGS))
    every = [o for rows in c.values() for o in rows]
    assert not any("gluten" in o["tags"] or "lactose" in o["tags"] or "caffeine" in o["tags"] for o in every)
    assert all(o["sodium_mg"] < dietplan.SODIUM_LIMIT_MG and o["sat_fat_g"] < dietplan.SAT_FAT_LIMIT_G for o in every)
    assert all(o["sat_fat_g"] < 3 for o in every)
    assert not any(o["subgroup"] == "caffeinated" for o in c["beverages"])
    assert any("Brown rice" in o["name"] for o in c["grains"])
    assert not any(o["food"] == "Whole-wheat bread" for o in c["grains"])


def test_paid_page_shows_tailoring_note(client):
    import storage
    uid = _paid(client)
    storage_summary = {"highlights": [{"gene": "HLA-DQ2.5", "focus_tags": ["gluten_free"]}]}
    view = dietplan.view(2000, storage_summary)
    assert view["tailoring"]["rules"] and view["tailoring"]["hidden"] > 0
    html = client.get("/diet").get_data(as_text=True)
    assert "diet-options" in html and "Brown rice, cooked (1/2 cup)" in html


def test_new_markers_star_without_hiding():
    full = {g: len(v) for g, v in dietplan.pool().items()}
    c = dietplan.choices(flags={"folate", "omega3"})
    assert {g: len(v) for g, v in c.items()} == full
    assert any(o["match"] for o in c["vegetables"] if o["food"].startswith("Spinach"))
    assert any(o["match"] for o in c["protein_foods"] if o["food"].startswith("Salmon"))


def test_apoe_and_fads_traits_present():
    from traits import summarize
    s = summarize({"genotypes": {"rs429358": "CT", "rs174537": "TT"}, "marker_count": 2})
    tags = {t for r in s["highlights"] for t in r["focus_tags"]}
    assert {"apoe", "omega3"} <= tags
