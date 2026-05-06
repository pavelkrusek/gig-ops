import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from gig_ops.db import db
from gig_ops.log import logger

# Valid status transitions
_TRANSITIONS: dict[str, set[str]] = {
    "NEW": {"EVALUATED"},
    "EVALUATED": {"CONTACT_FOUND", "DROPPED"},
    "CONTACT_FOUND": {"MAIL_DRAFTED"},
    "MAIL_DRAFTED": {"SENT"},
    "SENT": {"REPLIED", "NO_REPLY", "BOOKED", "REJECTED"},
    "REPLIED": {"BOOKED", "REJECTED"},
    "NO_REPLY": {"SENT"},  # allow re-send after follow-up
    "DROPPED": set(),
    "BOOKED": set(),
    "REJECTED": set(),
}

ALL_STATUSES = set(_TRANSITIONS.keys())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_suppressed(conn: Any, pattern: str) -> bool:
    """Check email, domain, or URL against suppression table."""
    from urllib.parse import urlparse

    if pattern.startswith(("http://", "https://")):
        domain = urlparse(pattern).netloc.removeprefix("www.")
    elif "@" in pattern:
        domain = pattern.split("@")[-1]
    else:
        domain = pattern

    row = conn.execute(
        "SELECT 1 FROM suppression WHERE pattern IN (?, ?)",
        (pattern, domain),
    ).fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------

def add_event(
        *,
        name: str,
        url: str | None = None,
        source: str | None = None,
        source_confidence: str | None = None,
        db_path: Path | None = None,
) -> int | None:
    """Insert a new event. Returns the new row id, or None if suppressed/duplicate."""
    kwargs: dict[str, Any] = {}
    if db_path:
        kwargs["db_path"] = db_path

    with db(**kwargs) as conn:
        if url and _is_suppressed(conn, url):
            logger.info("Skipping suppressed URL: {}", url)
            return None

        dedupe_key = _make_dedupe_key(name=name, url=url)
        existing = conn.execute(
            "SELECT id FROM events WHERE dedupe_key = ?", (dedupe_key,)
        ).fetchone()
        if existing:
            logger.debug("Duplicate event skipped: {} (id={})", name, existing["id"])
            return None

        now = _now()
        cur = conn.execute(
            """
            INSERT INTO events (name, url, source, source_confidence, dedupe_key, status, found_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'NEW', ?, ?)
            """,
            (name, url, source, source_confidence, dedupe_key, now, now),
        )
        event_id = cur.lastrowid
        logger.info("Event added: {} (id={})", name, event_id)
        return event_id


def set_status(event_id: int, new_status: str, db_path: Path | None = None) -> None:
    """Transition an event to a new status. Raises ValueError on invalid transition."""
    kwargs: dict[str, Any] = {}
    if db_path:
        kwargs["db_path"] = db_path

    with db(**kwargs) as conn:
        row = conn.execute("SELECT status FROM events WHERE id = ?", (event_id,)).fetchone()
        if not row:
            raise ValueError(f"Event {event_id} not found")

        current = row["status"]
        if new_status not in _TRANSITIONS.get(current, set()):
            raise ValueError(f"Invalid transition: {current} → {new_status}")

        conn.execute(
            "UPDATE events SET status = ?, updated_at = ? WHERE id = ?",
            (new_status, _now(), event_id),
        )
        logger.info("Event {} status: {} → {}", event_id, current, new_status)


def save_evaluation(
        event_id: int,
        *,
        score_final: str,
        score_dimensions: dict[str, Any],
        mode_version: str,
        db_path: Path | None = None,
) -> None:
    """Store evaluation results and advance status to EVALUATED or DROPPED."""
    kwargs: dict[str, Any] = {}
    if db_path:
        kwargs["db_path"] = db_path

    with db(**kwargs) as conn:
        conn.execute(
            """
            UPDATE events
            SET score_final           = ?,
                score_dimensions_json = ?,
                mode_versions_json    = ?,
                updated_at            = ?
            WHERE id = ?
            """,
            (
                score_final,
                json.dumps(score_dimensions),
                json.dumps({"evaluate": mode_version}),
                _now(),
                event_id,
            ),
        )

    set_status(event_id, "EVALUATED", db_path)
    if score_final in ("D", "F"):
        set_status(event_id, "DROPPED", db_path)


def save_contact(
        event_id: int,
        *,
        organizer_name: str | None,
        organizer_email: str | None,
        email_domain_verified: bool,
        source_url: str | None,
        db_path: Path | None = None,
) -> None:
    """Store organizer contact. Skips if email is suppressed."""
    kwargs: dict[str, Any] = {}
    if db_path:
        kwargs["db_path"] = db_path

    with db(**kwargs) as conn:
        if organizer_email and _is_suppressed(conn, organizer_email):
            logger.warning("Contact email suppressed, skipping: {}", organizer_email)
            return

        conn.execute(
            """
            INSERT INTO contacts (event_id, organizer_name, organizer_email, email_domain_verified, source_url,
                                  found_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (event_id, organizer_name, organizer_email, int(email_domain_verified), source_url, _now()),
        )

    set_status(event_id, "CONTACT_FOUND", db_path)


def save_mail_draft(
        event_id: int,
        *,
        draft_path: str,
        language: str,
        variant_label: str,
        mode_version: str,
        db_path: Path | None = None,
) -> None:
    """Record a generated mail draft."""
    kwargs: dict[str, Any] = {}
    if db_path:
        kwargs["db_path"] = db_path

    with db(**kwargs) as conn:
        conn.execute(
            """
            INSERT INTO mails (event_id, draft_path, language, variant_label, generated_at, mode_version)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (event_id, draft_path, language, variant_label, _now(), mode_version),
        )

    set_status(event_id, "MAIL_DRAFTED", db_path)


def add_suppression(pattern: str, reason: str | None = None, db_path: Path | None = None) -> None:
    """Add an email or domain to the suppression list."""
    kwargs: dict[str, Any] = {}
    if db_path:
        kwargs["db_path"] = db_path

    with db(**kwargs) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO suppression (pattern, reason, added_at) VALUES (?, ?, ?)",
            (pattern, reason, _now()),
        )
    logger.info("Suppressed: {}", pattern)


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------

def get_event_by_id(event_id: int, db_path: Path | None = None) -> dict[str, Any] | None:
    kwargs: dict[str, Any] = {}
    if db_path:
        kwargs["db_path"] = db_path

    with db(**kwargs) as conn:
        row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
        return dict(row) if row else None


def get_event_by_name(name: str, db_path: Path | None = None) -> dict[str, Any] | None:
    kwargs: dict[str, Any] = {}
    if db_path:
        kwargs["db_path"] = db_path

    with db(**kwargs) as conn:
        row = conn.execute(
            "SELECT * FROM events WHERE name = ? ORDER BY found_at DESC LIMIT 1", (name,)
        ).fetchone()
        return dict(row) if row else None


def list_events(
        status: str | None = None,
        db_path: Path | None = None,
) -> list[dict[str, Any]]:
    kwargs: dict[str, Any] = {}
    if db_path:
        kwargs["db_path"] = db_path

    with db(**kwargs) as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM events WHERE status = ? ORDER BY found_at DESC", (status,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM events ORDER BY found_at DESC").fetchall()
        return [dict(r) for r in rows]


def get_contact(event_id: int, db_path: Path | None = None) -> dict[str, Any] | None:
    kwargs: dict[str, Any] = {}
    if db_path:
        kwargs["db_path"] = db_path

    with db(**kwargs) as conn:
        row = conn.execute(
            "SELECT * FROM contacts WHERE event_id = ? ORDER BY found_at DESC LIMIT 1",
            (event_id,),
        ).fetchone()
        return dict(row) if row else None


def list_mail_drafts(event_id: int, db_path: Path | None = None) -> list[dict[str, Any]]:
    kwargs: dict[str, Any] = {}
    if db_path:
        kwargs["db_path"] = db_path

    with db(**kwargs) as conn:
        rows = conn.execute(
            "SELECT * FROM mails WHERE event_id = ? ORDER BY generated_at", (event_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def is_suppressed(pattern: str, db_path: Path | None = None) -> bool:
    kwargs: dict[str, Any] = {}
    if db_path:
        kwargs["db_path"] = db_path

    with db(**kwargs) as conn:
        return _is_suppressed(conn, pattern)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_dedupe_key(*, name: str, url: str | None) -> str:
    import re
    import unicodedata

    normalized = unicodedata.normalize("NFKD", name.lower())
    normalized = normalized.encode("ascii", "ignore").decode()
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")

    if url:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.removeprefix("www.")
        return f"{normalized}|{domain}"

    return normalized
