import traits
from tests.helpers import post, upload
from tests.samples import ROWS, genome_text, genome_zip, make_zip
from tests.test_dietplan import _paid

ACTN3 = ("rs1815739", "11", "66328095", "TT")


def _upload(client, confirm=True):
    name, raw = make_zip({"genome_Synthetic.txt": genome_text(list(ROWS) + [ACTN3])})
    upload(client, name, raw)
    if confirm:
        return post(client, "/parse/confirm")


def _notes(client):
    summ = traits.summarize({"genotypes": {r[0]: r[3] for r in list(ROWS) + [ACTN3]}, "marker_count": 1})
    return summ["highlights"]


def test_free_results_show_labels_not_advice(client):
    _upload(client, confirm=False)
    page = client.get("/results").get_data(as_text=True)
    rows = [r for r in _notes(client) if r["gene"] != "ACTN3"]
    assert rows
    for r in rows:
        assert r["label"] in page
        assert str(__import__("markupsafe").escape(r["note"][:40])) not in page
    assert "ACTN3" not in page and "Muscle" not in page and "muscle" not in page
    assert "Unlock your personalized diet suggestions" in page


def test_confirm_sends_free_user_to_results(client):
    resp = _upload(client)
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/results")


def test_free_user_plan_gated(client):
    _upload(client)
    for resp in (client.get("/plan"), post(client, "/plan", {"build_muscle": "on"}),
                 post(client, "/plan", {"weight_loss": "on"}), post(client, "/plan")):
        assert resp.status_code == 302 and resp.headers["Location"].endswith("/pricing")
    assert "subscription" in client.get("/pricing").get_data(as_text=True)
    home = client.get("/").get_data(as_text=True)
    assert 'href="/plan"' not in home


def test_subscriber_sees_advice_and_muscle(client):
    _paid(client)
    _upload(client)
    page = client.get("/results").get_data(as_text=True)
    for r in _notes(client):
        assert str(__import__("markupsafe").escape(r["note"][:40])) in page
    assert "Muscle fiber type" in page and "ACTN3" in page
    assert "Unlock your personalized" not in page
    assert "Build muscle" in client.get("/plan").get_data(as_text=True)
    assert post(client, "/plan", {"build_muscle": "on"}).status_code == 200
