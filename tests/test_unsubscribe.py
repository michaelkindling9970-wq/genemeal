import inspect
import re

import app as A
import blocked_states as B
import storage
import stripe_billing
from tests.helpers import post

PAGE_TEXT = (
    "Paid by card? Use the Manage card subscription button to cancel. "
    "Paid with PayPal? Cancel under Automatic payments in your PayPal account. "
    "Your subscription stops at the end of the current billing period."
)
PORTAL_URL = "https://billing.stripe.com/p/session/test_123"
LOGIN_OVERRIDE = "https://billing.stripe.com/p/login/override-example"


def _danger_zone(html: str) -> str:
    return html.split('<section class="danger-zone">', 1)[1].split("</section>", 1)[0]


def _uid(client):
    with client.session_transaction() as sess:
        return sess["uid"]


class _FakeStripe:
    def __init__(self, url=PORTAL_URL, body=None):
        self.calls = []
        self._url = url
        self._body = body

    def request(self, method, path, params=None, *, idempotency_key=None):
        self.calls.append((method, path, params, idempotency_key))
        if self._body is not None:
            return self._body
        return {"id": "bps_123", "url": self._url}


def _boom(*_args, **_kwargs):
    raise AssertionError("Stripe client should not be built")


def test_home_unsubscribe_sits_under_delete(client):
    html = client.get("/").get_data(as_text=True)
    zone = _danger_zone(html)
    form, after = zone.split("</form>", 1)
    assert 'action="/account/data"' in form
    assert 'name="confirm"' in form
    assert '>Delete my data</button>' in form
    assert "Delete and Unsubscribe" not in form
    assert "Delete and Unsubscribe" not in html
    link = re.search(
        r'<p><a class="button" href="(/unsubscribe)">Unsubscribe</a></p>',
        after,
    )
    assert link, after
    assert link.group(1) == "/unsubscribe"
    assert ">Unsubscribe</a>" in html
    assert "This allows you to unsubscribe as well." not in html
    assert "This allows you to unsubscribe as well." not in after
    assert "Manage card subscription" not in html


def test_home_leaves_other_controls_in_place(client):
    html = client.get("/").get_data(as_text=True)
    assert html.index(">Open 23andMe raw data</a>") < html.index(">Open Ancestry raw data</a>")
    card_at = html.index('id="pay-card"')
    paypal_at = html.index('id="pay-paypal"')
    assert card_at < paypal_at
    assert ">Credit or Debit Card</button>" in html[card_at:paypal_at]
    assert ">PayPal</button>" in html[paypal_at:]
    footer = html.split("<footer>", 1)[1]
    assert "built from 11 genetic public nutrition markers and genetic calorie and protein placeholders." in footer
    assert "Nothing here is sent to 23andMe / Ancestry — there is no third-party API." not in html
    assert "Manage card subscription" not in html


def test_unsubscribe_page_explains_cancel_without_billing_calls(client, monkeypatch):
    monkeypatch.setattr("billing.build_client", _boom)
    monkeypatch.setattr("stripe_billing.build_client", _boom)
    source = inspect.getsource(A.unsubscribe)
    assert "billing." not in source
    assert "stripe" not in source

    response = client.get("/unsubscribe")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert PAGE_TEXT in page
    assert "GeneMeal does not have a card cancellation page." not in page
    assert ">Manage card subscription</button>" in page
    assert 'action="/stripe/portal"' in page
    assert 'name="csrf_token"' in page
    assert ">Back to the guide</a>" in page
    assert "/static/style.css" in page
    assert 'class="brand"' in page
    assert "<footer>" in page
    assert 'href="/"' in page
    assert "/billing/checkout" not in page
    assert "/stripe/checkout" not in page
    copy = page.split("<h1>", 1)[1].split("</section>", 1)[0]
    paragraphs = " ".join(re.findall(r"<p>(.*?)</p>", copy, flags=re.S))
    assert "mailto:" not in paragraphs
    assert not re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", paragraphs)
    assert not re.search(r"(?:\+?\d[\d\s().-]{7,}\d)", paragraphs)
    pricing = client.get("/pricing").get_data(as_text=True)
    assert "Manage card subscription" not in pricing
    assert pricing.index('id="pay-card"') < pricing.index('id="pay-paypal"')


def test_unsubscribe_is_open_in_blocked_states(client, monkeypatch):
    assert not B.path_is_blocked_scope("/unsubscribe")
    assert not B.path_is_blocked_scope("/stripe/portal")
    assert B.path_is_blocked_scope("/stripe/checkout")
    monkeypatch.setenv("GEO_BLOCK_ENABLED", "1")
    monkeypatch.setattr(B, "resolve_state", lambda ip, fetch=None: "CA")
    response = client.get("/unsubscribe")
    assert response.status_code == 200
    assert "Not available in" not in response.get_data(as_text=True)


def test_portal_session_for_stored_customer(client, monkeypatch):
    fake = _FakeStripe()
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_example")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://genemeal.example")
    monkeypatch.setattr(stripe_billing, "build_client", lambda: fake)
    storage.set_stripe_billing(_uid(client), customer_id="cus_123")

    response = post(client, "/stripe/portal")

    assert response.status_code == 303
    assert response.headers["Location"] == PORTAL_URL
    assert len(fake.calls) == 1
    method, path, params, _idem = fake.calls[0]
    assert method == "POST"
    assert path == "/v1/billing_portal/sessions"
    assert params == {
        "customer": "cus_123",
        "return_url": "https://genemeal.example/unsubscribe",
    }
    assert "configuration" not in params
    assert "cancel" not in path
    assert "/v1/checkout/sessions" not in path
    assert "/v1/subscriptions" not in path


def test_portal_login_url_overrides_when_this_browser_has_no_customer(client, monkeypatch):
    monkeypatch.setenv("STRIPE_PORTAL_LOGIN_URL", LOGIN_OVERRIDE)
    monkeypatch.setattr(stripe_billing, "build_client", _boom)
    storage.set_stripe_billing(_uid(client), customer_id="   ")

    response = post(client, "/stripe/portal")

    assert response.status_code == 303
    assert response.headers["Location"] == LOGIN_OVERRIDE


def test_portal_uses_default_login_url_when_env_is_unset(client, monkeypatch):
    monkeypatch.delenv("STRIPE_PORTAL_LOGIN_URL", raising=False)
    monkeypatch.setattr(stripe_billing, "build_client", _boom)

    response = post(client, "/stripe/portal")

    assert response.status_code == 303
    assert response.headers["Location"] == stripe_billing.DEFAULT_PORTAL_LOGIN_URL
    assert response.headers["Location"] == "https://billing.stripe.com/p/login/6oU8wJ15b3vfc6c9Xpe3e00"


def test_portal_blank_env_still_uses_the_default_login_url(client, monkeypatch):
    monkeypatch.setenv("STRIPE_PORTAL_LOGIN_URL", "  ")
    monkeypatch.setattr(stripe_billing, "build_client", _boom)

    response = post(client, "/stripe/portal")

    assert response.status_code == 303
    assert response.headers["Location"] == stripe_billing.DEFAULT_PORTAL_LOGIN_URL


def test_portal_requires_csrf_and_does_not_call_stripe(client, monkeypatch):
    fake = _FakeStripe()
    monkeypatch.setattr(stripe_billing, "build_client", lambda: fake)
    storage.set_stripe_billing(_uid(client), customer_id="cus_123")

    response = client.post("/stripe/portal", data={})

    assert response.status_code == 400
    assert fake.calls == []


def test_portal_from_a_blocked_state_still_opens(client, monkeypatch):
    fake = _FakeStripe()
    monkeypatch.setenv("GEO_BLOCK_ENABLED", "1")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://genemeal.example")
    monkeypatch.setattr(B, "resolve_state", lambda ip, fetch=None: "CA")
    monkeypatch.setattr(stripe_billing, "build_client", lambda: fake)
    storage.set_stripe_billing(_uid(client), customer_id="cus_blocked")

    opened = post(client, "/stripe/portal")
    assert opened.status_code == 303
    assert opened.headers["Location"] == PORTAL_URL
    assert fake.calls[0][2]["customer"] == "cus_blocked"
    checkout = post(client, "/stripe/checkout")
    assert checkout.status_code == 451
    assert [call[1] for call in fake.calls] == ["/v1/billing_portal/sessions"]


def test_portal_works_where_billing_checkout_is_blocked(client, monkeypatch):
    fake = _FakeStripe()
    monkeypatch.delenv("GEO_BLOCK_ENABLED", raising=False)
    monkeypatch.setenv("BILLING_ENABLED", "1")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_example")
    monkeypatch.setenv("STRIPE_PUBLISHABLE_KEY", "pk_test_example")
    monkeypatch.setenv("STRIPE_PRICE_ID", "price_example")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_testexample")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://genemeal.example")
    monkeypatch.setattr(B, "resolve_state", lambda ip, fetch=None: "CT")
    monkeypatch.setattr(stripe_billing, "build_client", lambda: fake)
    storage.set_stripe_billing(_uid(client), customer_id="cus_ct")

    checkout = post(client, "/stripe/checkout")
    assert checkout.status_code == 451
    assert fake.calls == []

    opened = post(client, "/stripe/portal")
    assert opened.status_code == 303
    assert opened.headers["Location"] == PORTAL_URL
    assert fake.calls[0][1] == "/v1/billing_portal/sessions"
    assert fake.calls[0][2]["customer"] == "cus_ct"


def test_portal_failure_does_not_charge_or_return_500(client, monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://genemeal.example")
    storage.set_stripe_billing(_uid(client), customer_id="cus_missing_key")

    response = post(client, "/stripe/portal")

    assert response.status_code == 303
    assert response.status_code != 500
    assert response.headers["Location"].endswith("/unsubscribe")
    page = client.get("/unsubscribe").get_data(as_text=True)
    assert stripe_billing.PORTAL_UNAVAILABLE_MESSAGE in page
    assert PAGE_TEXT in page


def test_portal_without_a_url_does_not_return_500(client, monkeypatch):
    fake = _FakeStripe(body={"id": "bps_empty"})
    monkeypatch.setattr(stripe_billing, "build_client", lambda: fake)
    storage.set_stripe_billing(_uid(client), customer_id="cus_nourl")

    response = post(client, "/stripe/portal")

    assert response.status_code == 303
    assert response.headers["Location"].endswith("/unsubscribe")
    assert fake.calls[0][1] == "/v1/billing_portal/sessions"
    page = client.get("/unsubscribe").get_data(as_text=True)
    assert stripe_billing.PORTAL_UNAVAILABLE_MESSAGE in page


def test_unsubscribe_page_has_paypal_autopay_button(client):
    page = client.get("/unsubscribe").get_data(as_text=True)
    assert (
        '<a class="button" href="https://www.paypal.com/myaccount/autopay/" '
        'target="_blank" rel="noopener noreferrer">Manage PayPal subscription</a>'
    ) in page
    assert page.index(">Manage card subscription</button>") < page.index(
        "Manage PayPal subscription"
    ) < page.index(">Back to the guide</a>")
