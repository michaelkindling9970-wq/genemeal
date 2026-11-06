"""SQLite records plus Fernet-encrypted uploads for one local GeneMeal instance.

The Fernet key comes from GENEMEAL_FERNET_KEY. If that variable is unset, a key
is created at DATA_DIR/.fernet_key so a laptop demo can restart. Do not use
that fallback on a shared host.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

STATUSES = ("new", "requested", "waiting_email", "uploaded", "parsed", "failed")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    marker_count INTEGER,
    genome_build INTEGER,
    snps_source TEXT,
    error TEXT,
    trait_summary BLOB,
    last_plan BLOB
);
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    remind_at TEXT NOT NULL,
    kind TEXT NOT NULL,
    sent_at TEXT,
    channel TEXT,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    path TEXT NOT NULL,
    nbytes INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def data_dir() -> Path:
    raw = os.environ.get("DATA_DIR") or "data"
    path = Path(raw)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(data_dir() / "genemeal.sqlite", timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(_SCHEMA)
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    have = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
    for name in (
        "paypal_subscription_id",
        "subscription_status",
        "stripe_customer_id",
        "stripe_subscription_id",
    ):
        if name not in have:
            conn.execute(f"ALTER TABLE users ADD COLUMN {name} TEXT")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS paypal_events (
            id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            received_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_users_paypal_subscription ON users(paypal_subscription_id)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS stripe_events (
            id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            received_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_users_stripe_customer ON users(stripe_customer_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_users_stripe_subscription ON users(stripe_subscription_id)")


def fernet() -> Fernet:
    env = os.environ.get("GENEMEAL_FERNET_KEY", "").strip()
    if env:
        key = env.encode()
    else:
        path = data_dir() / ".fernet_key"
        if path.exists():
            key = path.read_bytes().strip()
        else:
            key = Fernet.generate_key()
            path.write_bytes(key + b"\n")
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
    try:
        return Fernet(key)
    except (ValueError, TypeError) as exc:
        raise RuntimeError(
            "GENEMEAL_FERNET_KEY is not a valid Fernet key. Generate one with "
            'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        ) from exc


def _user_root(uid: str) -> Path:
    root = (data_dir() / "users").resolve()
    target = (root / uid).resolve()
    if not target.is_relative_to(root):
        raise ValueError("unsafe user id")
    return target


def ensure_user(uid: str) -> dict:
    stamp = now_iso()
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (id, status, created_at, updated_at) VALUES (?, 'new', ?, ?)",
            (uid, stamp, stamp),
        )
    user = get_user(uid)
    assert user is not None
    return user


def _public_user(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    data = dict(row)
    data.pop("trait_summary", None)
    data.pop("last_plan", None)
    return data


def get_user(uid: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    return _public_user(row)


def set_billing(
    uid: str,
    *,
    subscription_id: str | None = None,
    status: str | None = None,
) -> None:
    assignments = ["updated_at = ?"]
    values: list = [now_iso()]
    if subscription_id is not None:
        assignments.append("paypal_subscription_id = ?")
        values.append(subscription_id)
    if status is not None:
        assignments.append("subscription_status = ?")
        values.append(status)
    values.append(uid)
    with _connect() as conn:
        conn.execute(
            f"UPDATE users SET {', '.join(assignments)} WHERE id = ?",
            values,
        )


def find_user_by_paypal_subscription(subscription_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE paypal_subscription_id = ?",
            (subscription_id,),
        ).fetchone()
    return _public_user(row)


def claim_paypal_event(event_id: str, event_type: str) -> bool:
    """Return True when this webhook event id is recorded for the first time."""
    try:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO paypal_events (id, event_type, received_at) VALUES (?, ?, ?)",
                (event_id, event_type, now_iso()),
            )
    except sqlite3.IntegrityError:
        return False
    return True


def forget_paypal_event(event_id: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM paypal_events WHERE id = ?", (event_id,))


def set_stripe_billing(
    uid: str,
    *,
    customer_id: str | None = None,
    subscription_id: str | None = None,
    status: str | None = None,
) -> None:
    """Stripe ids get their own columns; paypal_subscription_id is never touched."""
    assignments = ["updated_at = ?"]
    values: list = [now_iso()]
    for column, value in (
        ("stripe_customer_id", customer_id),
        ("stripe_subscription_id", subscription_id),
        ("subscription_status", status),
    ):
        if value is not None:
            assignments.append(f"{column} = ?")
            values.append(value)
    values.append(uid)
    with _connect() as conn:
        conn.execute(f"UPDATE users SET {', '.join(assignments)} WHERE id = ?", values)


def find_user_by_stripe_customer(customer_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE stripe_customer_id = ?", (customer_id,)).fetchone()
    return _public_user(row)


def find_user_by_stripe_subscription(subscription_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE stripe_subscription_id = ?", (subscription_id,)).fetchone()
    return _public_user(row)


def claim_stripe_event(event_id: str, event_type: str) -> bool:
    try:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO stripe_events (id, event_type, received_at) VALUES (?, ?, ?)",
                (event_id, event_type, now_iso()),
            )
    except sqlite3.IntegrityError:
        return False
    return True


def forget_stripe_event(event_id: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM stripe_events WHERE id = ?", (event_id,))


def set_email(uid: str, email: str | None) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET email = ?, updated_at = ? WHERE id = ?",
            (email, now_iso(), uid),
        )


def _write_status(uid: str, status: str, **fields) -> None:
    if status not in STATUSES:
        raise ValueError(status)
    assignments = ["status = ?", "updated_at = ?"]
    values: list = [status, now_iso()]
    for key, value in fields.items():
        assignments.append(f"{key} = ?")
        values.append(value)
    values.append(uid)
    with _connect() as conn:
        conn.execute(f"UPDATE users SET {', '.join(assignments)} WHERE id = ?", values)


def set_status(uid: str, status: str) -> None:
    _write_status(uid, status)


def schedule_reminders(uid: str, when_7: str, when_30: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM reminders WHERE user_id = ? AND sent_at IS NULL", (uid,))
        conn.execute(
            "INSERT INTO reminders (user_id, remind_at, kind) VALUES (?, ?, '7d'), (?, ?, '30d')",
            (uid, when_7, uid, when_30),
        )


def list_reminders(uid: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, user_id, remind_at, kind, sent_at, channel FROM reminders WHERE user_id = ? ORDER BY remind_at",
            (uid,),
        ).fetchall()
    return [dict(row) for row in rows]


def due_reminders(now: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT r.id, r.user_id, r.remind_at, r.kind, u.email
            FROM reminders r JOIN users u ON u.id = r.user_id
            WHERE r.sent_at IS NULL AND r.remind_at <= ?
            ORDER BY r.remind_at
            """,
            (now,),
        ).fetchall()
    return [dict(row) for row in rows]


def mark_reminder(reminder_id: int, sent_at: str, channel: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE reminders SET sent_at = ?, channel = ? WHERE id = ?",
            (sent_at, channel, reminder_id),
        )


def save_encrypted_upload(uid: str, raw: bytes) -> Path:
    folder = _user_root(uid)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "upload.bin"
    token = fernet().encrypt(raw)
    path.write_bytes(token)
    stamp = now_iso()
    with _connect() as conn:
        conn.execute("DELETE FROM files WHERE user_id = ?", (uid,))
        conn.execute(
            "INSERT INTO files (user_id, path, nbytes, created_at) VALUES (?, ?, ?, ?)",
            (uid, str(path), len(token), stamp),
        )
    return path


def encrypted_upload_path(uid: str) -> Path | None:
    path = _user_root(uid) / "upload.bin"
    return path if path.exists() else None


def read_encrypted_upload(uid: str) -> bytes | None:
    path = encrypted_upload_path(uid)
    if path is None:
        return None
    try:
        return fernet().decrypt(path.read_bytes())
    except InvalidToken:
        return None


def delete_upload_file(uid: str) -> None:
    folder = _user_root(uid)
    target = folder / "upload.bin"
    if target.exists():
        target.unlink()
    with _connect() as conn:
        conn.execute("DELETE FROM files WHERE user_id = ?", (uid,))
    if folder.exists() and not any(folder.iterdir()):
        folder.rmdir()


def save_summary(uid: str, summary: dict) -> None:
    blob = fernet().encrypt(json.dumps(summary).encode("utf-8"))
    _write_status(
        uid,
        "uploaded",
        marker_count=summary.get("marker_count"),
        genome_build=summary.get("build"),
        snps_source=summary.get("source"),
        error=None,
        trait_summary=blob,
        last_plan=None,
    )


def get_summary(uid: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT trait_summary FROM users WHERE id = ?", (uid,)).fetchone()
    if row is None or row["trait_summary"] is None:
        return None
    try:
        raw = fernet().decrypt(row["trait_summary"])
    except InvalidToken:
        return None
    return json.loads(raw.decode("utf-8"))


def save_plan(uid: str, plan: dict) -> None:
    blob = fernet().encrypt(json.dumps(plan).encode("utf-8"))
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET last_plan = ?, updated_at = ? WHERE id = ?",
            (blob, now_iso(), uid),
        )


def get_plan(uid: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT last_plan FROM users WHERE id = ?", (uid,)).fetchone()
    if row is None or row["last_plan"] is None:
        return None
    try:
        raw = fernet().decrypt(row["last_plan"])
    except InvalidToken:
        return None
    return json.loads(raw.decode("utf-8"))


def mark_failed(uid: str, message: str) -> None:
    delete_upload_file(uid)
    _write_status(
        uid,
        "failed",
        error=message,
        marker_count=None,
        genome_build=None,
        snps_source=None,
        trait_summary=None,
        last_plan=None,
    )


def mark_parsed(uid: str) -> None:
    delete_upload_file(uid)
    _write_status(uid, "parsed", error=None)


def delete_user(uid: str) -> None:
    folder = _user_root(uid)
    if folder.exists():
        shutil.rmtree(folder)
    with _connect() as conn:
        conn.execute("DELETE FROM reminders WHERE user_id = ?", (uid,))
        conn.execute("DELETE FROM files WHERE user_id = ?", (uid,))
        conn.execute("DELETE FROM users WHERE id = ?", (uid,))
