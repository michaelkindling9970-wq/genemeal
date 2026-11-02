import json
from types import SimpleNamespace

import billing
import blocked_states as B
import storage
from tests.helpers import post


class _Sessions:
    def __init__(self):
        self.params = None

    def create(self, params=None, options=None):
        self.params = params
        return SimpleNamespace(id="cs_test_session", url="https://checkout.stripe.com/c/pay/cs_test_session")


class _Customers:
    def __init__(self):
        self.params = None

    def create(self, params=None, options=None):
        self.params = params
        return SimpleNamespace(id="cus_created")


class _FakeStripe:
    def __init__(self):
        self.sessions = _Sessions()
        self.customers = _Customers()
        self.checkout = SimpleNamespace(sessions=self.sessions)


def _arm_keys(monkeypatch, fake=None):
    monkeypatch.setenv("BILLING_ENABLED", "1")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "rk_test_example")
    monkeypatch.setenv("STRIPE_PUBLISHABLE_KEY", "pk_test_example")
    monkeypatch.setenv("STRIPE_PRICE_ID", "price_example_monthly")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_example")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://genemeal.example")
    if fake is not None:
        monkeypatch.setattr(billing, "build_client", lambda: fake)


def test_missing_keys_do_not_crash_and_disable_subscribe(client):
    response = post(client, "/billing/checkout")
    assert response.status_code == 302
    page = client.get("/").get_data(as_text=True)
    assert response.location.endswith("/")
    assert billing.KEYS_MISSING_MESSAGE in page
    assert "disabled" in page
    assert "rk_test_" not in page
    assert "whsec_" not in page
    webhook = client.post("/stripe/webhook", data=b"{}")
    assert webhook.status_code == 503
    assert client.get("/pricing").status_code == 200


def test_billing_off_refuses_checkout_without_calling_stripe(client, monkeypatch):
    fake = _FakeStripe()
    _arm_keys(monkeypatch, fake)
    monkeypatch.setenv("BILLING_ENABLED", "0")

    def _boom():
        raise AssertionError("Stripe client should not be built")

    monkeypatch.setattr(billing, "build_client", _boom)
    response = post(client, "/billing/checkout")
    assert response.status_code == 302
    page = client.get("/").get_data(as_text=True)
    assert billing.BILLING_OFF_MESSAGE in page
    assert "disabled" in page
    assert fake.sessions.params is None


def test_checkout_session_is_subscription_for_price_id(client, monkeypatch):
    fake = _FakeStripe()
    _arm_keys(monkeypatch, fake)
    response = post(client, "/billing/checkout")
    assert response.status_code == 303
    assert response.location == "https://checkout.stripe.com/c/pay/cs_test_session"
    params = fake.sessions.params
    assert params["mode"] == "subscription"
    assert params["line_items"] == [{"price": "price_example_monthly", "quantity": 1}]
    assert "payment_method_types" not in params
    assert params["success_url"] == "https://genemeal.example/billing/success?session_id={CHECKOUT_SESSION_ID}"
    assert params["cancel_url"] == "https://genemeal.example/billing/cancel"
    assert params["integration_identifier"] == billing.INTEGRATION_IDENTIFIER
    assert params["integration_identifier"].endswith("kwmnpqrx")
    assert fake.customers.params["metadata"]["genemeal_user_id"] == params["client_reference_id"]
    page = client.get("/").get_data(as_text=True)
    assert 'action="/billing/checkout"' in page
    assert billing.KEYS_MISSING_MESSAGE not in page
    assert "rk_test_example" not in page
    assert "price_example_monthly" not in page


def test_webhook_paid_session_marks_subscription_active(client, monkeypatch):
    _arm_keys(monkeypatch)
    client.get("/")
    with client.session_transaction() as sess:
        uid = sess["uid"]
    storage.set_billing(uid, customer_id="cus_test_1")
    payload = {
        "id": "evt_paid_1",
        "object": "event",
        "api_version": billing.API_VERSION,
        "created": 1710000000,
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_1",
                "object": "checkout.session",
                "mode": "subscription",
                "payment_status": "paid",
                "customer": "cus_test_1",
                "subscription": "sub_test_1",
                "client_reference_id": uid,
                "status": "complete",
            }
        },
        "livemode": False,
        "pending_webhooks": 1,
        "request": {"id": None, "idempotency_key": None},
    }
    raw = json.dumps(payload)
    header = billing.stripe.WebhookSignature.generate_signature_header(raw, "whsec_example")
    response = client.post(
        "/stripe/webhook",
        data=raw,
        headers={"Stripe-Signature": header, "Content-Type": "application/json"},
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    user = storage.get_user(uid)
    assert user["subscription_status"] == "active"
    assert user["stripe_subscription_id"] == "sub_test_1"
    again = client.post(
        "/stripe/webhook",
        data=raw,
        headers={"Stripe-Signature": header, "Content-Type": "application/json"},
    )
    assert again.status_code == 200
    page = client.get("/").get_data(as_text=True)
    assert "Subscription active." in page


def test_webhook_rejects_bad_signature(client, monkeypatch):
    _arm_keys(monkeypatch)
    response = client.post(
        "/stripe/webhook",
        data=b"{}",
        headers={"Stripe-Signature": "t=1,v1=nope"},
    )
    assert response.status_code == 400


def test_unpaid_checkout_does_not_activate(client):
    client.get("/")
    with client.session_transaction() as sess:
        uid = sess["uid"]
    storage.set_billing(uid, customer_id="cus_wait")
    billing.apply_event(
        {
            "id": "evt_unpaid",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "payment_status": "unpaid",
                    "customer": "cus_wait",
                    "subscription": "sub_wait",
                    "client_reference_id": uid,
                }
            },
        }
    )
    assert storage.get_user(uid)["subscription_status"] == "incomplete"


def test_invoice_payment_failed_marks_past_due(client):
    client.get("/")
    with client.session_transaction() as sess:
        uid = sess["uid"]
    storage.set_billing(uid, customer_id="cus_due", subscription_id="sub_due", status="active")
    billing.apply_event(
        {
            "id": "evt_fail",
            "type": "invoice.payment_failed",
            "data": {
                "object": {
                    "customer": "cus_due",
                    "parent": {"subscription_details": {"subscription": "sub_due"}},
                }
            },
        }
    )
    assert storage.get_user(uid)["subscription_status"] == "past_due"


def test_webhook_is_exempt_from_geo_block(client, monkeypatch):
    B.clear_cache()
    monkeypatch.setenv("GEO_BLOCK_ENABLED", "1")
    monkeypatch.setattr(B, "resolve_state", lambda ip, fetch=None: "TX")
    response = client.post("/stripe/webhook", data=b"{}")
    assert response.status_code == 503


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
    fake = _FakeStripe()
    _arm_keys(monkeypatch, fake)
    monkeypatch.delenv("GEO_BLOCK_ENABLED", raising=False)
    monkeypatch.setattr(B, "resolve_state", lambda ip, fetch=None: "CT")

    response = post(client, "/billing/checkout")
    assert response.status_code == 451
    body = response.get_data(as_text=True)
    assert "Connecticut" in body
    assert "prevents you from using this service" in body
    assert fake.sessions.params is None

    home = client.get("/").get_data(as_text=True)
    assert "disabled" in home
    assert "Connecticut" in home
    assert "Subscribe" in home


def test_non_blocked_state_can_start_checkout(client, monkeypatch):
    fake = _FakeStripe()
    _arm_keys(monkeypatch, fake)
    monkeypatch.delenv("GEO_BLOCK_ENABLED", raising=False)
    monkeypatch.setattr(B, "resolve_state", lambda ip, fetch=None: "OH")

    response = post(client, "/billing/checkout")
    assert response.status_code == 303
    assert fake.sessions.params is not None


def test_pa_cannot_be_charged_after_bill_enacted(client, monkeypatch):
    fake = _FakeStripe()
    _arm_keys(monkeypatch, fake)
    monkeypatch.delenv("GEO_BLOCK_ENABLED", raising=False)
    monkeypatch.setattr(B, "resolve_state", lambda ip, fetch=None: "PA")
    assert "PA" in B.refresh_pending_watches(fetch=lambda w: "Became Law")

    response = post(client, "/billing/checkout")
    assert response.status_code == 451
    assert "Pennsylvania" in response.get_data(as_text=True)
    assert fake.sessions.params is None
