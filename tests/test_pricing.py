from decimal import Decimal
from pathlib import Path

import billing
import pricing
import stripe_billing

def _myplate_billing_sentence() -> str:
    # Split so this file does not contain the retired billing sentence.
    return "Includes the " + "MyPlate diet plan builder."


def test_fees_sum_to_monthly_price():
    assert pricing.BASE_FEE == Decimal("17.00")
    assert pricing.SERVER_USAGE_FEE == Decimal("2.00")
    assert pricing.GENOME_PROCESSING_FEE == Decimal("0.97")
    assert pricing.monthly_total() == Decimal("19.97")
    assert (
        pricing.BASE_FEE + pricing.SERVER_USAGE_FEE + pricing.GENOME_PROCESSING_FEE
        == Decimal("19.97")
    )


def test_home_and_pricing_page_show_one_price_not_fee_lines(client):
    for path in ("/", "/pricing"):
        response = client.get(path)
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "Base fee" not in body
        assert "Server usage fee" not in body
        assert "processing fee" not in body
        assert "$17.00" not in body
        assert "$2.00" not in body
        assert "$0.97" not in body
        assert "price-lines" not in body
        assert '<p class="price-heading" id="pricing-heading">$19.97/month</p>' in body
        assert billing.KEYS_MISSING_MESSAGE in body
        assert stripe_billing.COMING_SOON_MESSAGE in body
        assert "disabled" in body
        assert _myplate_billing_sentence() not in body
        assert 'action="/stripe/checkout"' not in body
        card_at = body.index('id="pay-card"')
        paypal_at = body.index('id="pay-paypal"')
        assert card_at < paypal_at
        assert ">Credit or Debit Card</button>" in body[card_at:paypal_at]
        assert ">PayPal</button>" in body[paypal_at:]
        card = body[body.rindex("<button", 0, card_at):body.index("</button>", card_at)]
        assert card.endswith(">Credit or Debit Card")
        assert "Stripe" not in card
        assert 'type="button"' in card
        assert "disabled" in card


def test_billing_flag_off_keeps_price(client, monkeypatch):
    monkeypatch.setenv("BILLING_ENABLED", "0")
    body = client.get("/").get_data(as_text=True)
    assert "Base fee" not in body
    assert "$19.97/month" in body
    assert billing.KEYS_MISSING_MESSAGE in body
    assert client.get("/pricing").status_code == 200


def test_home_pricing_sits_with_upload_and_does_not_call_paypal(client):
    body = client.get("/").get_data(as_text=True)
    price_at = body.index('id="pricing"')
    upload_at = body.index('id="upload-form"')
    form_at = body.rindex("<form", 0, upload_at)
    assert price_at < form_at
    assert "<form" not in body[price_at:form_at]
    assert "Upload and read" in body
    assert 'action="/upload"' in body
    assert "paypal.com" not in body
    assert 'type="button"' in body
    assert "PAYPAL_" not in body
    assert "STRIPE_" not in body
    assert "checkout.stripe.com" not in body


def test_myplate_billing_sentence_is_absent_from_the_repo():
    root = Path(__file__).resolve().parents[1]
    skip = {".git", ".venv", "venv", "__pycache__", ".pytest_cache"}
    needle = _myplate_billing_sentence().lower()
    found = []
    for path in root.rglob("*"):
        if not path.is_file() or any(part in skip for part in path.parts):
            continue
        if path.suffix.lower() not in {".py", ".html", ".md", ".css", ".js", ".txt", ".jinja", ".jinja2"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        if needle in text:
            found.append(str(path.relative_to(root)))
    assert found == []


def test_pay_buttons_sit_side_by_side_on_wide_and_stack_on_narrow():
    root = Path(__file__).resolve().parents[1]
    css = (root / "static" / "style.css").read_text()
    template = (root / "templates" / "_pricing.html").read_text()
    assert ".pay-buttons { display: grid; grid-template-columns: 1fr 1fr;" in css
    assert "@media (max-width: 480px) { .pay-buttons { grid-template-columns: 1fr; } }" in css
    assert "pay-single" not in template
    assert template.index('id="pay-card"') < template.index('id="pay-paypal"')


def test_pages_show_1997_per_month_only(client):
    for path in ("/", "/pricing"):
        body = client.get(path).get_data(as_text=True)
        assert "$19.97/month" in body
        assert "$12.97" not in body
        assert "prepaid" not in body.lower()


DISCLAIMER = (
    "GeneMeal is $19.97 per month and automatically renews each month at $19.97 until you cancel. "
    "You can cancel anytime online through your billing portal (Stripe or PayPal); cancellation stops "
    "future renewals and takes effect at the end of your current billing period, so you keep access "
    "until then. We do not refund a paid month or unused days after you cancel, unless the law requires it. "
    "Deleting your account data does not cancel billing \u2014 you must also cancel your subscription to stop charges."
)


def test_disclaimer_text_under_price_on_home_and_pricing(client):
    from markupsafe import escape
    assert pricing.SUBSCRIPTION_DISCLAIMER == DISCLAIMER
    for path in ("/", "/pricing"):
        body = client.get(path).get_data(as_text=True)
        slot = body.index('id="subscription-disclaimer"')
        assert body.index('id="pricing-heading"') < slot < body.index('id="pay-card"')
        assert str(escape(DISCLAIMER)) in body


def test_disclaimer_slot_renders_only_when_set(client, monkeypatch):
    monkeypatch.setattr(pricing, "SUBSCRIPTION_DISCLAIMER", "")
    assert 'id="subscription-disclaimer"' not in client.get("/pricing").get_data(as_text=True)
    monkeypatch.setattr(pricing, "SUBSCRIPTION_DISCLAIMER", "Example small print.")
    body = client.get("/pricing").get_data(as_text=True)
    slot = body.index('id="subscription-disclaimer"')
    assert body.index('id="pricing-heading"') < slot < body.index('id="pay-card"')
    assert "Example small print." in body
