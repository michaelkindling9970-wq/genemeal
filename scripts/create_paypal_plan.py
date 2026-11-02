"""Create the GeneMeal PayPal product and $13/month plan once.

Usage (sandbox by default):
    PAYPAL_CLIENT_ID=... PAYPAL_CLIENT_SECRET=... python scripts/create_paypal_plan.py
    PAYPAL_ENV=live ... python scripts/create_paypal_plan.py

Prints the plan id. Set it as PAYPAL_PLAN_ID on Render. The script makes no
changes to PayPal account settings.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import billing  # noqa: E402


def main() -> int:
    try:
        result = billing.create_product_and_plan(billing.build_client())
    except billing.CheckoutError as exc:
        print("error:", billing.safe_error(exc), file=sys.stderr)
        return 1
    print(f"env={result['env']} product_id={result['product_id']}")
    print(f"PAYPAL_PLAN_ID={result['plan_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
