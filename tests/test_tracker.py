from pathlib import Path

import pytest

from gig_ops.tracker import (
    add_event,
    add_suppression,
    get_contact,
    get_event_by_id,
    get_event_by_name,
    is_suppressed,
    list_events,
    list_mail_drafts,
    save_contact,
    save_evaluation,
    save_mail_draft,
    set_status,
)


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


def test_add_event_returns_id(tmp_db: Path) -> None:
    event_id = add_event(name="Odense Flower Fest", db_path=tmp_db)
    assert isinstance(event_id, int)


def test_add_event_default_status_is_new(tmp_db: Path) -> None:
    event_id = add_event(name="Test Fest", db_path=tmp_db)
    assert event_id is not None
    event = get_event_by_id(event_id, db_path=tmp_db)
    assert event is not None
    assert event["status"] == "NEW"


def test_add_event_deduplication(tmp_db: Path) -> None:
    id1 = add_event(name="Roskilde Festival", db_path=tmp_db)
    id2 = add_event(name="Roskilde Festival", db_path=tmp_db)
    assert id1 is not None
    assert id2 is None


def test_add_event_suppressed_url(tmp_db: Path) -> None:
    add_suppression("spamfest.dk", db_path=tmp_db)
    event_id = add_event(name="Spam Fest", url="https://spamfest.dk/event", db_path=tmp_db)
    assert event_id is None


def test_get_event_by_name(tmp_db: Path) -> None:
    add_event(name="Aarhus Jazz Fest", db_path=tmp_db)
    event = get_event_by_name("Aarhus Jazz Fest", db_path=tmp_db)
    assert event is not None
    assert event["name"] == "Aarhus Jazz Fest"


def test_get_event_by_name_missing(tmp_db: Path) -> None:
    assert get_event_by_name("Nonexistent", db_path=tmp_db) is None


def test_set_status_valid_transition(tmp_db: Path) -> None:
    event_id = add_event(name="Fest A", db_path=tmp_db)
    assert event_id is not None
    set_status(event_id, "EVALUATED", db_path=tmp_db)
    event = get_event_by_id(event_id, db_path=tmp_db)
    assert event is not None
    assert event["status"] == "EVALUATED"


def test_set_status_invalid_transition(tmp_db: Path) -> None:
    event_id = add_event(name="Fest B", db_path=tmp_db)
    assert event_id is not None
    with pytest.raises(ValueError, match="Invalid transition"):
        set_status(event_id, "SENT", db_path=tmp_db)


def test_set_status_unknown_event(tmp_db: Path) -> None:
    with pytest.raises(ValueError, match="not found"):
        set_status(9999, "EVALUATED", db_path=tmp_db)


def test_save_evaluation_good_score(tmp_db: Path) -> None:
    event_id = add_event(name="Fest C", db_path=tmp_db)
    assert event_id is not None
    save_evaluation(
        event_id,
        score_final="B",
        score_dimensions={"event_type": "A", "audience_size": "B"},
        mode_version="1.0",
        db_path=tmp_db,
    )
    event = get_event_by_id(event_id, db_path=tmp_db)
    assert event is not None
    assert event["status"] == "EVALUATED"
    assert event["score_final"] == "B"


def test_save_evaluation_bad_score_drops(tmp_db: Path) -> None:
    event_id = add_event(name="Fest D", db_path=tmp_db)
    assert event_id is not None
    save_evaluation(
        event_id,
        score_final="F",
        score_dimensions={},
        mode_version="1.0",
        db_path=tmp_db,
    )
    event = get_event_by_id(event_id, db_path=tmp_db)
    assert event is not None
    assert event["status"] == "DROPPED"


def test_save_contact(tmp_db: Path) -> None:
    event_id = add_event(name="Fest E", db_path=tmp_db)
    assert event_id is not None
    set_status(event_id, "EVALUATED", db_path=tmp_db)
    save_contact(
        event_id,
        organizer_name="Jana Novak",
        organizer_email="jana@example.dk",
        email_domain_verified=True,
        source_url="https://example.dk/contact",
        db_path=tmp_db,
    )
    event = get_event_by_id(event_id, db_path=tmp_db)
    assert event is not None
    assert event["status"] == "CONTACT_FOUND"
    contact = get_contact(event_id, db_path=tmp_db)
    assert contact is not None
    assert contact["organizer_email"] == "jana@example.dk"


def test_save_contact_suppressed_email(tmp_db: Path) -> None:
    event_id = add_event(name="Fest F", db_path=tmp_db)
    assert event_id is not None
    set_status(event_id, "EVALUATED", db_path=tmp_db)
    add_suppression("blocked@example.dk", db_path=tmp_db)
    save_contact(
        event_id,
        organizer_name="Blocked Person",
        organizer_email="blocked@example.dk",
        email_domain_verified=True,
        source_url=None,
        db_path=tmp_db,
    )
    contact = get_contact(event_id, db_path=tmp_db)
    assert contact is None


def test_save_mail_draft(tmp_db: Path) -> None:
    event_id = add_event(name="Fest G", db_path=tmp_db)
    assert event_id is not None
    set_status(event_id, "EVALUATED", db_path=tmp_db)
    save_contact(
        event_id,
        organizer_name="Ole",
        organizer_email="ole@fest.dk",
        email_domain_verified=True,
        source_url=None,
        db_path=tmp_db,
    )
    save_mail_draft(
        event_id,
        draft_path="data/mails/fest-g-A.md",
        language="da",
        variant_label="A",
        mode_version="1.0",
        db_path=tmp_db,
    )
    drafts = list_mail_drafts(event_id, db_path=tmp_db)
    assert len(drafts) == 1
    assert drafts[0]["variant_label"] == "A"
    event = get_event_by_id(event_id, db_path=tmp_db)
    assert event is not None
    assert event["status"] == "MAIL_DRAFTED"


def test_list_events_filter_by_status(tmp_db: Path) -> None:
    add_event(name="Fest H", db_path=tmp_db)
    add_event(name="Fest I", db_path=tmp_db)
    results = list_events(status="NEW", db_path=tmp_db)
    assert len(results) == 2
    assert all(e["status"] == "NEW" for e in results)


def test_is_suppressed_email(tmp_db: Path) -> None:
    add_suppression("nope@spam.dk", db_path=tmp_db)
    assert is_suppressed("nope@spam.dk", db_path=tmp_db)
    assert not is_suppressed("ok@legit.dk", db_path=tmp_db)


def test_is_suppressed_domain(tmp_db: Path) -> None:
    add_suppression("spam.dk", db_path=tmp_db)
    assert is_suppressed("anyone@spam.dk", db_path=tmp_db)
