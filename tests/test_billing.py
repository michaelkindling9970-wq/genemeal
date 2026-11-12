import json

import billing
import blocked_states as B
import storage
from tests.helpers import post

SIG_HEADERS = {
    "PAYPAL-AUTH-ALGO": "SHA256withRSA",
    "PAYPAL-CERT-URL": "https://api.sandbox.paypal.com/v1/notifications/certs/CERT-1",
    "PAYPAL-TRANSMISSION-ID": "tx-1",
    "PAYPAL-TRANSMISSION-SIG": "sig",
    "PAYPAL-TRANSMISSION-TIME": "2026-11-02T22:00:00Z",
    "Content-Type": "application/json",
}


class _FakePayPal:
    def __init__(self, verify="SUCCESS"):
        self.calls = []
        self.verify = verify

    def request(self, method, path, body=None, *, request_id=None):
        self.calls.append((method, path, body))
        if path == "/v1/billing/subscriptions":
            return {
                "id": "I-SUB123",
                "status": "APPROVAL_PENDING",
                "links": [
                    {"rel": "approve", "href": "https://www.sandbox.paypal.com/webapps/billing/subscriptions?ba_token=BA-1"},
                    {"rel": "self", "href": "https://api-m.sandbox.paypal.com/v1/billing/subscriptions/I-SUB123"},
                ],
            }
        if path == "/v1/notifications/verify-webhook-signature":
            return {"verification_status": self.verify}
        if path == "/v1/catalogs/products":
            return {"id": "PROD-1"}
        if path == "/v1/billing/plans":
            return {"id": "P-PLAN1", "status": "ACTIVE"}
        raise AssertionError(path)

    def paths(self):
        return [c[1] for c in self.calls]


def _arm_keys(monkeypatch, fake=None):
    monkeypatch.setenv("BILLING_ENABLED", "1")
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "client-id-example")
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "client-secret-example")
    monkeypatch.setenv("PAYPAL_WEBHOOK_ID", "WH-EXAMPLE")
    monkeypatch.setenv("PAYPAL_PLAN_ID", "P-PLAN1")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://genemeal.example")
    if fake is not None:
        monkeypatch.setattr(billing, "build_client", lambda: fake)


def _uid(client):
    client.get("/")
    with client.session_transaction() as sess:
        return sess["uid"]


def _hook(client, event):
    return client.post("/paypal/webhook", data=json.dumps(event), headers=SIG_HEADERS)


def test_env_defaults_to_sandbox(monkeypatch):
    assert billing.paypal_env() == "sandbox"
    assert billing.api_base() == "https://api-m.sandbox.paypal.com"
    monkeypatch.setenv("PAYPAL_ENV", "live")
    assert billing.api_base() == "https://api-m.paypal.com"
    monkeypatch.setenv("PAYPAL_ENV", "bogus")
    assert billing.paypal_env() == "sandbox"


def test_soft_descriptor_is_genemeal_brand():
    assert billing.SOFT_DESCRIPTOR == "GENEMEAL"
    assert len(billing.SOFT_DESCRIPTOR) <= 22
    assert "gmail" not in billing.SOFT_DESCRIPTOR.lower()
    assert "paypal" not in billing.SOFT_DESCRIPTOR.lower()


def test_missing_keys_do_not_crash_and_disable_subscribe(client):
    response = post(client, "/billing/checkout")
    assert response.status_code == 302
    page = client.get("/").get_data(as_text=True)
    assert billing.KEYS_MISSING_MESSAGE in page
    assert "disabled" in page
    assert client.post("/paypal/webhook", data=b"{}").status_code == 503
    assert client.get("/pricing").status_code == 200


def test_billing_off_refuses_checkout_without_calling_paypal(client, monkeypatch):
    _arm_keys(monkeypatch)
    monkeypatch.setenv("BILLING_ENABLED", "0")

    def _boom():
        raise AssertionError("PayPal client should not be built")

    monkeypatch.setattr(billing, "build_client", _boom)
    response = post(client, "/billing/checkout")
    assert response.status_code == 302
    assert billing.BILLING_OFF_MESSAGE in client.get("/").get_data(as_text=True)


def test_checkout_creates_subscription_and_redirects_to_approval(client, monkeypatch):
    fake = _FakePayPal()
    _arm_keys(monkeypatch, fake)
    uid = _uid(client)
    response = post(client, "/billing/checkout")
    assert response.status_code == 303
    assert response.location.startswith("https://www.sandbox.paypal.com/webapps/billing/subscriptions")
    method, path, body = fake.calls[0]
    assert (method, path) == ("POST", "/v1/billing/subscriptions")
    assert body["plan_id"] == "P-PLAN1"
    assert body["custom_id"] == uid
    ctx = body["application_context"]
    assert ctx["return_url"] == "https://genemeal.example/billing/success"
    assert ctx["cancel_url"] == "https://genemeal.example/billing/cancel"
    assert ctx["brand_name"] == "GeneMeal"
    user = storage.get_user(uid)
    assert user["paypal_subscription_id"] == "I-SUB123"
    assert user["subscription_status"] == "incomplete"
    page = client.get("/").get_data(as_text=True)
    assert 'action="/billing/checkout"' in page
    assert "client-secret-example" not in page
    assert "P-PLAN1" not in page


def test_plan_is_13_usd_monthly():
    fake = _FakePayPal()
    result = billing.create_product_and_plan(fake)
    assert result["plan_id"] == "P-PLAN1"
    plan = fake.calls[1][2]
    assert plan["product_id"] == "PROD-1"
    cycle = plan["billing_cycles"][0]
    assert cycle["frequency"] == {"interval_unit": "MONTH", "interval_count": 1}
    assert cycle["pricing_scheme"]["fixed_price"] == {"value": "13.00", "currency_code": "USD"}


def test_webhook_activated_then_sale_then_cancelled(client, monkeypatch):
    fake = _FakePayPal()
    _arm_keys(monkeypatch, fake)
    uid = _uid(client)
    event = {
        "id": "WH-EVT-1",
        "event_type": "BILLING.SUBSCRIPTION.ACTIVATED",
        "resource": {"id": "I-SUB9", "status": "ACTIVE", "custom_id": uid},
    }
    response = _hook(client, event)
    assert response.status_code == 200, response.get_data(as_text=True)
    verify = [c for c in fake.calls if c[1] == "/v1/notifications/verify-webhook-signature"][0][2]
    assert verify["webhook_id"] == "WH-EXAMPLE"
    assert verify["transmission_id"] == "tx-1"
    assert verify["webhook_event"]["id"] == "WH-EVT-1"
    user = storage.get_user(uid)
    assert user["subscription_status"] == "active"
    assert user["paypal_subscription_id"] == "I-SUB9"
    assert _hook(client, event).status_code == 200  # replay is a no-op
    assert "Subscription active." in client.get("/").get_data(as_text=True)

    storage.set_billing(uid, status="past_due")
    sale = {
        "id": "WH-EVT-2",
        "event_type": "PAYMENT.SALE.COMPLETED",
        "resource": {"id": "SALE-1", "billing_agreement_id": "I-SUB9", "state": "completed"},
    }
    assert _hook(client, sale).status_code == 200
    assert storage.get_user(uid)["subscription_status"] == "active"

    cancel = {
        "id": "WH-EVT-3",
        "event_type": "BILLING.SUBSCRIPTION.CANCELLED",
        "resource": {"id": "I-SUB9", "status": "CANCELLED"},
    }
    assert _hook(client, cancel).status_code == 200
    assert storage.get_user(uid)["subscription_status"] == "canceled"


def test_webhook_rejects_failed_verification(client, monkeypatch):
    fake = _FakePayPal(verify="FAILURE")
    _arm_keys(monkeypatch, fake)
    uid = _uid(client)
    event = {"id": "WH-BAD", "event_type": "BILLING.SUBSCRIPTION.ACTIVATED",
             "resource": {"id": "I-X", "custom_id": uid}}
    assert _hook(client, event).status_code == 400
    assert storage.get_user(uid)["subscription_status"] in (None, "")


def test_webhook_rejects_missing_signature_headers(client, monkeypatch):
    fake = _FakePayPal()
    _arm_keys(monkeypatch, fake)
    response = client.post("/paypal/webhook", data=b"{}", headers={"Content-Type": "application/json"})
    assert response.status_code == 400
    assert fake.calls == []


def test_payment_failed_marks_past_due(client, monkeypatch):
    uid = _uid(client)
    storage.set_billing(uid, subscription_id="I-DUE", status="active")
    billing.apply_event({"id": "E-F", "event_type": "BILLING.SUBSCRIPTION.PAYMENT.FAILED",
                         "resource": {"id": "I-DUE"}})
    assert storage.get_user(uid)["subscription_status"] == "past_due"


def test_unknown_subscriber_returns_500_so_paypal_retries(client, monkeypatch):
    fake = _FakePayPal()
    _arm_keys(monkeypatch, fake)
    event = {"id": "WH-NOUSER", "event_type": "BILLING.SUBSCRIPTION.ACTIVATED",
             "resource": {"id": "I-NOPE"}}
    assert _hook(client, event).status_code == 500
    assert storage.claim_paypal_event("WH-NOUSER", "x") is True


def test_webhook_is_exempt_from_geo_block(client, monkeypatch):
    B.clear_cache()
    monkeypatch.setenv("GEO_BLOCK_ENABLED", "1")
    monkeypatch.setattr(B, "resolve_state", lambda ip, fetch=None: "TX")
    assert client.post("/paypal/webhook", data=b"{}").status_code == 503


def test_paypal_module_does_not_embed_stripe_or_square():
    """PayPal stays in billing.py. Card checkout lives in stripe_billing.py."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    for name in ("billing.py", "requirements.txt"):
        text = (root / name).read_text().lower()
        assert "stripe" not in text, name
        assert "squareup" not in text, name
    for name in ("app.py", "storage.py", "blocked_states.py", "stripe_billing.py"):
        text = (root / name).read_text().lower()
        assert "squareup" not in text, name


def test_repo_does_not_contain_retired_account_fragment():
    from pathlib import Path

    retired = "kmX" + "Si"
    root = Path(__file__).resolve().parents[1]
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in {".git", ".venv", "venv", "__pycache__", ".pytest_cache"} for part in path.parts):
            continue
        if path.suffix.lower() not in {".py", ".html", ".md", ".css", ".txt", ".ini"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert retired not in text, path


def test_blocked_state_cannot_start_checkout(client, monkeypatch):
    """Blocked-state visitors are never charged, even when GEO_BLOCK_ENABLED is off."""
    fake = _FakePayPal()
    _arm_keys(monkeypatch, fake)
    monkeypatch.delenv("GEO_BLOCK_ENABLED", raising=False)
    monkeypatch.setattr(B, "resolve_state", lambda ip, fetch=None: "CT")
    response = post(client, "/billing/checkout")
    assert response.status_code == 451
    body = response.get_data(as_text=True)
    assert "Connecticut" in body
    assert "prevents you from using this service" in body
    assert fake.calls == []
    home = client.get("/").get_data(as_text=True)
    assert "disabled" in home
    assert "Connecticut" in home
    assert home.index(">Credit or Debit Card</button>") < home.index(">PayPal</button>")


def test_non_blocked_state_can_start_checkout(client, monkeypatch):
    fake = _FakePayPal()
    _arm_keys(monkeypatch, fake)
    monkeypatch.delenv("GEO_BLOCK_ENABLED", raising=False)
    monkeypatch.setattr(B, "resolve_state", lambda ip, fetch=None: "OH")
    assert post(client, "/billing/checkout").status_code == 303
    assert fake.paths() == ["/v1/billing/subscriptions"]


def test_pa_cannot_be_charged_after_bill_enacted(client, monkeypatch):
    fake = _FakePayPal()
    _arm_keys(monkeypatch, fake)
    monkeypatch.delenv("GEO_BLOCK_ENABLED", raising=False)
    monkeypatch.setattr(B, "resolve_state", lambda ip, fetch=None: "PA")
    assert "PA" in B.refresh_pending_watches(fetch=lambda w: "Became Law")
    response = post(client, "/billing/checkout")
    assert response.status_code == 451
    assert "Pennsylvania" in response.get_data(as_text=True)
    assert fake.calls == []
