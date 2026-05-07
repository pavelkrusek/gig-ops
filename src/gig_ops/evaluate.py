from pathlib import Path
from typing import Any

import anthropic
from pydantic import BaseModel

from gig_ops.infrastructure.sqlite.repository import SQLiteRepository
from gig_ops.log import logger
from gig_ops.protocol.repository import Repository
from gig_ops.settings import get_settings

_MODE_PATH = Path(__file__).parents[2] / "modes" / "evaluate.md"
_MODEL = "claude-haiku-4-5"
_MODE_VERSION = "1.0"


class _DimensionScore(BaseModel):
    score: str
    citation: str | None = None


class _EvaluationResult(BaseModel):
    event_type: _DimensionScore
    audience_size: _DimensionScore
    date: _DimensionScore
    geography: _DimensionScore
    visible_contact_signal: _DimensionScore
    budget_signal: _DimensionScore
    style_fit: _DimensionScore
    competition: _DimensionScore
    score_final: str
    reasoning: str


def evaluate_event(event_name: str, repo: Repository | None = None) -> dict[str, Any] | None:
    if repo is None:
        repo = SQLiteRepository()

    event = repo.get_event_by_name(event_name)
    if not event:
        logger.error("Event not found: {}", event_name)
        return None

    api_key = get_settings().anthropic_api_key
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is not set")

    client = anthropic.Anthropic(api_key=api_key)
    system_prompt = _MODE_PATH.read_text()

    user_content = (
        f"Event name: {event.name}\n"
        f"URL: {event.url or 'unknown'}\n"
        f"Source: {event.source or 'unknown'}\n\n"
        f"Scraped content:\n{event.raw_scraped_text or '(no content available)'}"
    )

    logger.info("Evaluating event: {}", event.name)
    response = client.messages.parse(
        model=_MODEL,
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
        output_format=_EvaluationResult,
    )

    if response.parsed_output is None:
        raise ValueError("Claude returned no structured output")
    result: _EvaluationResult = response.parsed_output
    score_dimensions = {
        "event_type": {"score": result.event_type.score, "citation": result.event_type.citation},
        "audience_size": {"score": result.audience_size.score, "citation": result.audience_size.citation},
        "date": {"score": result.date.score, "citation": result.date.citation},
        "geography": {"score": result.geography.score, "citation": result.geography.citation},
        "visible_contact_signal": {"score": result.visible_contact_signal.score,
                                   "citation": result.visible_contact_signal.citation},
        "budget_signal": {"score": result.budget_signal.score, "citation": result.budget_signal.citation},
        "style_fit": {"score": result.style_fit.score, "citation": result.style_fit.citation},
        "competition": {"score": result.competition.score, "citation": result.competition.citation},
        "reasoning": result.reasoning,
    }

    repo.save_evaluation(
        event.id,
        score_final=result.score_final,
        score_dimensions=score_dimensions,
        mode_version=_MODE_VERSION,
    )

    logger.info("Event {} scored: {}", event.name, result.score_final)
    return {"score_final": result.score_final, "dimensions": score_dimensions}
