"""Stripe Checkout for the GeneMeal monthly subscription.

Keys come from the environment only. Nothing in this file is a live credential.
Checkout stays off until BILLING_ENABLED=1 and the Stripe vars are all set.
Missing keys return a disabled control; they do not raise on page render.
"""
from __future__ import annotations

import os
import re
from typing import Any

import storage

API_VERSION = "2026-09-30.endive"
# Stable label for the Checkout dashboard. Suffix is 8 letters.
INTEGRATION_IDENTIFIER = "genemeal_monthly_kwmnpqrx"

KEYS_MISSING_MESSAGE = "Add Stripe keys to enable checkout"
BILLING_OFF_MESSAGE = "Set BILLING_ENABLED=1 to enable checkout"

_SECRET_RE = re.compile(
    r"(?:sk|rk|pk)_(?:test|live)_[A-Za-z0-9]+|whsec_[A-Za-z0-9]+"
)

try:
    import stripe
    from stripe import SignatureVerificationError, StripeClient
except ImportError:  # pragma: no cover - dependency is in requirements.txt
    stripe = None  # type: ignore[assignment]
    SignatureVerificationError = Exception  # type: ignore[misc, assignment]
    StripeClient = None  # type: ignore[assignment]


class CheckoutError(Exception):
    pass


class SignatureError(Exception):
    pass


class UserNotFound(Exception):
    pass


def _clean(name: str) -> str:
    return os.environ.get(name, "").strip()


def secret_key() -> str:
    return _clean("STRIPE_SECRET_KEY")


def publishable_key() -> str:
    return _clean("STRIPE_PUBLISHABLE_KEY")


def price_id() -> str:
    return _clean("STRIPE_PRICE_ID")


def webhook_secret() -> str:
    return _clean("STRIPE_WEBHOOK_SECRET")


def billing_enabled() -> bool:
    """Default on. Checkout still requires the Stripe env vars."""
    return os.environ.get("BILLING_ENABLED", "1") == "1"


def keys_present() -> bool:
    return bool(secret_key() and publishable_key() and price_id() and webhook_secret())


def checkout_ready() -> bool:
    return billing_enabled() and keys_present() and StripeClient is not None


def checkout_view(subscription_status: str | None = None) -> dict:
    ready = checkout_ready()
    missing = not keys_present()
    if missing or StripeClient is None:
        message = KEYS_MISSING_MESSAGE
    elif not billing_enabled():
        message = BILLING_OFF_MESSAGE
    else:
        message = ""
    return {
        "billing_enabled": billing_enabled(),
        "checkout_ready": ready,
        "keys_missing": missing,
        "checkout_message": message,
        "subscription_status": subscription_status or "",
    }


def safe_error(exc: BaseException) -> str:
    text = _SECRET_RE.sub("[redacted]", str(exc))
    return text[:400]


def build_client():
    """Live Stripe client. Tests set GENEMEAL_FORBID_NETWORK and inject a double."""
    if os.environ.get("GENEMEAL_FORBID_NETWORK") == "1":
        raise CheckoutError("live Stripe calls are disabled")
    if StripeClient is None:
        raise CheckoutError("Stripe SDK is not installed")
    key = secret_key()
    if not key:
        raise CheckoutError("STRIPE_SECRET_KEY is not set")
    return StripeClient(key, stripe_version=API_VERSION)


def _signature_client():
    if StripeClient is None:
        raise CheckoutError("Stripe SDK is not installed")
    key = secret_key() or "rk_test_signature_only"
    return StripeClient(key, stripe_version=API_VERSION)


def start_checkout(user: dict, base_url: str) -> str:
    if not keys_present():
        raise CheckoutError(KEYS_MISSING_MESSAGE)
    if not billing_enabled():
        raise CheckoutError(BILLING_OFF_MESSAGE)
    client = build_client()
    customer_id = user.get("stripe_customer_id") or _create_customer(client, user)
    base = base_url.rstrip("/")
    params = {
        "mode": "subscription",
        "customer": customer_id,
        "client_reference_id": user["id"],
        "line_items": [{"price": price_id(), "quantity": 1}],
        "success_url": base + "/billing/success?session_id={CHECKOUT_SESSION_ID}",
        "cancel_url": base + "/billing/cancel",
        "integration_identifier": INTEGRATION_IDENTIFIER,
    }
    session = client.checkout.sessions.create(params=params)
    url = getattr(session, "url", None) or ""
    if not url:
        raise CheckoutError("Stripe did not return a Checkout URL")
    return url


def _create_customer(client: Any, user: dict) -> str:
    params: dict[str, Any] = {"metadata": {"genemeal_user_id": user["id"]}}
    email = (user.get("email") or "").strip()
    if email:
        params["email"] = email
    customer = client.customers.create(params=params)
    customer_id = getattr(customer, "id", None)
    if not customer_id:
        raise CheckoutError("Stripe did not return a customer id")
    storage.set_billing(user["id"], customer_id=customer_id)
    user["stripe_customer_id"] = customer_id
    return customer_id


def construct_webhook_event(payload: bytes, signature: str, secret: str):
    if stripe is None:
        raise CheckoutError("Stripe SDK is not installed")
    try:
        return _signature_client().construct_event(payload, signature, secret)
    except SignatureVerificationError as exc:
        raise SignatureError(safe_error(exc)) from exc


def apply_event(event: Any, client: Any = None) -> None:
    data = _event_dict(event)
    event_id = data.get("id") if isinstance(data.get("id"), str) else ""
    event_type = data.get("type") if isinstance(data.get("type"), str) else ""
    claimed = False
    if event_id:
        claimed = storage.claim_stripe_event(event_id, event_type or "unknown")
        if not claimed:
            return
    try:
        obj = ((data.get("data") or {}) if isinstance(data.get("data"), dict) else {}).get("object") or {}
        if not isinstance(obj, dict):
            obj = _as_dict(obj)
        result = _dispatch(event_type, obj, client)
        if result is False:
            raise UserNotFound(event_type or "stripe event")
    except Exception:
        if claimed and event_id:
            storage.forget_stripe_event(event_id)
        raise


def _dispatch(event_type: str, obj: dict, client: Any) -> bool | None:
    if event_type in {"checkout.session.completed", "checkout.session.async_payment_succeeded"}:
        return _on_checkout_paid(obj)
    if event_type == "checkout.session.async_payment_failed":
        return _on_checkout_failed(obj)
    if event_type in {
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "customer.subscription.paused",
        "customer.subscription.resumed",
    }:
        return _on_subscription(obj)
    if event_type == "invoice.paid":
        return _on_invoice(obj, paid=True)
    if event_type == "invoice.payment_failed":
        return _on_invoice(obj, paid=False)
    if event_type == "charge.dispute.created":
        return _on_risk(obj, client, status="disputed")
    if event_type == "charge.refunded":
        if obj.get("refunded") is not True:
            return True
        return _on_risk(obj, client, status="refunded")
    if event_type == "radar.early_fraud_warning.created":
        return _on_risk(obj, client, status="fraud_warning")
    return None


def _on_checkout_paid(obj: dict) -> bool:
    user = _user_from_checkout(obj)
    if user is None:
        return False
    unpaid = obj.get("payment_status") == "unpaid"
    status = None
    if unpaid:
        if user.get("subscription_status") not in {"active", "trialing"}:
            status = "incomplete"
    else:
        status = "active"
    _save_link(user, obj, status=status)
    return True


def _on_checkout_failed(obj: dict) -> bool:
    user = _user_from_checkout(obj)
    if user is None:
        return False
    status = "incomplete"
    if user.get("subscription_status") in {"active", "trialing"}:
        status = None
    _save_link(user, obj, status=status)
    return True


def _save_link(user: dict, obj: dict, *, status: str | None) -> None:
    customer = _stripe_id(obj.get("customer")) or user.get("stripe_customer_id")
    subscription = _stripe_id(obj.get("subscription")) or user.get("stripe_subscription_id")
    storage.set_billing(
        user["id"],
        customer_id=customer,
        subscription_id=subscription,
        status=status,
    )


def _on_subscription(obj: dict) -> bool:
    customer = _stripe_id(obj.get("customer"))
    sub_id = _stripe_id(obj.get("id"))
    user = _user_by_customer_or_subscription(customer, sub_id)
    if user is None:
        return True if customer else False
    status = obj.get("status") if isinstance(obj.get("status"), str) else "canceled"
    storage.set_billing(
        user["id"],
        customer_id=customer or user.get("stripe_customer_id"),
        subscription_id=sub_id or user.get("stripe_subscription_id"),
        status=status,
    )
    return True


def _on_invoice(obj: dict, *, paid: bool) -> bool:
    customer = _stripe_id(obj.get("customer"))
    sub_id = _invoice_subscription_id(obj)
    user = _user_by_customer_or_subscription(customer, sub_id)
    if user is None:
        return True if customer else False
    if not sub_id and not user.get("stripe_subscription_id"):
        return True
    storage.set_billing(
        user["id"],
        customer_id=customer or user.get("stripe_customer_id"),
        subscription_id=sub_id or user.get("stripe_subscription_id"),
        status="active" if paid else "past_due",
    )
    return True


def _on_risk(obj: dict, client: Any, *, status: str) -> bool:
    customer = _stripe_id(obj.get("customer"))
    if not customer:
        customer = _customer_from_charge(obj.get("charge"), client)
    if not customer:
        customer = _customer_from_charge(obj.get("payment_intent"), client)
    if not customer:
        return False
    user = storage.find_user_by_stripe_customer(customer)
    if user is None:
        return True
    storage.set_billing(user["id"], status=status)
    return True


def _user_from_checkout(obj: dict) -> dict | None:
    customer = _stripe_id(obj.get("customer"))
    sub_id = _stripe_id(obj.get("subscription"))
    user = _user_by_customer_or_subscription(customer, sub_id)
    if user is not None:
        return user
    ref = obj.get("client_reference_id")
    if isinstance(ref, str) and ref:
        return storage.get_user(ref)
    return None


def _user_by_customer_or_subscription(customer: str | None, sub_id: str | None) -> dict | None:
    if customer:
        user = storage.find_user_by_stripe_customer(customer)
        if user is not None:
            return user
    if sub_id:
        return storage.find_user_by_stripe_subscription(sub_id)
    return None


def _invoice_subscription_id(obj: dict) -> str | None:
    parent = obj.get("parent")
    if isinstance(parent, dict):
        details = parent.get("subscription_details")
        if isinstance(details, dict):
            found = _stripe_id(details.get("subscription"))
            if found:
                return found
    return _stripe_id(obj.get("subscription"))


def _customer_from_charge(ref: Any, client: Any) -> str | None:
    if isinstance(ref, dict):
        found = _stripe_id(ref.get("customer"))
        if found:
            return found
        ref = ref.get("id")
    if not isinstance(ref, str) or not ref or client is None:
        return None
    if ref.startswith("ch_"):
        try:
            charge = client.charges.retrieve(ref)
        except Exception:
            return None
        return _stripe_id(getattr(charge, "customer", None))
    if ref.startswith("pi_") and hasattr(client, "payment_intents"):
        try:
            intent = client.payment_intents.retrieve(ref)
        except Exception:
            return None
        return _stripe_id(getattr(intent, "customer", None))
    return None


def _stripe_id(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, dict):
        inner = value.get("id")
        if isinstance(inner, str) and inner:
            return inner
    inner = getattr(value, "id", None)
    if isinstance(inner, str) and inner:
        return inner
    return None


def _event_dict(event: Any) -> dict:
    if isinstance(event, dict):
        return event
    data_obj = getattr(getattr(event, "data", None), "object", None)
    return {
        "id": getattr(event, "id", None),
        "type": getattr(event, "type", None),
        "data": {"object": _plain(data_obj) if data_obj is not None else {}},
    }


def _plain(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    as_dict = _as_dict(value)
    if as_dict:
        return {str(key): _plain(item) for key, item in as_dict.items()}
    return _stripe_id(value)


def _as_dict(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if value is None:
        return {}
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            converted = to_dict()
        except Exception:
            converted = None
        if isinstance(converted, dict):
            return converted
    return {}
