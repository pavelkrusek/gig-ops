import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

DB_PATH = Path("data/gigs.db")
SCHEMA_VERSION = 1


def _apply_migrations(conn: sqlite3.Connection) -> None:
    version: int = conn.execute("PRAGMA user_version").fetchone()[0]

    if version < 1:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS events (
                id                      INTEGER PRIMARY KEY,
                name                    TEXT NOT NULL,
                url                     TEXT,
                date                    TEXT,
                location                TEXT,
                type                    TEXT,
                score_final             TEXT,
                score_dimensions_json   TEXT,
                raw_scraped_text        TEXT,
                status                  TEXT NOT NULL DEFAULT 'NEW',
                source                  TEXT,
                source_confidence       TEXT,
                dedupe_key              TEXT,
                possible_duplicate_of   INTEGER REFERENCES events(id),
                needs_review            INTEGER NOT NULL DEFAULT 0,
                review_reason           TEXT,
                found_at                TEXT NOT NULL,
                updated_at              TEXT NOT NULL,
                mode_versions_json      TEXT
            );

            CREATE TABLE IF NOT EXISTS contacts (
                id                      INTEGER PRIMARY KEY,
                event_id                INTEGER NOT NULL REFERENCES events(id),
                organizer_name          TEXT,
                organizer_email         TEXT,
                email_domain_verified   INTEGER NOT NULL DEFAULT 0,
                source_url              TEXT,
                found_at                TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS mails (
                id              INTEGER PRIMARY KEY,
                event_id        INTEGER NOT NULL REFERENCES events(id),
                draft_path      TEXT,
                language        TEXT,
                variant_label   TEXT,
                generated_at    TEXT NOT NULL,
                mode_version    TEXT
            );

            CREATE TABLE IF NOT EXISTS replies (
                id          INTEGER PRIMARY KEY,
                event_id    INTEGER NOT NULL REFERENCES events(id),
                received_at TEXT NOT NULL,
                snippet     TEXT,
                marked_by   TEXT
            );

            CREATE TABLE IF NOT EXISTS suppression (
                pattern     TEXT PRIMARY KEY,
                reason      TEXT,
                added_at    TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS runs (
                id              INTEGER PRIMARY KEY,
                mode            TEXT NOT NULL,
                started_at      TEXT NOT NULL,
                finished_at     TEXT,
                status          TEXT,
                input_summary   TEXT,
                result_summary  TEXT,
                error           TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_events_status  ON events(status);
            CREATE INDEX IF NOT EXISTS idx_events_score   ON events(score_final);
            CREATE INDEX IF NOT EXISTS idx_events_dedupe  ON events(dedupe_key);

            PRAGMA user_version = 1;
        """)


def _configure(conn: sqlite3.Connection) -> None:
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA synchronous = NORMAL")


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    _configure(conn)
    _apply_migrations(conn)
    return conn


@contextmanager
def db(db_path: Path = DB_PATH) -> Generator[sqlite3.Connection, None, None]:
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
