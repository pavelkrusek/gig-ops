import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from gig_ops.db import DB_PATH, db
from gig_ops.domain.models import Contact, Event, MailDraft
from gig_ops.log import logger
from gig_ops.protocol.repository import Repository

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


def _suppressed(conn: Any, pattern: str) -> bool:
    if pattern.startswith(("http://", "https://")):
        domain = urlparse(pattern).netloc.removeprefix("www.")
    elif "@" in pattern:
        domain = pattern.split("@")[-1]
    else:
        domain = pattern
    return conn.execute(
        "SELECT 1 FROM suppression WHERE pattern IN (?, ?)", (pattern, domain)
    ).fetchone() is not None


def _dedupe_key(name: str, url: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", name.lower())
    normalized = normalized.encode("ascii", "ignore").decode()
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    if url:
        domain = urlparse(url).netloc.removeprefix("www.")
        return f"{normalized}|{domain}"
    return normalized


def _row_to_event(row: Any) -> Event:
    d = dict(row)
    return Event(
        id=d["id"],
        name=d["name"],
        status=d["status"],
        url=d["url"],
        date=d["date"],
        location=d["location"],
        type=d["type"],
        score_final=d["score_final"],
        score_dimensions=json.loads(d["score_dimensions_json"]) if d["score_dimensions_json"] else {},
        raw_scraped_text=d["raw_scraped_text"],
        source=d["source"],
        source_confidence=d["source_confidence"],
        dedupe_key=d["dedupe_key"],
        possible_duplicate_of=d["possible_duplicate_of"],
        needs_review=bool(d["needs_review"]),
        review_reason=d["review_reason"],
        found_at=d["found_at"],
        updated_at=d["updated_at"],
        mode_versions=json.loads(d["mode_versions_json"]) if d["mode_versions_json"] else {},
    )


def _row_to_contact(row: Any) -> Contact:
    d = dict(row)
    return Contact(
        id=d["id"],
        event_id=d["event_id"],
        found_at=d["found_at"],
        organizer_name=d["organizer_name"],
        organizer_email=d["organizer_email"],
        email_domain_verified=bool(d["email_domain_verified"]),
        source_url=d["source_url"],
    )


def _row_to_mail_draft(row: Any) -> MailDraft:
    d = dict(row)
    return MailDraft(
        id=d["id"],
        event_id=d["event_id"],
        generated_at=d["generated_at"],
        draft_path=d["draft_path"],
        language=d["language"],
        variant_label=d["variant_label"],
        mode_version=d["mode_version"],
    )


class SQLiteRepository(Repository):
    def __init__(self, db_path: Path = DB_PATH) -> None:
        self._db_path = db_path

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def add_event(
            self,
            *,
            name: str,
            url: str | None = None,
            source: str | None = None,
            source_confidence: str | None = None,
            raw_scraped_text: str | None = None,
    ) -> int | None:
        with db(self._db_path) as conn:
            if url and _suppressed(conn, url):
                logger.info("Skipping suppressed URL: {}", url)
                return None

            key = _dedupe_key(name, url)
            if conn.execute("SELECT id FROM events WHERE dedupe_key = ?", (key,)).fetchone():
                logger.debug("Duplicate event skipped: {}", name)
                return None

            now = _now()
            cur = conn.execute(
                """
                INSERT INTO events (name, url, source, source_confidence, raw_scraped_text,
                                    dedupe_key, status, found_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 'NEW', ?, ?)
                """,
                (name, url, source, source_confidence, raw_scraped_text, key, now, now),
            )
            event_id: int = cur.lastrowid  # type: ignore[assignment]
            logger.info("Event added: {} (id={})", name, event_id)
            return event_id

    def set_status(self, event_id: int, new_status: str) -> None:
        with db(self._db_path) as conn:
            row = conn.execute("SELECT status FROM events WHERE id = ?", (event_id,)).fetchone()
            if not row:
                raise ValueError(f"Event {event_id} not found")
            current: str = row["status"]
            if new_status not in _TRANSITIONS.get(current, set()):
                raise ValueError(f"Invalid transition: {current} → {new_status}")
            conn.execute(
                "UPDATE events SET status = ?, updated_at = ? WHERE id = ?",
                (new_status, _now(), event_id),
            )
            logger.info("Event {} status: {} → {}", event_id, current, new_status)

    def save_evaluation(
            self,
            event_id: int,
            *,
            score_final: str,
            score_dimensions: dict[str, Any],
            mode_version: str,
    ) -> None:
        with db(self._db_path) as conn:
            conn.execute(
                """
                UPDATE events
                SET score_final           = ?,
                    score_dimensions_json = ?,
                    mode_versions_json    = ?,
                    updated_at            = ?
                WHERE id = ?
                """,
                (score_final, json.dumps(score_dimensions), json.dumps({"evaluate": mode_version}), _now(), event_id),
            )
        self.set_status(event_id, "EVALUATED")
        if score_final in ("D", "F"):
            self.set_status(event_id, "DROPPED")

    def save_contact(
            self,
            event_id: int,
            *,
            organizer_name: str | None,
            organizer_email: str | None,
            email_domain_verified: bool,
            source_url: str | None,
    ) -> None:
        with db(self._db_path) as conn:
            if organizer_email and _suppressed(conn, organizer_email):
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
        self.set_status(event_id, "CONTACT_FOUND")

    def save_mail_draft(
            self,
            event_id: int,
            *,
            draft_path: str,
            language: str,
            variant_label: str,
            mode_version: str,
    ) -> None:
        with db(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO mails (event_id, draft_path, language, variant_label, generated_at, mode_version)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (event_id, draft_path, language, variant_label, _now(), mode_version),
            )
        self.set_status(event_id, "MAIL_DRAFTED")

    def add_suppression(self, pattern: str, reason: str | None = None) -> None:
        with db(self._db_path) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO suppression (pattern, reason, added_at) VALUES (?, ?, ?)",
                (pattern, reason, _now()),
            )
        logger.info("Suppressed: {}", pattern)

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get_event_by_id(self, event_id: int) -> Event | None:
        with db(self._db_path) as conn:
            row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
            return _row_to_event(row) if row else None

    def get_event_by_name(self, name: str) -> Event | None:
        with db(self._db_path) as conn:
            row = conn.execute(
                "SELECT * FROM events WHERE name = ? ORDER BY found_at DESC LIMIT 1", (name,)
            ).fetchone()
            return _row_to_event(row) if row else None

    def list_events(self, status: str | None = None) -> list[Event]:
        with db(self._db_path) as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM events WHERE status = ? ORDER BY found_at DESC", (status,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM events ORDER BY found_at DESC").fetchall()
            return [_row_to_event(r) for r in rows]

    def get_contact(self, event_id: int) -> Contact | None:
        with db(self._db_path) as conn:
            row = conn.execute(
                "SELECT * FROM contacts WHERE event_id = ? ORDER BY found_at DESC LIMIT 1", (event_id,)
            ).fetchone()
            return _row_to_contact(row) if row else None

    def list_mail_drafts(self, event_id: int) -> list[MailDraft]:
        with db(self._db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM mails WHERE event_id = ? ORDER BY generated_at", (event_id,)
            ).fetchall()
            return [_row_to_mail_draft(r) for r in rows]

    def is_suppressed(self, pattern: str) -> bool:
        with db(self._db_path) as conn:
            return _suppressed(conn, pattern)
