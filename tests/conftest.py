import sys
import urllib.request
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _reset_geo_watch():
    import blocked_states as B
    B.clear_cache()
    B.clear_auto_blocked()
    yield
    B.clear_cache()
    B.clear_auto_blocked()


@pytest.fixture(autouse=True)
def _no_paypal_env(monkeypatch):
    """Checkout tests opt in by setting keys. A developer shell must not leak them."""
    for name in (
        "PAYPAL_CLIENT_ID",
        "PAYPAL_CLIENT_SECRET",
        "PAYPAL_WEBHOOK_ID",
        "PAYPAL_PLAN_ID",
        "PAYPAL_ENV",
        "PREVIEW_MODE",
        "PREVIEW_TOKEN",
        "BILLING_ENABLED",
        "PUBLIC_BASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def _no_live_http(monkeypatch):
    """FoodData Central and any other HTTP stay off in the suite."""
    monkeypatch.setenv("GENEMEAL_FORBID_NETWORK", "1")

    def _blocked(*_args, **_kwargs):
        raise AssertionError("live HTTP is not allowed in tests")

    monkeypatch.setattr(urllib.request, "urlopen", _blocked)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GENEMEAL_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.delenv("FDC_API_KEY", raising=False)
    monkeypatch.delenv("REMINDER_EMAIL_ENABLED", raising=False)
    monkeypatch.delenv("GEO_BLOCK_ENABLED", raising=False)
    monkeypatch.delenv("GEO_BLOCK_FORCE_ENACTED", raising=False)
    import app as A

    A.app.config["TESTING"] = True
    A.app.config["SECRET_KEY"] = "test-secret"
    A.app.config["MAX_UPLOAD_BYTES"] = 50 * 1024 * 1024
    A.fdc_client_factory = None
    test_client = A.app.test_client()
    test_client.get("/")
    with test_client.session_transaction() as sess:
        test_client.csrf = sess["csrf"]
    return test_client


