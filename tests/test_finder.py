from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from gig_ops.finder import find_contact, _verify_domain
from gig_ops.infrastructure.sqlite.repository import SQLiteRepository


def _make_event(tmp_path: Path, score: str = "A") -> tuple[SQLiteRepository, int]:
    repo = SQLiteRepository(tmp_path / "test.db")
    event_id = repo.add_event(
        name="Odense Food Festival",
        url="https://example.dk/food",
        source="tavily",
        source_confidence="medium",
        raw_scraped_text="Contact: Anders Hansen, anders@odensefood.dk",
    )
    assert event_id is not None
    repo.save_evaluation(
        event_id,
        score_final=score,
        score_dimensions={"reasoning": "Good fit"},
        mode_version="1.0",
    )
    return repo, event_id


def _mock_contact(name: str = "Anders Hansen", email: str = "anders@odensefood.dk") -> MagicMock:
    result = MagicMock()
    result.organizer_name = name
    result.organizer_email = email
    result.source_note = "Found in page footer"
    response = MagicMock()
    response.parsed_output = result
    return response


@patch("gig_ops.finder._fetch_page", new_callable=AsyncMock)
@patch("gig_ops.finder.anthropic.Anthropic")
@patch("gig_ops.finder.get_settings")
@patch("gig_ops.finder._verify_domain", return_value=True)
def test_find_contact_saves_to_db(mock_verify, mock_settings, mock_anthropic, mock_fetch, tmp_path):
    mock_settings.return_value.anthropic_api_key = "test-key"
    mock_fetch.return_value = "Contact: Anders Hansen anders@odensefood.dk"
    mock_anthropic.return_value.messages.parse.return_value = _mock_contact()

    repo, event_id = _make_event(tmp_path)
    result = find_contact(str(event_id), repo=repo)

    assert result is not None
    assert result["organizer_name"] == "Anders Hansen"
    assert result["organizer_email"] == "anders@odensefood.dk"
    assert result["email_domain_verified"] is True

    contact = repo.get_contact(event_id)
    assert contact is not None
    assert contact.organizer_email == "anders@odensefood.dk"
    event = repo.get_event_by_id(event_id)
    assert event is not None
    assert event.status == "CONTACT_FOUND"


@patch("gig_ops.finder._fetch_page", new_callable=AsyncMock)
@patch("gig_ops.finder.anthropic.Anthropic")
@patch("gig_ops.finder.get_settings")
def test_find_contact_skips_low_score(mock_settings, mock_anthropic, mock_fetch, tmp_path):
    mock_settings.return_value.anthropic_api_key = "test-key"
    mock_fetch.return_value = ""

    repo, _ = _make_event(tmp_path, score="D")
    result = find_contact("Odense Food Festival", repo=repo)

    assert result is not None
    assert result.get("skipped") is True
    mock_anthropic.return_value.messages.parse.assert_not_called()


@patch("gig_ops.finder._fetch_page", new_callable=AsyncMock)
@patch("gig_ops.finder.anthropic.Anthropic")
@patch("gig_ops.finder.get_settings")
def test_find_contact_skips_suppressed_email(mock_settings, mock_anthropic, mock_fetch, tmp_path):
    mock_settings.return_value.anthropic_api_key = "test-key"
    mock_fetch.return_value = "Contact page"
    mock_anthropic.return_value.messages.parse.return_value = _mock_contact(email="spam@badactor.dk")

    repo, _ = _make_event(tmp_path)
    repo.add_suppression("badactor.dk")
    result = find_contact("Odense Food Festival", repo=repo)

    assert result is not None
    assert result.get("skipped") is True
    assert result.get("reason") == "suppressed"


def test_verify_domain_valid():
    assert _verify_domain("test@google.com") is True


def test_verify_domain_invalid():
    assert _verify_domain("test@thisdomaindoesnotexist123456789.dk") is False
