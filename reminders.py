"""Reminder schedule for the 23andMe wait.

About 7 days and about 30 days after the person marks the request. Sending is
log-only unless REMINDER_EMAIL_ENABLED=1, and even then the sender is a stub:
it does not open a socket and it does not log the email address.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

import storage

log = logging.getLogger("genemeal.reminders")


def _iso(moment: datetime) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def schedule(uid: str, *, now: datetime | None = None) -> tuple[str, str]:
    moment = now or datetime.now(timezone.utc)
    when_7 = _iso(moment + timedelta(days=7))
    when_30 = _iso(moment + timedelta(days=30))
    storage.schedule_reminders(uid, when_7, when_30)
    return when_7, when_30


def _stub_send(kind: str) -> None:
    # No SMTP. The flag only distinguishes a stub "send" from a silent log.
    log.info("reminder stub-send kind=%s", kind)


def process_due(now: datetime | None = None) -> list[dict]:
    moment = now or datetime.now(timezone.utc)
    stamp = _iso(moment)
    enabled = os.environ.get("REMINDER_EMAIL_ENABLED") == "1"
    sent = []
    for row in storage.due_reminders(stamp):
        if enabled:
            _stub_send(row["kind"])
            channel = "stub"
        else:
            log.info("reminder log-only kind=%s", row["kind"])
            channel = "log"
        storage.mark_reminder(row["id"], stamp, channel)
        sent.append({"id": row["id"], "kind": row["kind"], "channel": channel})
    return sent
