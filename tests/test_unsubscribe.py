import inspect
import re

import app as A
import blocked_states as B


def _danger_zone(html: str) -> str:
    return html.split('<section class="danger-zone">', 1)[1].split("</section>", 1)[0]


def test_home_delete_and_unsubscribe_sits_under_delete(client):
    html = client.get("/").get_data(as_text=True)
    zone = _danger_zone(html)
    form, after = zone.split("</form>", 1)
    assert 'action="/account/data"' in form
    assert 'name="confirm"' in form
    assert '>Delete my data</button>' in form
    assert "Delete and Unsubscribe" not in form
    link = re.search(
        r'<p><a class="button" href="(/unsubscribe)">Delete and Unsubscribe</a></p>\s*'
        r'<p class="fine">This allows you to unsubscribe as well.</p>',
        after,
    )
    assert link, after
    assert link.group(1) == "/unsubscribe"
    assert ">Unsubscribe</a>" not in html


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


def test_unsubscribe_page_explains_cancel_without_billing_calls(client, monkeypatch):
    def _boom(*_args, **_kwargs):
        raise AssertionError("billing client should not be built")

    monkeypatch.setattr("billing.build_client", _boom)
    monkeypatch.setattr("stripe_billing.build_client", _boom)
    source = inspect.getsource(A.unsubscribe)
    assert "billing." not in source
    assert "stripe" not in source

    response = client.get("/unsubscribe")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "PayPal subscriptions can be cancelled in the PayPal account's automatic payments settings." in page
    assert "GeneMeal does not have a card cancellation page." in page
    assert "/static/style.css" in page
    assert 'class="brand"' in page
    assert "<footer>" in page
    assert 'href="/"' in page
    assert "/billing/checkout" not in page
    assert "/stripe/checkout" not in page
    copy = page.split("<h1>", 1)[1].split("</section>", 1)[0]
    assert "mailto:" not in copy
    assert not re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", copy)
    assert not re.search(r"(?:\+?\d[\d\s().-]{7,}\d)", copy)


def test_unsubscribe_is_open_in_blocked_states(client, monkeypatch):
    assert not B.path_is_blocked_scope("/unsubscribe")
    monkeypatch.setenv("GEO_BLOCK_ENABLED", "1")
    monkeypatch.setattr(B, "resolve_state", lambda ip, fetch=None: "CA")
    response = client.get("/unsubscribe")
    assert response.status_code == 200
    assert "Not available in" not in response.get_data(as_text=True)
