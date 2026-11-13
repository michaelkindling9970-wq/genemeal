import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import blocked_states as B
import site_meta
import app as A

SITE_TITLE = "Nutrigenomics Meal Plans from Your DNA | GeneMeal"
SITE_DESCRIPTION = (
    "Nutrigenomics meal plans from your DNA: GeneMeal turns the raw DNA file from your DNA testing service "
    "into a gene-based diet with personalized nutrition targets. Educational, not medical advice."
)


@pytest.fixture
def client(monkeypatch):
    B.clear_cache()
    B.clear_auto_blocked()
    monkeypatch.delenv("GEO_BLOCK_ENABLED", raising=False)
    monkeypatch.delenv("GEO_BLOCK_FORCE_ENACTED", raising=False)
    A.app.config["TESTING"] = True
    return A.app.test_client()


@pytest.fixture(autouse=True)
def _reset_bill_watch():
    B.clear_cache()
    B.clear_auto_blocked()
    yield
    B.clear_cache()
    B.clear_auto_blocked()


def test_blocked_states_list():
    need = {"AL","AZ","CA","CT","FL","IL","IN","KY","MD","MN","MT","NE","RI","SD","TN","TX","UT","VA","VT","WA","WY"}
    assert need <= B.BLOCKED_STATES
    assert "PA" not in B.BLOCKED_STATES
    assert any(w["state"] == "PA" for w in B.PENDING_WATCHES)
    assert B.is_blocked_state("CA", refresh=False) and B.is_blocked_state("CT", refresh=False) and B.is_blocked_state("MN", refresh=False)
    assert not B.is_blocked_state("PA", fetch=lambda w: "Engrossed — 50% progression")


def test_off_by_default(client, monkeypatch):
    monkeypatch.delenv("GEO_BLOCK_ENABLED", raising=False)
    monkeypatch.setattr(B, "resolve_state", lambda ip, fetch=None: "CA")
    assert client.get("/").status_code == 200


def test_denies_blocked_state(client, monkeypatch):
    monkeypatch.setenv("GEO_BLOCK_ENABLED", "1")
    monkeypatch.setattr(B, "resolve_state", lambda ip, fetch=None: "CA")
    home = client.get("/")
    assert home.status_code == 200
    assert "Not available in California" not in home.get_data(as_text=True)
    r = client.get("/results")
    assert r.status_code == 451
    assert "Not available in California" in r.get_data(as_text=True)
    assert "Genetic Information Privacy Act" in r.get_data(as_text=True)


def test_allows_other_state(client, monkeypatch):
    monkeypatch.setenv("GEO_BLOCK_ENABLED", "1")
    monkeypatch.setattr(B, "resolve_state", lambda ip, fetch=None: "PA")
    assert client.get("/").status_code == 200


def test_allows_unknown(client, monkeypatch):
    monkeypatch.setenv("GEO_BLOCK_ENABLED", "1")
    monkeypatch.setattr(B, "resolve_state", lambda ip, fetch=None: None)
    assert client.get("/").status_code == 200


def test_exempts_robots(client, monkeypatch):
    monkeypatch.setenv("GEO_BLOCK_ENABLED", "1")
    monkeypatch.setattr(B, "resolve_state", lambda ip, fetch=None: "TX")
    assert client.get("/robots.txt").status_code == 200

def test_pa_pending_not_blocked():
    assert not B.is_blocked_state("PA", fetch=lambda w: "Status: Engrossed on December 16 2025 - 50% progression")


def test_pa_auto_blocks_when_bill_enacted():
    assert B.is_blocked_state("PA", fetch=lambda w: "Status: Became Law")
    # Persistence: later pending page still blocks
    assert B.is_blocked_state("PA", fetch=lambda w: "still in committee")


def test_pa_force_env(monkeypatch):
    monkeypatch.setenv("GEO_BLOCK_FORCE_ENACTED", "PA")
    assert B.is_blocked_state("PA", fetch=lambda w: "pending only", refresh=True)


def test_denies_pa_after_enacted(client, monkeypatch):
    monkeypatch.setenv("GEO_BLOCK_ENABLED", "1")
    monkeypatch.setattr(B, "resolve_state", lambda ip, fetch=None: "PA")
    # Pretend the bill page shows enacted
    monkeypatch.setattr(
        B,
        "check_watch_enacted",
        lambda watch, fetch=None, now=None: watch["state"] == "PA",
    )
    # Also seed persist path via refresh
    assert "PA" in B.refresh_pending_watches(fetch=lambda w: "Became Law")
    assert client.get("/").status_code == 200
    r = client.get("/results")
    assert r.status_code == 451


def test_allows_pa_while_pending(client, monkeypatch):
    monkeypatch.setenv("GEO_BLOCK_ENABLED", "1")
    monkeypatch.setattr(B, "resolve_state", lambda ip, fetch=None: "PA")
    monkeypatch.setattr(
        B,
        "check_watch_enacted",
        lambda watch, fetch=None, now=None: False,
    )
    assert client.get("/").status_code == 200

def test_va_block_page_preview_uses_site_defaults(client, monkeypatch):
    """A blocked route's 451 page keeps GeneMeal's normal link preview, including the share image."""
    assert site_meta.SITE_TITLE == SITE_TITLE
    assert site_meta.SITE_DESCRIPTION == SITE_DESCRIPTION
    monkeypatch.setenv("GEO_BLOCK_ENABLED", "1")
    monkeypatch.setattr(B, "resolve_state", lambda ip, fetch=None: "VA")
    home = client.get("/")
    assert home.status_code == 200
    assert "Not available in Virginia" not in home.get_data(as_text=True)
    r = client.get("/results")
    assert r.status_code == 451
    page = r.get_data(as_text=True)
    head, _, body = page.partition("</head>")
    assert f"<title>{SITE_TITLE}</title>" in head
    assert f'<meta name="description" content="{SITE_DESCRIPTION}">' in head
    assert '<meta property="og:type" content="website">' in head
    assert '<meta property="og:site_name" content="GeneMeal">' in head
    assert f'<meta property="og:title" content="{SITE_TITLE}">' in head
    assert f'<meta property="og:description" content="{SITE_DESCRIPTION}">' in head
    assert '<meta property="og:url" content="https://genemeal.onrender.com/">' in head
    assert f'<meta property="og:image" content="{site_meta.OG_IMAGE_URL}">' in head
    assert '<meta property="og:image:width" content="1200">' in head
    assert '<meta property="og:image:height" content="630">' in head
    assert f'<meta property="og:image:alt" content="{site_meta.OG_IMAGE_ALT}">' in head
    assert f'<meta name="twitter:card" content="{site_meta.TWITTER_CARD}">' in head
    assert f'<meta name="twitter:image" content="{site_meta.OG_IMAGE_URL}">' in head
    assert "<h1>Not available in Virginia</h1>" in body
    assert "Virginia state statute Genetic privacy protections prevents you from using this service." in body
    assert ">Genetic privacy protections</span>" in body
    assert "Read the full statute text" in body
    assert "https://law.lis.virginia.gov/" in body
    assert "try again without a VPN" in body


def test_block_page_names_state_and_statute(client, monkeypatch):
    monkeypatch.setenv("GEO_BLOCK_ENABLED", "1")
    monkeypatch.setattr(B, "resolve_state", lambda ip, fetch=None: "CA")
    r = client.get("/results")
    assert r.status_code == 451
    body = r.get_data(as_text=True)
    assert "California" in body
    assert "Genetic Information Privacy Act" in body
    assert "prevents you from using this service" in body
    assert "Read the full statute text" in body
    assert "leginfo.legislature.ca.gov" in body
    assert "<style>" in body  # styled page


def test_pa_alert_once_enacted(client, monkeypatch):
    monkeypatch.setenv("GEO_BLOCK_ENABLED", "1")
    monkeypatch.setattr(B, "resolve_state", lambda ip, fetch=None: "PA")
    assert "PA" in B.refresh_pending_watches(fetch=lambda w: "Became Law")
    assert client.get("/").status_code == 200
    r = client.get("/billing/success")
    assert r.status_code == 451
    body = r.get_data(as_text=True)
    assert "Pennsylvania" in body
    assert "Genetic Information Privacy Act" in body
    assert "HB 1530" in body
    assert "palegis.us" in body


CONTENT_STATUS = {
    "/": 200,
    "/pricing": 200,
    "/research/stress-diet": 200,
    "/unsubscribe": 200,
    "/robots.txt": 200,
    "/sitemap.xml": 200,
    "/favicon.ico": 204,
    "/static/style.css": 200,
    "/static/og.png": 200,
    "/health": 200,
}
BLOCKED_GET = (
    "/results",
    "/plan",
    "/diet",
    "/billing/success",
    "/billing/cancel",
    "/preview-login",
    "/account/status",
)
BLOCKED_POST = (
    "/upload",
    "/parse/confirm",
    "/plan",
    "/billing/checkout",
    "/stripe/checkout",
    "/account/requested",
    "/account/waiting",
    "/account/reminders/process",
    "/account/data",
)


def _as_state(code):
    return lambda ip, fetch=None, code=code: code


@pytest.mark.parametrize("state", ["CA", "VA"])
def test_content_open_sensitive_blocked(client, monkeypatch, state):
    monkeypatch.setenv("GEO_BLOCK_ENABLED", "1")
    monkeypatch.setattr(B, "resolve_state", _as_state(state))
    for path, status in CONTENT_STATUS.items():
        response = client.get(path)
        assert response.status_code == status, path
        if path in ("/", "/pricing", "/research/stress-diet", "/unsubscribe"):
            assert "Not available in" not in response.get_data(as_text=True)
    for path in BLOCKED_GET:
        response = client.get(path)
        assert response.status_code == 451, path
        assert "Not available in" in response.get_data(as_text=True)
    for path in BLOCKED_POST:
        response = client.post(path)
        assert response.status_code == 451, path
    assert client.post("/paypal/webhook", data=b"{}").status_code != 451
    assert client.post("/PayPal/webhook", data=b"{}").status_code != 451
    assert client.post("/stripe/webhook", data=b"{}").status_code != 451


def test_sensitive_routes_work_for_allowed_state(client, monkeypatch):
    monkeypatch.setenv("GEO_BLOCK_ENABLED", "1")
    monkeypatch.setattr(B, "resolve_state", lambda ip, fetch=None: "NY")
    assert client.get("/").status_code == 200
    assert client.get("/results").status_code == 200
    assert client.get("/billing/success").status_code == 200
    assert client.get("/plan").status_code == 302
    assert client.get("/diet").status_code == 302
    assert client.get("/account/status").status_code == 200
    client.get("/")
    with client.session_transaction() as sess:
        token = sess["csrf"]
    upload = client.post("/upload", data={"csrf_token": token})
    assert upload.status_code == 302
    assert upload.status_code != 451
    checkout = client.post("/billing/checkout", data={"csrf_token": token})
    assert checkout.status_code == 302
    card = client.post("/stripe/checkout", data={"csrf_token": token})
    assert card.status_code == 302


def test_block_scope_matches_upload_results_billing():
    for path in CONTENT_STATUS:
        assert not B.path_is_blocked_scope(path), path
    for path in ("/paypal/webhook", "/PayPal/webhook", "/stripe/webhook", "/stripe/portal"):
        assert not B.path_is_blocked_scope(path), path
    for path in BLOCKED_GET + BLOCKED_POST:
        assert B.path_is_blocked_scope(path), path


def test_alert_copy_covers_all_hard_blocked_states():
    for code in B.BLOCKED_STATES:
        info = B.alert_copy(code)
        assert info["state_name"]
        assert info["statute"]
        assert info["url"].startswith("http")
        assert code in info["message"] or info["state_name"] in info["message"]
