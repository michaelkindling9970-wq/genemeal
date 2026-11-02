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
    monkeypatch.delenv("GEO_BLOCK_ENABLED", raising=False)
    A.app.config["TESTING"] = True
    return A.app.test_client()


def test_blocked_states_list():
    need = {"AL","AZ","CA","FL","IL","IN","KY","MD","MT","NE","RI","SD","TN","TX","UT","VA","VT","WA","WY"}
    assert need <= B.BLOCKED_STATES
    assert B.is_blocked_state("CA") and not B.is_blocked_state("PA")


def test_off_by_default(client, monkeypatch):
    monkeypatch.delenv("GEO_BLOCK_ENABLED", raising=False)
    monkeypatch.setattr(B, "resolve_state", lambda ip, fetch=None: "CA")
    assert client.get("/").status_code == 200


def test_denies_blocked_state(client, monkeypatch):
    monkeypatch.setenv("GEO_BLOCK_ENABLED", "1")
    monkeypatch.setattr(B, "resolve_state", lambda ip, fetch=None: "CA")
    r = client.get("/")
    assert r.status_code == 451
    assert "Not available in your area" in r.get_data(as_text=True)


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
