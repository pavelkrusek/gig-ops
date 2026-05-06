import sqlite3
from pathlib import Path

import pytest

from gig_ops.db import SCHEMA_VERSION, db, get_connection


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


def test_creates_database(tmp_db: Path) -> None:
    with db(tmp_db):
        pass
    assert tmp_db.exists()


def test_schema_version(tmp_db: Path) -> None:
    conn = get_connection(tmp_db)
    version: int = conn.execute("PRAGMA user_version").fetchone()[0]
    conn.close()
    assert version == SCHEMA_VERSION


def test_wal_mode(tmp_db: Path) -> None:
    conn = get_connection(tmp_db)
    journal_mode: str = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()
    assert journal_mode == "wal"


def test_foreign_keys_on(tmp_db: Path) -> None:
    conn = get_connection(tmp_db)
    fk: int = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    conn.close()
    assert fk == 1


def test_all_tables_exist(tmp_db: Path) -> None:
    expected = {"events", "contacts", "mails", "replies", "suppression", "runs"}
    conn = get_connection(tmp_db)
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    conn.close()
    actual = {row[0] for row in rows}
    assert expected <= actual


def test_migrations_are_idempotent(tmp_db: Path) -> None:
    get_connection(tmp_db).close()
    get_connection(tmp_db).close()  # second open should not raise


def test_foreign_key_constraint_enforced(tmp_db: Path) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        with db(tmp_db) as conn:
            conn.execute(
                "INSERT INTO contacts (event_id, found_at) VALUES (?, ?)",
                (9999, "2026-01-01T00:00:00"),
            )


def test_suppression_pattern_unique(tmp_db: Path) -> None:
    with db(tmp_db) as conn:
        conn.execute(
            "INSERT INTO suppression (pattern, added_at) VALUES (?, ?)",
            ("example.dk", "2026-01-01T00:00:00"),
        )
    with pytest.raises(sqlite3.IntegrityError):
        with db(tmp_db) as conn:
            conn.execute(
                "INSERT INTO suppression (pattern, added_at) VALUES (?, ?)",
                ("example.dk", "2026-01-02T00:00:00"),
            )


def test_context_manager_rollback_on_error(tmp_db: Path) -> None:
    with pytest.raises(ValueError):
        with db(tmp_db) as conn:
            conn.execute(
                "INSERT INTO suppression (pattern, added_at) VALUES (?, ?)",
                ("rollback-test.dk", "2026-01-01T00:00:00"),
            )
            raise ValueError("simulated error")

    with db(tmp_db) as conn:
        row = conn.execute(
            "SELECT 1 FROM suppression WHERE pattern = ?", ("rollback-test.dk",)
        ).fetchone()
    assert row is None
