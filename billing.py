"""PayPal Subscriptions for the GeneMeal $13/month plan.

Credentials come from the environment only. Nothing in this file is a live
credential. Checkout stays off until BILLING_ENABLED=1 (default) and the PayPal
vars are all set. Missing vars return a disabled control; they never raise on
page render.

Flow:
  1. scripts/create_paypal_plan.py creates the product + $13/month plan once
     and prints the plan id for PAYPAL_PLAN_ID.
  2. POST /billing/checkout creates a subscription and redirects the buyer to
     PayPal's approval page.
  3. PayPal calls POST /paypal/webhook. The signature is verified with
     PayPal's verify-webhook-signature API before any status is recorded.
"""
from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Callable

import pricing
import storage

# Statement name GeneMeal asks for. It must name this business: never another
# company's brand. PayPal Subscriptions do not accept a per-request descriptor;
# recurring charges use the account's "credit card statement name" setting.
SOFT_DESCRIPTOR = "GENEMEAL"
BRAND_NAME = "GeneMeal"

API_BASES = {
    "sandbox": "https://api-m.sandbox.paypal.com",
    "live": "https://api-m.paypal.com",
}

KEYS_MISSING_MESSAGE = "Add PayPal credentials to enable checkout"
BILLING_OFF_MESSAGE = "Set BILLING_ENABLED=1 to enable checkout"

HANDLED_EVENTS = {
    "BILLING.SUBSCRIPTION.CREATED",
    "BILLING.SUBSCRIPTION.ACTIVATED",
    "BILLING.SUBSCRIPTION.UPDATED",
    "BILLING.SUBSCRIPTION.RE-ACTIVATED",
    "BILLING.SUBSCRIPTION.CANCELLED",
    "BILLING.SUBSCRIPTION.SUSPENDED",
    "BILLING.SUBSCRIPTION.EXPIRED",
    "BILLING.SUBSCRIPTION.PAYMENT.FAILED",
    "PAYMENT.SALE.COMPLETED",
    "PAYMENT.SALE.REFUNDED",
    "PAYMENT.SALE.REVERSED",
}

_STATUS_FOR_EVENT = {
    "BILLING.SUBSCRIPTION.ACTIVATED": "active",
    "BILLING.SUBSCRIPTION.RE-ACTIVATED": "active",
    "BILLING.SUBSCRIPTION.CANCELLED": "canceled",
    "BILLING.SUBSCRIPTION.SUSPENDED": "suspended",
    "BILLING.SUBSCRIPTION.EXPIRED": "expired",
    "BILLING.SUBSCRIPTION.PAYMENT.FAILED": "past_due",
    "PAYMENT.SALE.COMPLETED": "active",
    "PAYMENT.SALE.REFUNDED": "refunded",
    "PAYMENT.SALE.REVERSED": "disputed",
}

_PAYPAL_STATUS = {
    "APPROVAL_PENDING": "incomplete",
    "APPROVED": "incomplete",
    "ACTIVE": "active",
    "SUSPENDED": "suspended",
    "CANCELLED": "canceled",
    "EXPIRED": "expired",
}

_SIG_HEADERS = {
    "auth_algo": "PAYPAL-AUTH-ALGO",
    "cert_url": "PAYPAL-CERT-URL",
    "transmission_id": "PAYPAL-TRANSMISSION-ID",
    "transmission_sig": "PAYPAL-TRANSMISSION-SIG",
    "transmission_time": "PAYPAL-TRANSMISSION-TIME",
}

_SECRET_RE = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]+|(basic\s+)[A-Za-z0-9+/=]+|access_token[\"':= ]+[A-Za-z0-9._\-]+")


class CheckoutError(Exception):
    pass


class SignatureError(Exception):
    pass


class UserNotFound(Exception):
    pass


def _clean(name: str) -> str:
    return os.environ.get(name, "").strip()


def client_id() -> str:
    return _clean("PAYPAL_CLIENT_ID")


def client_secret() -> str:
    return _clean("PAYPAL_CLIENT_SECRET")


def webhook_id() -> str:
    return _clean("PAYPAL_WEBHOOK_ID")


def plan_id() -> str:
    return _clean("PAYPAL_PLAN_ID")


def paypal_env() -> str:
    env = _clean("PAYPAL_ENV").lower() or "sandbox"
    return env if env in API_BASES else "sandbox"


def api_base() -> str:
    return API_BASES[paypal_env()]


def billing_enabled() -> bool:
    """Default on. Checkout still requires the PayPal env vars."""
    return os.environ.get("BILLING_ENABLED", "1") == "1"


def keys_present() -> bool:
    return bool(client_id() and client_secret() and webhook_id() and plan_id())


def checkout_ready() -> bool:
    return billing_enabled() and keys_present()


def checkout_view(subscription_status: str | None = None) -> dict:
    missing = not keys_present()
    if missing:
        message = KEYS_MISSING_MESSAGE
    elif not billing_enabled():
        message = BILLING_OFF_MESSAGE
    else:
        message = ""
    return {
        "billing_enabled": billing_enabled(),
        "checkout_ready": checkout_ready(),
        "keys_missing": missing,
        "checkout_message": message,
        "subscription_status": subscription_status or "",
    }


def safe_error(exc: BaseException) -> str:
    text = str(exc)
    for value in (client_secret(), client_id()):
        if value:
            text = text.replace(value, "[redacted]")
    return _SECRET_RE.sub("[redacted]", text)[:400]


# --------------------------------------------------------------------------
# HTTP. Tests replace `build_client` with a fake that has `.request(...)`.
# --------------------------------------------------------------------------


class PayPalClient:
    def __init__(self, cid: str, secret: str, base: str):
        self._cid = cid
        self._secret = secret
        self.base = base.rstrip("/")
        self._token: str | None = None

    def _http(self, method: str, url: str, headers: dict, body: bytes | None) -> dict:
        req = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read()[:300].decode("utf-8", "ignore")
            raise CheckoutError(f"PayPal HTTP {exc.code}: {detail}") from None
        except urllib.error.URLError as exc:
            raise CheckoutError(f"PayPal unreachable: {exc.reason}") from None
        return json.loads(raw or b"{}")

    def token(self) -> str:
        if self._token:
            return self._token
        basic = base64.b64encode(f"{self._cid}:{self._secret}".encode()).decode()
        data = self._http(
            "POST",
            self.base + "/v1/oauth2/token",
            {
                "Authorization": "Basic " + basic,
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            b"grant_type=client_credentials",
        )
        token = data.get("access_token")
        if not isinstance(token, str) or not token:
            raise CheckoutError("PayPal did not return an access token")
        self._token = token
        return token

    def request(self, method: str, path: str, body: dict | None = None, *, request_id: str | None = None) -> dict:
        headers = {
            "Authorization": "Bearer " + self.token(),
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Prefer": "return=representation",
        }
        if request_id:
            headers["PayPal-Request-Id"] = request_id
        payload = json.dumps(body).encode() if body is not None else None
        return self._http(method, self.base + path, headers, payload)


def build_client() -> PayPalClient:
    """Live PayPal client. Tests set GENEMEAL_FORBID_NETWORK and inject a double."""
    if os.environ.get("GENEMEAL_FORBID_NETWORK") == "1":
        raise CheckoutError("live PayPal calls are disabled")
    if not (client_id() and client_secret()):
        raise CheckoutError("PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET are not set")
    return PayPalClient(client_id(), client_secret(), api_base())


# --------------------------------------------------------------------------
# Product + plan (used by scripts/create_paypal_plan.py)
# --------------------------------------------------------------------------


def product_body() -> dict:
    return {
        "name": "GeneMeal monthly plan",
        "description": "Genotype-informed meal plans",
        "type": "SERVICE",
        "category": "SOFTWARE",
    }


def plan_body(product_id: str) -> dict:
    total = f"{pricing.monthly_total():.2f}"
    return {
        "product_id": product_id,
        "name": f"GeneMeal monthly ${total}",
        "description": "Base fee + server usage + genome processing",
        "status": "ACTIVE",
        "billing_cycles": [
            {
                "frequency": {"interval_unit": "MONTH", "interval_count": 1},
                "tenure_type": "REGULAR",
                "sequence": 1,
                "total_cycles": 0,
                "pricing_scheme": {"fixed_price": {"value": total, "currency_code": "USD"}},
            }
        ],
        "payment_preferences": {
            "auto_bill_outstanding": True,
            "setup_fee_failure_action": "CANCEL",
            "payment_failure_threshold": 3,
        },
    }


def create_product_and_plan(client: Any) -> dict:
    product = client.request("POST", "/v1/catalogs/products", product_body(), request_id="genemeal-product-v1")
    pid = product.get("id")
    if not pid:
        raise CheckoutError("PayPal did not return a product id")
    plan = client.request("POST", "/v1/billing/plans", plan_body(pid), request_id="genemeal-plan-1300-v1")
    if not plan.get("id"):
        raise CheckoutError("PayPal did not return a plan id")
    return {"product_id": pid, "plan_id": plan["id"], "env": paypal_env()}


# --------------------------------------------------------------------------
# Subscribe
# --------------------------------------------------------------------------


def subscription_body(user: dict, base_url: str) -> dict:
    base = base_url.rstrip("/")
    body: dict[str, Any] = {
        "plan_id": plan_id(),
        "custom_id": user["id"],
        "application_context": {
            "brand_name": BRAND_NAME,
            "shipping_preference": "NO_SHIPPING",
            "user_action": "SUBSCRIBE_NOW",
            "return_url": base + "/billing/success",
            "cancel_url": base + "/billing/cancel",
        },
    }
    email = (user.get("email") or "").strip()
    if email:
        body["subscriber"] = {"email_address": email}
    return body


def start_checkout(user: dict, base_url: str) -> str:
    if not keys_present():
        raise CheckoutError(KEYS_MISSING_MESSAGE)
    if not billing_enabled():
        raise CheckoutError(BILLING_OFF_MESSAGE)
    client = build_client()
    sub = client.request("POST", "/v1/billing/subscriptions", subscription_body(user, base_url))
    sub_id = sub.get("id") if isinstance(sub.get("id"), str) else ""
    approve = ""
    for link in sub.get("links") or []:
        if isinstance(link, dict) and link.get("rel") == "approve":
            approve = link.get("href") or ""
    if not sub_id or not approve:
        raise CheckoutError("PayPal did not return an approval link")
    status = None
    if user.get("subscription_status") not in {"active", "trialing"}:
        status = "incomplete"
    storage.set_billing(user["id"], subscription_id=sub_id, status=status)
    return approve


# --------------------------------------------------------------------------
# Webhooks
# --------------------------------------------------------------------------


def verify_webhook(headers: Any, payload: bytes, client: Any = None) -> dict:
    """Verify with PayPal's verify-webhook-signature API. Returns the parsed event."""
    try:
        event = json.loads(payload or b"")
    except ValueError as exc:
        raise SignatureError("invalid JSON") from exc
    if not isinstance(event, dict):
        raise SignatureError("invalid event")
    body: dict[str, Any] = {}
    for key, header in _SIG_HEADERS.items():
        value = headers.get(header) or ""
        if not value:
            raise SignatureError(f"missing {header}")
        body[key] = value
    body["webhook_id"] = webhook_id()
    body["webhook_event"] = event
    client = client or build_client()
    result = client.request("POST", "/v1/notifications/verify-webhook-signature", body)
    if result.get("verification_status") != "SUCCESS":
        raise SignatureError("PayPal verification failed")
    return event


def apply_event(event: dict) -> None:
    event_id = event.get("id") if isinstance(event.get("id"), str) else ""
    event_type = event.get("event_type") if isinstance(event.get("event_type"), str) else ""
    if event_type not in HANDLED_EVENTS:
        return
    claimed = False
    if event_id:
        claimed = storage.claim_paypal_event(event_id, event_type)
        if not claimed:
            return
    try:
        resource = event.get("resource") if isinstance(event.get("resource"), dict) else {}
        if _dispatch(event_type, resource) is False:
            raise UserNotFound(event_type)
    except Exception:
        if claimed:
            storage.forget_paypal_event(event_id)
        raise


def _dispatch(event_type: str, resource: dict) -> bool:
    if event_type.startswith("PAYMENT.SALE."):
        sub_id = _str(resource.get("billing_agreement_id"))
        if not sub_id:
            return True  # one-off sale, not a GeneMeal subscription
        user = _find_user(sub_id, _str(resource.get("custom")) or _str(resource.get("custom_id")))
    else:
        sub_id = _str(resource.get("id"))
        user = _find_user(sub_id, _str(resource.get("custom_id")))
    if user is None:
        return False
    status = _STATUS_FOR_EVENT.get(event_type)
    if status is None:
        status = _PAYPAL_STATUS.get(_str(resource.get("status")).upper())
        if status == "incomplete" and user.get("subscription_status") in {"active", "trialing"}:
            status = None
    storage.set_billing(user["id"], subscription_id=sub_id or None, status=status)
    return True


def _find_user(sub_id: str, custom_id: str) -> dict | None:
    if sub_id:
        user = storage.find_user_by_paypal_subscription(sub_id)
        if user is not None:
            return user
    if custom_id:
        return storage.get_user(custom_id)
    return None


def _str(value: Any) -> str:
    return value if isinstance(value, str) else ""
