from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gig_ops.evaluate import evaluate_event
from gig_ops.infrastructure.sqlite.repository import SQLiteRepository


def _make_event(tmp_path: Path) -> tuple[SQLiteRepository, int]:
    repo = SQLiteRepository(tmp_path / "test.db")
    event_id = repo.add_event(
        name="Odense Food Festival",
        url="https://example.dk/food",
        source="tavily",
        source_confidence="medium",
        raw_scraped_text="Annual food festival in Odense city centre. 5000 visitors expected. Contact: info@foodfest.dk. Date: August 2026.",
    )
    assert event_id is not None
    return repo, event_id


def _mock_response(score_final: str = "B") -> MagicMock:
    dim = MagicMock()
    dim.score = "B"
    dim.citation = "5000 visitors expected"

    result = MagicMock()
    result.event_type = dim
    result.audience_size = dim
    result.date = dim
    result.geography = dim
    result.visible_contact_signal = dim
    result.budget_signal = dim
    result.style_fit = dim
    result.competition = dim
    result.score_final = score_final
    result.reasoning = "Good fit overall."

    response = MagicMock()
    response.parsed_output = result
    return response


@patch("gig_ops.evaluate.anthropic.Anthropic")
@patch("gig_ops.evaluate.get_settings")
def test_evaluate_scores_event(mock_settings, mock_anthropic, tmp_path):
    mock_settings.return_value.anthropic_api_key = "test-key"
    mock_anthropic.return_value.messages.parse.return_value = _mock_response("B")

    repo, _ = _make_event(tmp_path)
    result = evaluate_event("Odense Food Festival", repo=repo)

    assert result is not None
    assert result["score_final"] == "B"
    event = repo.get_event_by_name("Odense Food Festival")
    assert event is not None
    assert event.score_final == "B"
    assert event.status == "EVALUATED"


@patch("gig_ops.evaluate.anthropic.Anthropic")
@patch("gig_ops.evaluate.get_settings")
def test_evaluate_drops_low_score(mock_settings, mock_anthropic, tmp_path):
    mock_settings.return_value.anthropic_api_key = "test-key"
    mock_anthropic.return_value.messages.parse.return_value = _mock_response("F")

    repo, _ = _make_event(tmp_path)
    evaluate_event("Odense Food Festival", repo=repo)

    event = repo.get_event_by_name("Odense Food Festival")
    assert event is not None
    assert event.status == "DROPPED"


def test_evaluate_returns_none_for_unknown_event(tmp_path):
    repo = SQLiteRepository(tmp_path / "test.db")
    result = evaluate_event("Nonexistent Event", repo=repo)
    assert result is None


@patch("gig_ops.evaluate.get_settings")
def test_evaluate_raises_without_api_key(mock_settings, tmp_path):
    mock_settings.return_value.anthropic_api_key = None
    repo, _ = _make_event(tmp_path)
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        evaluate_event("Odense Food Festival", repo=repo)
