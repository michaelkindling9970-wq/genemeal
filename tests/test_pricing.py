from decimal import Decimal

import billing
import pricing


def test_fees_sum_to_thirteen():
    assert pricing.BASE_FEE == Decimal("10.00")
    assert pricing.SERVER_USAGE_FEE == Decimal("2.00")
    assert pricing.GENOME_PROCESSING_FEE == Decimal("1.00")
    assert pricing.monthly_total() == Decimal("13.00")
    assert (
        pricing.BASE_FEE + pricing.SERVER_USAGE_FEE + pricing.GENOME_PROCESSING_FEE
        == Decimal("13.00")
    )


def test_home_and_pricing_page_show_fee_labels(client):
    for path in ("/", "/pricing"):
        response = client.get(path)
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "Base fee" in body
        assert "Server usage fee" in body
        assert "Genome analysis / processing fee" in body
        assert "Monthly total" in body
        assert "$10.00" in body
        assert "$2.00" in body
        assert "$1.00" in body
        assert "$13.00" in body
        assert billing.KEYS_MISSING_MESSAGE in body
        assert "disabled" in body
        assert ">PayPal</button>" in body


def test_billing_flag_off_keeps_fees(client, monkeypatch):
    monkeypatch.setenv("BILLING_ENABLED", "0")
    body = client.get("/").get_data(as_text=True)
    assert "Base fee" in body
    assert "$13.00" in body
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
