from datetime import datetime, timedelta, timezone

from tests.helpers import post, upload
from tests.samples import genome_zip
import reminders
import storage


def _status(client):
    return client.get("/account/status").get_json()


def test_status_transitions_and_reminders(client, caplog):
    import logging

    assert _status(client)["status"] == "new"
    bad = post(client, "/account/requested", {"email": "not-an-email"})
    assert bad.status_code == 302
    assert "valid email" in client.get("/").get_data(as_text=True)
    assert _status(client)["status"] == "new"

    before = datetime.now(timezone.utc)
    response = post(client, "/account/requested", {"email": "ada@example.com"})
    assert response.status_code == 302
    after = datetime.now(timezone.utc)
    body = _status(client)
    assert body["status"] == "requested"
    assert body["email"] == "ada@example.com"
    assert len(body["reminders"]) == 2
    kinds = {row["kind"]: row["remind_at"] for row in body["reminders"]}
    assert set(kinds) == {"7d", "30d"}
    for kind, days in (("7d", 7), ("30d", 30)):
        moment = datetime.strptime(kinds[kind], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        assert before + timedelta(days=days) - timedelta(minutes=1) <= moment <= after + timedelta(days=days) + timedelta(minutes=1)

    page = client.get("/").get_data(as_text=True)
    assert "you.23andme.com/tools/data/" in page
    assert "raw data download is ready" in page
    assert "date of birth" in page
    assert "Drag the zip here" in page

    post(client, "/account/waiting")
    assert _status(client)["status"] == "waiting_email"

    name, raw = genome_zip()
    upload(client, name, raw)
    assert _status(client)["status"] == "uploaded"
    assert _status(client)["has_raw_file"] is True

    assert post(client, "/parse/confirm").status_code == 302
    confirmed = _status(client)
    assert confirmed["status"] == "parsed"
    assert confirmed["has_raw_file"] is False
    assert confirmed["has_summary"] is True
    assert "GRCh37" in client.get("/results").get_data(as_text=True)

    post(client, "/account/waiting")
    assert _status(client)["status"] == "parsed"

    with caplog.at_level(logging.INFO, logger="genemeal.reminders"):
        sent = reminders.process_due(datetime.now(timezone.utc) + timedelta(days=8))
    assert any(item["kind"] == "7d" and item["channel"] == "log" for item in sent)
    assert "stub-send" not in caplog.text
    assert "log-only" in caplog.text
    assert "ada@example.com" not in caplog.text


def test_reminder_stub_does_not_send_mail(client, monkeypatch):
    post(client, "/account/requested", {"email": "ada@example.com"})
    monkeypatch.setenv("REMINDER_EMAIL_ENABLED", "1")

    def _boom(*_args, **_kwargs):
        raise AssertionError("SMTP should not be constructed")

    monkeypatch.setattr("smtplib.SMTP", _boom, raising=False)
    sent = reminders.process_due(datetime.now(timezone.utc) + timedelta(days=31))
    assert {item["channel"] for item in sent} == {"stub"}
    routed = post(client, "/account/reminders/process")
    assert routed.status_code == 200
    assert routed.get_json()["processed"] == []


def test_encrypted_upload_is_not_plaintext(client):
    name, raw = genome_zip()
    upload(client, name, raw)
    folder = storage.data_dir() / "users"
    files = list(folder.glob("*/upload.bin"))
    assert len(files) == 1
    blob = files[0].read_bytes()
    assert b"23andMe" not in blob
    assert b"rs1801133" not in blob
    uid = files[0].parent.name
    assert storage.read_encrypted_upload(uid) == raw


def test_delete_my_data(client):
    name, raw = genome_zip()
    upload(client, name, raw)
    folder = storage.data_dir() / "users"
    uid = next(folder.iterdir()).name
    assert storage.get_user(uid)["status"] == "uploaded"
    post(client, "/parse/confirm")
    assert storage.get_user(uid)["status"] == "parsed"
    assert storage.encrypted_upload_path(uid) is None
    response = client.delete("/account/data", headers={"X-CSRF-Token": client.csrf})
    assert response.status_code == 302
    assert storage.get_user(uid) is None
    assert not (folder / uid).exists()
    page = client.get("/").get_data(as_text=True)
    assert "deleted" in page.lower()
    assert client.get("/account/status").get_json()["status"] == "new"


def test_delete_requires_the_checkbox_on_the_form(client):
    name, raw = genome_zip()
    upload(client, name, raw)
    response = post(client, "/account/data", {})
    assert response.status_code == 302
    assert client.get("/account/status").get_json()["status"] == "uploaded"
    response = post(client, "/account/data", {"confirm": "yes"})
    assert response.status_code == 302
    assert client.get("/account/status").get_json()["status"] == "new"


def test_bad_reupload_keeps_a_confirmed_file(client):
    name, raw = genome_zip()
    upload(client, name, raw)
    post(client, "/parse/confirm")
    upload(client, "genome_report.pdf", b"%PDF-1.4\n%%EOF\n", content_type="application/pdf")
    page = client.get("/").get_data(as_text=True)
    assert "PDF" in page
    assert client.get("/account/status").get_json()["status"] == "parsed"


def test_plan_page_after_confirm(client):
    from tests.test_dietplan import _paid
    _paid(client)
    assert "Confirm the parse first" in client.get("/plan").get_data(as_text=True)
    name, raw = genome_zip()
    upload(client, name, raw)
    post(client, "/parse/confirm")
    page = client.get("/plan").get_data(as_text=True)
    assert "Weight loss" in page
    assert "Build muscle" in page
    assert "Generate" in page
    assert "Not medical advice" in page
    generated = post(client, "/plan", {"weight_loss": "on"})
    assert generated.status_code == 200
    text = generated.get_data(as_text=True)
    for day in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"):
        assert day in text
    assert "Not medical advice" in text
    assert "1,700 kcal" in text
    assert "approximate" in text
