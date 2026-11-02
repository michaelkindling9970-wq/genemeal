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
    assert dairy["Low-fat milk (1 cup)"]["avoid"]
    assert dairy["Fortified soy milk (1 cup)"]["match"]


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
