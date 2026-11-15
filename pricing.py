"""Monthly GeneMeal price.

Amounts live here so checkout can stay in sync with the page. This module does
not call PayPal and does not read API keys. `billing.py` reads the PayPal env
vars and starts a subscription when they are set.
"""
from __future__ import annotations

from decimal import Decimal

BASE_FEE = Decimal("17.00")
SERVER_USAGE_FEE = Decimal("2.00")
GENOME_PROCESSING_FEE = Decimal("0.97")

LINE_ITEMS = (
    {"code": "base", "label": "Base fee", "amount": BASE_FEE},
    {"code": "server", "label": "Server usage fee", "amount": SERVER_USAGE_FEE},
    {
        "code": "genome",
        "label": "Genome analysis / processing fee",
        "amount": GENOME_PROCESSING_FEE,
    },
)


# Gray small-print subscription disclaimer shown just under the price.
# Approved text; do not reword. When this is empty, nothing is rendered.
SUBSCRIPTION_DISCLAIMER = (
    "GeneMeal is $19.97 per month and automatically renews each month at $19.97 "
    "until you cancel. You can cancel anytime online through your billing portal "
    "(Stripe or PayPal); cancellation stops future renewals and takes effect at the "
    "end of your current billing period, so you keep access until then. We do not "
    "refund a paid month or unused days after you cancel, unless the law requires it. "
    "Deleting your account data does not cancel billing \u2014 you must also cancel "
    "your subscription to stop charges."
)


def monthly_total() -> Decimal:
    return sum((item["amount"] for item in LINE_ITEMS), Decimal("0.00"))


def money(amount: Decimal) -> str:
    return f"${amount:.2f}"


def view() -> dict:
    return {
        "lines": [
            {"label": item["label"], "amount": money(item["amount"])}
            for item in LINE_ITEMS
        ],
        "total": money(monthly_total()),
        "disclaimer": SUBSCRIPTION_DISCLAIMER,
    }
