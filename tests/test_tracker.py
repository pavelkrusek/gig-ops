from pathlib import Path

import pytest

from gig_ops.infrastructure.sqlite.repository import SQLiteRepository


@pytest.fixture
def repo(tmp_path: Path) -> SQLiteRepository:
    return SQLiteRepository(tmp_path / "test.db")


def test_add_event_returns_id(repo: SQLiteRepository) -> None:
    event_id = repo.add_event(name="Odense Flower Fest")
    assert isinstance(event_id, int)


def test_add_event_default_status_is_new(repo: SQLiteRepository) -> None:
    event_id = repo.add_event(name="Test Fest")
    assert event_id is not None
    event = repo.get_event_by_id(event_id)
    assert event is not None
    assert event.status == "NEW"


def test_add_event_deduplication(repo: SQLiteRepository) -> None:
    id1 = repo.add_event(name="Roskilde Festival")
    id2 = repo.add_event(name="Roskilde Festival")
    assert id1 is not None
    assert id2 is None


def test_add_event_suppressed_url(repo: SQLiteRepository) -> None:
    repo.add_suppression("spamfest.dk")
    event_id = repo.add_event(name="Spam Fest", url="https://spamfest.dk/event")
    assert event_id is None


def test_get_event_by_name(repo: SQLiteRepository) -> None:
    repo.add_event(name="Aarhus Jazz Fest")
    event = repo.get_event_by_name("Aarhus Jazz Fest")
    assert event is not None
    assert event.name == "Aarhus Jazz Fest"


def test_get_event_by_name_missing(repo: SQLiteRepository) -> None:
    assert repo.get_event_by_name("Nonexistent") is None


def test_set_status_valid_transition(repo: SQLiteRepository) -> None:
    event_id = repo.add_event(name="Fest A")
    assert event_id is not None
    repo.set_status(event_id, "EVALUATED")
    event = repo.get_event_by_id(event_id)
    assert event is not None
    assert event.status == "EVALUATED"


def test_set_status_invalid_transition(repo: SQLiteRepository) -> None:
    event_id = repo.add_event(name="Fest B")
    assert event_id is not None
    with pytest.raises(ValueError, match="Invalid transition"):
        repo.set_status(event_id, "SENT")


def test_set_status_unknown_event(repo: SQLiteRepository) -> None:
    with pytest.raises(ValueError, match="not found"):
        repo.set_status(9999, "EVALUATED")


def test_save_evaluation_good_score(repo: SQLiteRepository) -> None:
    event_id = repo.add_event(name="Fest C")
    assert event_id is not None
    repo.save_evaluation(
        event_id,
        score_final="B",
        score_dimensions={"event_type": "A", "audience_size": "B"},
        mode_version="1.0",
    )
    event = repo.get_event_by_id(event_id)
    assert event is not None
    assert event.status == "EVALUATED"
    assert event.score_final == "B"
    assert event.score_dimensions["event_type"] == "A"


def test_save_evaluation_bad_score_drops(repo: SQLiteRepository) -> None:
    event_id = repo.add_event(name="Fest D")
    assert event_id is not None
    repo.save_evaluation(event_id, score_final="F", score_dimensions={}, mode_version="1.0")
    event = repo.get_event_by_id(event_id)
    assert event is not None
    assert event.status == "DROPPED"


def test_save_contact(repo: SQLiteRepository) -> None:
    event_id = repo.add_event(name="Fest E")
    assert event_id is not None
    repo.set_status(event_id, "EVALUATED")
    repo.save_contact(
        event_id,
        organizer_name="Jana Novak",
        organizer_email="jana@example.dk",
        email_domain_verified=True,
        source_url="https://example.dk/contact",
    )
    event = repo.get_event_by_id(event_id)
    assert event is not None
    assert event.status == "CONTACT_FOUND"
    contact = repo.get_contact(event_id)
    assert contact is not None
    assert contact.organizer_email == "jana@example.dk"
    assert contact.email_domain_verified is True


def test_save_contact_suppressed_email(repo: SQLiteRepository) -> None:
    event_id = repo.add_event(name="Fest F")
    assert event_id is not None
    repo.set_status(event_id, "EVALUATED")
    repo.add_suppression("blocked@example.dk")
    repo.save_contact(
        event_id,
        organizer_name="Blocked Person",
        organizer_email="blocked@example.dk",
        email_domain_verified=True,
        source_url=None,
    )
    assert repo.get_contact(event_id) is None


def test_save_mail_draft(repo: SQLiteRepository) -> None:
    event_id = repo.add_event(name="Fest G")
    assert event_id is not None
    repo.set_status(event_id, "EVALUATED")
    repo.save_contact(event_id, organizer_name="Ole", organizer_email="ole@fest.dk",
                      email_domain_verified=True, source_url=None)
    repo.save_mail_draft(event_id, draft_path="data/mails/fest-g-A.md",
                         language="da", variant_label="A", mode_version="1.0")
    drafts = repo.list_mail_drafts(event_id)
    assert len(drafts) == 1
    assert drafts[0].variant_label == "A"
    event = repo.get_event_by_id(event_id)
    assert event is not None
    assert event.status == "MAIL_DRAFTED"


def test_list_events_filter_by_status(repo: SQLiteRepository) -> None:
    repo.add_event(name="Fest H")
    repo.add_event(name="Fest I")
    results = repo.list_events(status="NEW")
    assert len(results) == 2
    assert all(e.status == "NEW" for e in results)


def test_is_suppressed_email(repo: SQLiteRepository) -> None:
    repo.add_suppression("nope@spam.dk")
    assert repo.is_suppressed("nope@spam.dk")
    assert not repo.is_suppressed("ok@legit.dk")


def test_is_suppressed_domain(repo: SQLiteRepository) -> None:
    repo.add_suppression("spam.dk")
    assert repo.is_suppressed("anyone@spam.dk")
