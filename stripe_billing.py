"""Stripe Checkout for the Credit or Debit Card button.

Runs alongside PayPal (billing.py); neither replaces the other. Keys come from
the environment only. Nothing in this file is a live credential. The button
label is "Credit or Debit Card". It submits only when BILLING_ENABLED=1 and
STRIPE_SECRET_KEY, STRIPE_PUBLISHABLE_KEY, STRIPE_WEBHOOK_SECRET, and
STRIPE_PRICE_ID are all set. If any of those are missing, the button does not
start checkout and the page says card checkout is coming soon.

Flow:
  1. POST /stripe/checkout creates a Checkout Session (mode=subscription) for
     STRIPE_PRICE_ID ($13/month, same as the PayPal plan) and redirects.
  2. Stripe calls POST /stripe/webhook. The Stripe-Signature header is verified
     (HMAC-SHA256 over "t.payload", 5 minute tolerance) before anything is saved.
  3. Status lands in the same users.subscription_status column PayPal uses.
     Stripe ids go in their own columns, so PayPal records stay untouched.

Uses the REST API directly (urllib), so no extra dependency is needed.

Cancellation for an existing card subscription goes through Stripe's hosted
customer portal (POST /stripe/portal). That call creates a Billing Portal
session only. It does not charge the customer and it does not cancel a
subscription. With no stored customer id, the visitor is sent to Stripe's
no-code portal login link.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

import storage

API_BASE = "https://api.stripe.com"
SIGNATURE_TOLERANCE = 300

CARD_BUTTON_LABEL = "Credit or Debit Card"
COMING_SOON_MESSAGE = "Card checkout coming soon."
KEYS_MISSING_MESSAGE = COMING_SOON_MESSAGE
BILLING_OFF_MESSAGE = "Set BILLING_ENABLED=1 to enable checkout"
# Stripe's no-code customer portal login. STRIPE_PORTAL_LOGIN_URL overrides it.
DEFAULT_PORTAL_LOGIN_URL = "https://billing.stripe.com/p/login/6oU8wJ15b3vfc6c9Xpe3e00"
PORTAL_UNAVAILABLE_MESSAGE = "The card subscription page could not be opened."

_SECRET_RE = re.compile(r"(?:sk|rk|pk)_(?:test|live)_[A-Za-z0-9]+|whsec_[A-Za-z0-9]+")


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
    return os.environ.get("BILLING_ENABLED", "1") == "1"


def keys_present() -> bool:
    return bool(secret_key() and publishable_key() and webhook_secret() and price_id())


def checkout_ready() -> bool:
    return billing_enabled() and keys_present()


def checkout_view() -> dict:
    if not keys_present():
        message = KEYS_MISSING_MESSAGE
    elif not billing_enabled():
        message = BILLING_OFF_MESSAGE
    else:
        message = ""
    return {"stripe_ready": checkout_ready(), "stripe_message": message}


def safe_error(exc: BaseException) -> str:
    text = str(exc)
    for value in (secret_key(), publishable_key(), webhook_secret()):
        if value:
            text = text.replace(value, "[redacted]")
    return _SECRET_RE.sub("[redacted]", text)[:400]


def _flatten(params: dict, prefix: str = "") -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for key, value in params.items():
        name = f"{prefix}[{key}]" if prefix else str(key)
        if isinstance(value, dict):
            out.extend(_flatten(value, name))
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    out.extend(_flatten(item, f"{name}[{i}]"))
                else:
                    out.append((f"{name}[{i}]", str(item)))
        elif value is not None:
            out.append((name, str(value)))
    return out


class StripeClient:
    def __init__(self, key: str, base: str = API_BASE):
        self._key = key
        self.base = base

    def request(self, method: str, path: str, params: dict | None = None, *, idempotency_key: str | None = None) -> dict:
        body = urllib.parse.urlencode(_flatten(params or {})).encode() if params is not None else None
        headers = {
            "Authorization": "Bearer " + self._key,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        req = urllib.request.Request(self.base + path, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read()[:300].decode("utf-8", "ignore")
            raise CheckoutError(f"Stripe HTTP {exc.code}: {detail}") from None
        except urllib.error.URLError as exc:
            raise CheckoutError(f"Stripe unreachable: {exc.reason}") from None
        return json.loads(raw or b"{}")


def build_client() -> StripeClient:
    """Live Stripe client. Tests set GENEMEAL_FORBID_NETWORK and inject a double."""
    if os.environ.get("GENEMEAL_FORBID_NETWORK") == "1":
        raise CheckoutError("live Stripe calls are disabled")
    if not secret_key():
        raise CheckoutError("STRIPE_SECRET_KEY is not set")
    return StripeClient(secret_key())


def session_params(user: dict, base_url: str) -> dict:
    base = base_url.rstrip("/")
    params: dict[str, Any] = {
        "mode": "subscription",
        "client_reference_id": user["id"],
        "line_items": [{"price": price_id(), "quantity": 1}],
        "success_url": base + "/billing/success?gateway=stripe&session_id={CHECKOUT_SESSION_ID}",
        "cancel_url": base + "/billing/cancel",
        "metadata": {"genemeal_user_id": user["id"]},
        "subscription_data": {"metadata": {"genemeal_user_id": user["id"]}},
    }
    customer = user.get("stripe_customer_id")
    if customer:
        params["customer"] = customer
    else:
        email = (user.get("email") or "").strip()
        if email:
            params["customer_email"] = email
    return params


def portal_login_url() -> str:
    """Hosted portal login. An explicit STRIPE_PORTAL_LOGIN_URL wins."""
    return _clean("STRIPE_PORTAL_LOGIN_URL") or DEFAULT_PORTAL_LOGIN_URL


def start_portal(customer_id: str, base_url: str) -> str:
    """Create a Billing Portal session and return its hosted URL.

    The body is only the customer and the return URL. Stripe applies the
    Dashboard's default portal configuration, so this does not send a
    configuration id, does not charge, and does not cancel.
    """
    client = build_client()
    session = client.request(
        "POST",
        "/v1/billing_portal/sessions",
        {
            "customer": customer_id,
            "return_url": base_url.rstrip("/") + "/unsubscribe",
        },
    )
    url = session.get("url") or ""
    if not url:
        raise CheckoutError("Stripe did not return a portal URL")
    return url


def start_checkout(user: dict, base_url: str) -> str:
    if not keys_present():
        raise CheckoutError(KEYS_MISSING_MESSAGE)
    if not billing_enabled():
        raise CheckoutError(BILLING_OFF_MESSAGE)
    client = build_client()
    session = client.request("POST", "/v1/checkout/sessions", session_params(user, base_url))
    url = session.get("url") or ""
    if not url:
        raise CheckoutError("Stripe did not return a Checkout URL")
    return url


# --------------------------------------------------------------------------
# Webhook
# --------------------------------------------------------------------------


def verify_signature(payload: bytes, header: str, secret: str, *, now: float | None = None) -> dict:
    if not secret:
        raise SignatureError("no webhook secret")
    timestamp = ""
    signatures: list[str] = []
    for part in (header or "").split(","):
        key, _, value = part.strip().partition("=")
        if key == "t":
            timestamp = value
        elif key == "v1":
            signatures.append(value)
    if not timestamp.isdigit() or not signatures:
        raise SignatureError("malformed Stripe-Signature header")
    current = time.time() if now is None else now
    if abs(current - int(timestamp)) > SIGNATURE_TOLERANCE:
        raise SignatureError("timestamp outside tolerance")
    signed = timestamp.encode() + b"." + payload
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, sig) for sig in signatures):
        raise SignatureError("signature mismatch")
    try:
        event = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise SignatureError("payload is not JSON") from None
    if not isinstance(event, dict):
        raise SignatureError("payload is not an object")
    return event


def sign_payload(payload: bytes, secret: str, timestamp: int | None = None) -> str:
    """Build a Stripe-Signature header. Used by tests."""
    ts = int(time.time()) if timestamp is None else timestamp
    sig = hmac.new(secret.encode(), str(ts).encode() + b"." + payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


def apply_event(event: dict) -> None:
    event_id = _str(event.get("id"))
    event_type = _str(event.get("type"))
    claimed = False
    if event_id:
        claimed = storage.claim_stripe_event(event_id, event_type or "unknown")
        if not claimed:
            return
    try:
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        obj = data.get("object") if isinstance(data.get("object"), dict) else {}
        if _dispatch(event_type, obj) is False:
            raise UserNotFound(event_type or "stripe event")
    except Exception:
        if claimed:
            storage.forget_stripe_event(event_id)
        raise


def _dispatch(event_type: str, obj: dict) -> bool | None:
    if event_type in {"checkout.session.completed", "checkout.session.async_payment_succeeded"}:
        return _on_checkout(obj, paid=obj.get("payment_status") != "unpaid")
    if event_type == "checkout.session.async_payment_failed":
        return _on_checkout(obj, paid=False)
    if event_type.startswith("customer.subscription."):
        return _on_subscription(obj, deleted=event_type.endswith(".deleted"))
    if event_type == "invoice.paid":
        return _on_invoice(obj, status="active")
    if event_type == "invoice.payment_failed":
        return _on_invoice(obj, status="past_due")
    if event_type == "charge.refunded" and obj.get("refunded") is True:
        return _on_charge(obj, status="refunded")
    if event_type == "charge.dispute.created":
        return _on_charge(obj, status="disputed")
    return None


def _on_checkout(obj: dict, *, paid: bool) -> bool:
    customer = _id(obj.get("customer"))
    sub_id = _id(obj.get("subscription"))
    user = _find_user(customer, sub_id, obj)
    if user is None:
        return False
    status = "active" if paid else None
    if not paid and user.get("subscription_status") not in {"active", "trialing"}:
        status = "incomplete"
    storage.set_stripe_billing(user["id"], customer_id=customer, subscription_id=sub_id, status=status)
    return True


def _on_subscription(obj: dict, *, deleted: bool) -> bool:
    customer = _id(obj.get("customer"))
    sub_id = _id(obj.get("id"))
    user = _find_user(customer, sub_id, obj)
    if user is None:
        return False
    status = "canceled" if deleted else (_str(obj.get("status")) or "incomplete")
    storage.set_stripe_billing(user["id"], customer_id=customer, subscription_id=sub_id, status=status)
    return True


def _on_invoice(obj: dict, *, status: str) -> bool:
    customer = _id(obj.get("customer"))
    sub_id = _invoice_subscription(obj)
    user = _find_user(customer, sub_id, {})
    if user is None:
        return True if not (customer or sub_id) else False
    storage.set_stripe_billing(user["id"], customer_id=customer, subscription_id=sub_id, status=status)
    return True


def _on_charge(obj: dict, *, status: str) -> bool:
    customer = _id(obj.get("customer"))
    if not customer:
        return True  # dispute objects carry no customer; nothing safe to update
    user = storage.find_user_by_stripe_customer(customer)
    if user is None:
        return True
    storage.set_stripe_billing(user["id"], status=status)
    return True


def _find_user(customer: str | None, sub_id: str | None, obj: dict) -> dict | None:
    if customer:
        user = storage.find_user_by_stripe_customer(customer)
        if user is not None:
            return user
    if sub_id:
        user = storage.find_user_by_stripe_subscription(sub_id)
        if user is not None:
            return user
    ref = _str(obj.get("client_reference_id"))
    if not ref:
        meta = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
        ref = _str(meta.get("genemeal_user_id"))
    return storage.get_user(ref) if ref else None


def _invoice_subscription(obj: dict) -> str | None:
    parent = obj.get("parent")
    if isinstance(parent, dict) and isinstance(parent.get("subscription_details"), dict):
        found = _id(parent["subscription_details"].get("subscription"))
        if found:
            return found
    return _id(obj.get("subscription"))


def _id(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, dict) and isinstance(value.get("id"), str) and value["id"]:
        return value["id"]
    return None


def _str(value: Any) -> str:
    return value if isinstance(value, str) else ""
