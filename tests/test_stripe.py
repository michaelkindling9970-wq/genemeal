import json

import blocked_states as B
import storage
import stripe_billing
from tests.helpers import post

SECRET = "whsec_testexample"


class _FakeStripe:
    def __init__(self):
        self.calls = []

    def request(self, method, path, params=None, *, idempotency_key=None):
        self.calls.append((method, path, params))
        assert path == "/v1/checkout/sessions"
        return {"id": "cs_1", "url": "https://checkout.stripe.com/c/pay/cs_1"}


CARD_LABEL = "Credit or Debit Card"


def _arm(monkeypatch, fake=None):
    monkeypatch.setenv("BILLING_ENABLED", "1")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_example")
    monkeypatch.setenv("STRIPE_PUBLISHABLE_KEY", "pk_test_example")
    monkeypatch.setenv("STRIPE_PRICE_ID", "price_example")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://genemeal.example")
    monkeypatch.setattr(B, "resolve_state", lambda ip, fetch=None: "OH")
    if fake is not None:
        monkeypatch.setattr(stripe_billing, "build_client", lambda: fake)


def _arm_paypal(monkeypatch):
    for key, value in {
        "PAYPAL_CLIENT_ID": "c",
        "PAYPAL_CLIENT_SECRET": "s",
        "PAYPAL_WEBHOOK_ID": "W",
        "PAYPAL_PLAN_ID": "P",
    }.items():
        monkeypatch.setenv(key, value)


def _uid(client):
    client.get("/")
    with client.session_transaction() as sess:
        return sess["uid"]


def _send(client, event, secret=SECRET):
    raw = json.dumps(event).encode()
    return client.post(
        "/stripe/webhook",
        data=raw,
        headers={
            "Stripe-Signature": stripe_billing.sign_payload(raw, secret),
            "Content-Type": "application/json",
        },
    )


def test_missing_keys_show_coming_soon_and_do_not_start_checkout(client):
    for path in ("/", "/pricing"):
        response = client.get(path)
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert 'id="pay-card"' in body
        assert 'id="pay-paypal"' in body
        assert body.index('id="pay-card"') < body.index('id="pay-paypal"')
        assert f">{CARD_LABEL}</button>" in body
        assert ">PayPal</button>" in body
        assert stripe_billing.COMING_SOON_MESSAGE in body
        assert 'action="/stripe/checkout"' not in body
        card = body[body.index('id="pay-card"'):body.index("</button>", body.index('id="pay-card"'))]
        assert "Stripe" not in card
        assert "disabled" in body[body.rindex("<button", 0, body.index('id="pay-card"')):body.index("</button>", body.index('id="pay-card"'))]


def test_each_button_follows_its_own_keys(client, monkeypatch):
    _arm(monkeypatch)
    body = client.get("/pricing").get_data(as_text=True)
    assert f'<button type="submit" id="pay-card">{CARD_LABEL}</button>' in body
    assert 'id="pay-paypal" class="secondary" disabled' in body
    assert body.index('id="pay-card"') < body.index('id="pay-paypal"')
    assert stripe_billing.COMING_SOON_MESSAGE not in body
    _arm_paypal(monkeypatch)
    body = client.get("/pricing").get_data(as_text=True)
    assert '<button type="submit" id="pay-paypal">PayPal</button>' in body
    assert f'<button type="submit" id="pay-card">{CARD_LABEL}</button>' in body
    assert body.index(f">{CARD_LABEL}</button>") < body.index(">PayPal</button>")
    card = body[body.index('id="pay-card"'):body.index("</button>", body.index('id="pay-card"'))]
    assert card.endswith(CARD_LABEL)
    assert "Stripe" not in card


def test_checkout_session_is_subscription(client, monkeypatch):
    fake = _FakeStripe()
    _arm(monkeypatch, fake)
    uid = _uid(client)
    resp = post(client, "/stripe/checkout")
    assert resp.status_code == 303
    assert resp.headers["Location"].startswith("https://checkout.stripe.com/")
    params = fake.calls[0][2]
    assert params["mode"] == "subscription"
    assert params["line_items"] == [{"price": "price_example", "quantity": 1}]
    assert params["client_reference_id"] == uid
    assert "payment_method_types" not in params
    page = client.get("/pricing").get_data(as_text=True)
    assert 'action="/stripe/checkout"' in page
    assert f">{CARD_LABEL}</button>" in page
    assert "sk_test_example" not in page
    assert "pk_test_example" not in page
    assert "price_example" not in page
    assert SECRET not in page


def test_missing_stripe_keys_do_not_call_stripe(client, monkeypatch):
    def _boom():
        raise AssertionError("Stripe client should not be built")

    monkeypatch.setattr(stripe_billing, "build_client", _boom)
    bare = post(client, "/stripe/checkout")
    assert bare.status_code == 302
    assert bare.status_code != 500
    for name in (
        "STRIPE_SECRET_KEY",
        "STRIPE_PUBLISHABLE_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "STRIPE_PRICE_ID",
    ):
        _arm(monkeypatch)
        monkeypatch.delenv(name)
        response = post(client, "/stripe/checkout")
        assert response.status_code == 302, name
        assert response.status_code != 500
        page = client.get("/").get_data(as_text=True)
        assert page
        assert stripe_billing.COMING_SOON_MESSAGE in page
        assert f">{CARD_LABEL}</button>" in page
        assert 'action="/stripe/checkout"' not in page
        home = client.get("/pricing")
        assert home.status_code == 200


def test_blocked_state_cannot_use_card(client, monkeypatch):
    fake = _FakeStripe()
    _arm(monkeypatch, fake)
    monkeypatch.delenv("GEO_BLOCK_ENABLED", raising=False)
    monkeypatch.setattr(B, "resolve_state", lambda ip, fetch=None: "CT")
    assert post(client, "/stripe/checkout").status_code == 451
    assert fake.calls == []
    body = client.get("/pricing").get_data(as_text=True)
    assert 'id="pay-card" class="secondary" disabled' in body
    assert body.index('id="pay-card"') < body.index('id="pay-paypal"')


def test_webhook_rejects_bad_signature(client, monkeypatch):
    _arm(monkeypatch)
    assert _send(client, {"id": "evt_x", "type": "invoice.paid"}, secret="whsec_wrong").status_code == 400


def test_webhook_is_geo_exempt(client, monkeypatch):
    _arm(monkeypatch)
    monkeypatch.setenv("GEO_BLOCK_ENABLED", "1")
    monkeypatch.setattr(B, "resolve_state", lambda ip, fetch=None: "CT")
    assert B.path_exempt("/stripe/webhook")
    assert _send(client, {"id": "evt_geo", "type": "ping"}).status_code == 200


def test_webhook_updates_status_and_keeps_paypal(client, monkeypatch):
    _arm(monkeypatch)
    uid = _uid(client)
    storage.set_billing(uid, subscription_id="I-PAYPAL1", status="canceled")
    event = {
        "id": "evt_1",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "client_reference_id": uid,
                "customer": "cus_1",
                "subscription": "sub_1",
                "payment_status": "paid",
            }
        },
    }
    assert _send(client, event).status_code == 200
    user = storage.get_user(uid)
    assert user["subscription_status"] == "active"
    assert user["stripe_customer_id"] == "cus_1"
    assert user["paypal_subscription_id"] == "I-PAYPAL1"
    gone = {
        "id": "evt_2",
        "type": "customer.subscription.deleted",
        "data": {"object": {"id": "sub_1", "customer": "cus_1", "status": "canceled"}},
    }
    assert _send(client, gone).status_code == 200
    assert storage.get_user(uid)["subscription_status"] == "canceled"
    assert _send(client, event).status_code == 200
    assert storage.get_user(uid)["subscription_status"] == "canceled"


def test_signature_timestamp_tolerance():
    raw = b"{}"
    header = stripe_billing.sign_payload(raw, SECRET, timestamp=1000)
    try:
        stripe_billing.verify_signature(raw, header, SECRET, now=5000)
    except stripe_billing.SignatureError:
        return
    raise AssertionError("old signature accepted")
