"""GeneMeal — educational 23andMe raw-data notes and a 7-day menu sketch.

Not medical advice. Geo-block stays off unless GEO_BLOCK_ENABLED=1.
Raw genotype bytes are encrypted at rest and removed after you confirm the parse.
"""
from __future__ import annotations

import hmac
import os
import re
import secrets
from datetime import datetime, timedelta

from flask import Flask, Response, flash, jsonify, redirect, render_template, request, session, url_for

import billing
import blocked_states
import fdc
import genome
import mealplan
import pricing
import reminders
import storage
import traits

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY") or os.urandom(32).hex(),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("GENEMEAL_COOKIE_SECURE") == "1",
    MAX_CONTENT_LENGTH=52 * 1024 * 1024,
    MAX_UPLOAD_BYTES=genome.MAX_UPLOAD_BYTES,
    PERMANENT_SESSION_LIFETIME=timedelta(days=60),
)

DOWNLOAD_URL = "https://you.23andme.com/tools/data/"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Tests inject a FoodData Central client. Production leaves this as None.
fdc_client_factory = None


@app.before_request
def geo_block_gate():
    """Deny visitors from blocked US states when GEO_BLOCK_ENABLED=1. Logs state only, never IP."""
    blocked, state = blocked_states.should_block(request)
    if not blocked:
        return None
    try:
        app.logger.info("geo_block deny state=%s path=%s", state, request.path)
    except Exception:
        pass
    body = f"""<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Not available in your area — GeneMeal</title>
<style>body{{font-family:system-ui,sans-serif;background:#0b1220;color:#e8eef8;margin:0;display:grid;min-height:100vh;place-items:center;padding:2rem}}
main{{max-width:32rem;line-height:1.5}}h1{{font-size:1.35rem;margin:0 0 .75rem}}p{{margin:0;color:#b7c4d8}}</style>
<main><h1>Not available in your area</h1><p>{blocked_states.BLOCKED_FRIENDLY}</p></main>"""
    return Response(body, status=451, mimetype="text/html")


@app.before_request
def csrf_gate():
    if request.path.rstrip("/") == "/stripe/webhook":
        return None
    if request.method == "GET":
        if "csrf" not in session:
            session["csrf"] = secrets.token_hex(16)
        return None
    expected = session.get("csrf") or ""
    supplied = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token") or ""
    if not expected or not hmac.compare_digest(expected, supplied):
        return render_template("message.html", title="Page expired", body="Reload the page and try that again."), 400
    return None


@app.context_processor
def inject_globals():
    return {
        "csrf_token": session.get("csrf", ""),
        "disclaimer": mealplan.DISCLAIMER,
        "download_url": DOWNLOAD_URL,
        "flash": session.pop("flash", None),
        "pricing": _pricing_context(),
    }


def _pricing_context() -> dict:
    status = ""
    uid = session.get("uid")
    if isinstance(uid, str) and uid:
        user = storage.get_user(uid)
        if user:
            status = user.get("subscription_status") or ""
    data = pricing.view()
    data.update(billing.checkout_view(status))
    return data


def _external_base() -> str:
    configured = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if configured:
        return configured
    proto = (request.headers.get("X-Forwarded-Proto") or request.scheme or "https").split(",")[0].strip()
    host = (request.headers.get("X-Forwarded-Host") or request.host).split(",")[0].strip()
    return f"{proto}://{host}"


def _notice(message: str, category: str = "ok") -> None:
    session["flash"] = {"category": category, "message": message}


def _uid() -> str:
    uid = session.get("uid")
    if not uid or not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", uid):
        uid = secrets.token_urlsafe(12)
        session["uid"] = uid
        session.permanent = True
    storage.ensure_user(uid)
    return uid


def _load() -> dict:
    return storage.ensure_user(_uid())


def _make_fdc() -> fdc.FdcClient:
    if fdc_client_factory is not None:
        return fdc_client_factory()
    return fdc.FdcClient(cache_path=storage.data_dir() / "fdc_cache.json")


def _clean_email(raw: str | None) -> str | None:
    text = (raw or "").strip()
    if not text:
        return None
    if not EMAIL_RE.match(text) or len(text) > 200:
        raise ValueError("Enter a valid email, or leave the field blank.")
    return text


def _parse_reminders(rows: list[dict]) -> list[dict]:
    shown = []
    for row in rows:
        try:
            moment = datetime.strptime(row["remind_at"], "%Y-%m-%dT%H:%M:%SZ")
            label = f"{moment:%b} {moment.day}, {moment.year}"
        except ValueError:
            label = row["remind_at"]
        shown.append({**row, "label": label})
    return shown


@app.get("/pricing")
def pricing_page():
    return render_template("pricing.html")


@app.post("/billing/checkout")
def billing_checkout():
    user = _load()
    if not billing.keys_present() or billing.StripeClient is None:
        _notice(billing.KEYS_MISSING_MESSAGE, "error")
        return redirect(url_for("home"))
    if not billing.billing_enabled():
        _notice(billing.BILLING_OFF_MESSAGE, "error")
        return redirect(url_for("home"))
    try:
        url = billing.start_checkout(user, _external_base())
    except Exception as exc:
        app.logger.info("checkout start failed: %s", billing.safe_error(exc))
        _notice("Checkout could not be started. Check the Stripe keys and price.", "error")
        return redirect(url_for("home"))
    return redirect(url, code=303)


@app.get("/billing/success")
def billing_success():
    return render_template(
        "message.html",
        title="Checkout returned",
        body=(
            "Stripe Checkout returned to GeneMeal. The subscription is recorded "
            "when Stripe sends the webhook. Upload stays available on the guide page."
        ),
    )


@app.get("/billing/cancel")
def billing_cancel():
    _notice("Checkout was canceled.", "error")
    return redirect(url_for("home"))


@app.post("/stripe/webhook")
def stripe_webhook():
    secret = billing.webhook_secret()
    if not secret:
        return jsonify({"error": billing.KEYS_MISSING_MESSAGE}), 503
    payload = request.get_data(cache=False) or b""
    signature = request.headers.get("Stripe-Signature", "")
    try:
        event = billing.construct_webhook_event(payload, signature, secret)
    except billing.SignatureError:
        return jsonify({"error": "invalid signature"}), 400
    except Exception as exc:
        app.logger.info("stripe webhook rejected: %s", billing.safe_error(exc))
        return jsonify({"error": "invalid payload"}), 400
    event_id = getattr(event, "id", None)
    event_type = getattr(event, "type", None)
    app.logger.info("stripe webhook type=%s id=%s", event_type, event_id)
    try:
        client = None
        if billing.secret_key() and os.environ.get("GENEMEAL_FORBID_NETWORK") != "1":
            client = billing.build_client()
        billing.apply_event(event, client=client)
    except billing.UserNotFound:
        app.logger.info("stripe webhook user not found type=%s id=%s", event_type, event_id)
        return jsonify({"error": "user not found"}), 500
    except billing.CheckoutError as exc:
        app.logger.info("stripe webhook skipped: %s", billing.safe_error(exc))
        return jsonify({"error": "webhook unavailable"}), 503
    except Exception as exc:
        app.logger.info("stripe webhook failed: %s", billing.safe_error(exc))
        return jsonify({"error": "webhook failed"}), 500
    return jsonify({"received": True})


@app.get("/")
def home():
    user = _load()
    rows = _parse_reminders(storage.list_reminders(user["id"]))
    return render_template("home.html", user=user, reminders=rows)


@app.get("/results")
def results():
    user = _load()
    summary = storage.get_summary(user["id"])
    return render_template("results.html", user=user, summary=summary)


@app.get("/plan")
def plan():
    user = _load()
    return render_template("plan.html", user=user, plan=storage.get_plan(user["id"]), generated=False)


@app.post("/plan")
def plan_generate():
    user = _load()
    if user["status"] != "parsed" or storage.get_summary(user["id"]) is None:
        _notice("Confirm the parsed file before generating a week.", "error")
        return redirect(url_for("plan"))
    weight_loss = request.form.get("weight_loss") == "on"
    build_muscle = request.form.get("build_muscle") == "on"
    summary = storage.get_summary(user["id"])
    menu = mealplan.build_meal_plan(
        summary,
        weight_loss=weight_loss,
        build_muscle=build_muscle,
        fdc_client=_make_fdc(),
    )
    storage.save_plan(user["id"], menu)
    return render_template("plan.html", user=storage.get_user(user["id"]), plan=menu, generated=True)


@app.post("/upload")
def upload():
    user = _load()
    incoming = request.files.get("genome")
    if incoming is None or not incoming.filename:
        _notice("Choose a genome zip first.", "error")
        return redirect(url_for("home"))
    data = incoming.read()
    max_bytes = int(app.config.get("MAX_UPLOAD_BYTES") or genome.MAX_UPLOAD_BYTES)
    try:
        text = genome.screen_upload(incoming.filename, data, max_bytes=max_bytes)
        parsed = genome.parse_genotype_bytes(text)
        summary = traits.summarize(parsed)
    except genome.Rejected as exc:
        # A bad file should not wipe notes that were already read.
        if user["status"] in {"uploaded", "parsed"} and storage.get_summary(user["id"]) is not None:
            _notice(exc.message, "error")
            return redirect(url_for("home"))
        storage.mark_failed(user["id"], exc.message)
        _notice("That file was rejected.", "error")
        return redirect(url_for("home"))
    storage.save_encrypted_upload(user["id"], data)
    storage.save_summary(user["id"], summary)
    app.logger.info(
        "upload accepted markers=%s build=%s",
        summary.get("marker_count"),
        summary.get("build"),
    )
    _notice("File read. Review the markers, then confirm.", "ok")
    return redirect(url_for("results"))


@app.post("/parse/confirm")
def confirm_parse():
    user = _load()
    summary = storage.get_summary(user["id"])
    if user["status"] != "uploaded" or summary is None:
        _notice("There is no parsed file waiting to confirm.", "error")
        return redirect(url_for("results"))
    storage.mark_parsed(user["id"])
    _notice("Notes saved. The raw file was removed from disk. You can generate a week.", "ok")
    return redirect(url_for("plan"))


@app.post("/account/requested")
def mark_requested():
    user = _load()
    if user["status"] in {"uploaded", "parsed"}:
        _notice("A file is already on this session, so the request status was left as it is.", "error")
        return redirect(url_for("home"))
    try:
        email = _clean_email(request.form.get("email"))
    except ValueError as exc:
        _notice(str(exc), "error")
        return redirect(url_for("home"))
    if email:
        storage.set_email(user["id"], email)
    when_7, when_30 = reminders.schedule(user["id"])
    storage.set_status(user["id"], "requested")
    _notice(f"Marked as requested. Reminders are stored for {when_7[:10]} and {when_30[:10]}.", "ok")
    return redirect(url_for("home"))


@app.post("/account/waiting")
def mark_waiting():
    user = _load()
    if user["status"] in {"uploaded", "parsed"}:
        _notice("A file is already on this session, so the status was left as it is.", "error")
        return redirect(url_for("home"))
    if not storage.list_reminders(user["id"]):
        reminders.schedule(user["id"])
    storage.set_status(user["id"], "waiting_email")
    _notice("Status set to waiting for the 23andMe email.", "ok")
    return redirect(url_for("home"))


@app.post("/account/reminders/process")
def process_reminders():
    _load()
    sent = reminders.process_due()
    return jsonify({"processed": sent})


@app.get("/account/status")
def account_status():
    user = _load()
    summary = storage.get_summary(user["id"])
    return jsonify(
        {
            "status": user["status"],
            "email": user.get("email"),
            "marker_count": user.get("marker_count"),
            "genome_build": user.get("genome_build"),
            "source": user.get("snps_source"),
            "error": user.get("error"),
            "has_raw_file": storage.encrypted_upload_path(user["id"]) is not None,
            "has_summary": summary is not None,
            "reminders": storage.list_reminders(user["id"]),
        }
    )


@app.route("/account/data", methods=["DELETE", "POST"])
def delete_data():
    if request.method == "POST" and request.form.get("confirm") != "yes":
        _notice("Check the box to confirm deletion.", "error")
        return redirect(url_for("home"))
    uid = session.get("uid")
    if uid:
        storage.delete_user(uid)
    session.clear()
    _notice("Your encrypted file and records were deleted from this server.", "ok")
    return redirect(url_for("home"))


@app.get("/robots.txt")
def robots():
    return Response("User-agent: *\nDisallow: /\n", mimetype="text/plain")


@app.get("/favicon.ico")
def favicon():
    return Response(status=204)


@app.get("/health")
def health():
    return {"ok": True, "geo_block": blocked_states.enabled()}


@app.errorhandler(413)
def too_large(_exc):
    return (
        render_template(
            "message.html",
            title="File too large",
            body="This upload is too large. The limit is 50 MB.",
        ),
        413,
    )


@app.errorhandler(404)
def missing(_exc):
    return render_template("message.html", title="Not found", body="That page is not part of GeneMeal."), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8741")))
