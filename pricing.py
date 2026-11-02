"""Monthly GeneMeal price.

Amounts live here so checkout can stay in sync with the page. This module does
not call PayPal and does not read API keys. `billing.py` reads the PayPal env
vars and starts a subscription when they are set.
"""
from __future__ import annotations

from decimal import Decimal

BASE_FEE = Decimal("10.00")
SERVER_USAGE_FEE = Decimal("2.00")
GENOME_PROCESSING_FEE = Decimal("1.00")

LINE_ITEMS = (
    {"code": "base", "label": "Base fee", "amount": BASE_FEE},
    {"code": "server", "label": "Server usage fee", "amount": SERVER_USAGE_FEE},
    {
        "code": "genome",
        "label": "Genome analysis / processing fee",
        "amount": GENOME_PROCESSING_FEE,
    },
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
    }
