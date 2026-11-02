import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import blocked_states as B
import app as A


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
    r = client.get("/")
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
    r = client.get("/")
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

def test_block_page_names_state_and_statute(client, monkeypatch):
    monkeypatch.setenv("GEO_BLOCK_ENABLED", "1")
    monkeypatch.setattr(B, "resolve_state", lambda ip, fetch=None: "CA")
    r = client.get("/")
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
    r = client.get("/")
    assert r.status_code == 451
    body = r.get_data(as_text=True)
    assert "Pennsylvania" in body
    assert "Genetic Information Privacy Act" in body
    assert "HB 1530" in body
    assert "palegis.us" in body


def test_alert_copy_covers_all_hard_blocked_states():
    for code in B.BLOCKED_STATES:
        info = B.alert_copy(code)
        assert info["state_name"]
        assert info["statute"]
        assert info["url"].startswith("http")
        assert code in info["message"] or info["state_name"] in info["message"]
