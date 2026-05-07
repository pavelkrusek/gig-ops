import asyncio
import socket
from pathlib import Path
from typing import Any

import anthropic
from pydantic import BaseModel

from gig_ops.infrastructure.sqlite.repository import SQLiteRepository
from gig_ops.log import logger
from gig_ops.protocol.repository import Repository
from gig_ops.settings import get_settings

_MODE_PATH = Path(__file__).parents[2] / "modes" / "contact.md"
_MODEL = "claude-haiku-4-5"
_MAX_PAGE_CHARS = 16_000
_ELIGIBLE_SCORES = {"A", "B", "C"}


class _ContactResult(BaseModel):
    organizer_name: str | None = None
    organizer_email: str | None = None
    source_note: str | None = None


async def _fetch_page(url: str) -> str:
    from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
    config = CrawlerRunConfig(page_timeout=30000, remove_overlay_elements=True)
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url, config=config)
        if result.success:  # type: ignore[union-attr]
            return result.markdown or ""  # type: ignore[union-attr]
        logger.warning("Crawl4AI failed for {}: {}", url, result.error_message)  # type: ignore[union-attr]
        return ""


def _verify_domain(email: str) -> bool:
    try:
        domain = email.split("@")[-1]
        socket.getaddrinfo(domain, None)
        return True
    except (socket.gaierror, IndexError):
        return False


def _extract_contact(page_text: str, event_name: str, api_key: str) -> _ContactResult:
    client = anthropic.Anthropic(api_key=api_key)
    system_prompt = _MODE_PATH.read_text()
    user_content = (
        f"Event: {event_name}\n\n"
        f"Page content:\n{page_text[:_MAX_PAGE_CHARS]}"
    )
    response = client.messages.parse(
        model=_MODEL,
        max_tokens=512,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
        output_format=_ContactResult,
    )
    if response.parsed_output is None:
        return _ContactResult()
    return response.parsed_output


def find_contact(event_selector: str, repo: Repository | None = None) -> dict[str, Any] | None:
    if repo is None:
        repo = SQLiteRepository()

    event = repo.find_event(event_selector)
    if not event:
        logger.error("Event not found: {}", event_selector)
        return None

    if event.status == "CONTACT_FOUND":
        logger.info("Skipping event {} — contact already found", event.name)
        return {"skipped": True, "reason": "contact already found"}

    if event.score_final not in _ELIGIBLE_SCORES:
        logger.info("Skipping event {} — score {} below C", event.name, event.score_final)
        return {"skipped": True, "reason": f"score {event.score_final} below C"}

    if not event.url:
        logger.warning("No URL for event: {}", event.name)
        return {"skipped": True, "reason": "no URL"}

    api_key = get_settings().anthropic_api_key
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is not set")

    logger.info("Fetching page: {}", event.url)
    page_text = asyncio.run(_fetch_page(event.url))

    if page_text:
        repo.update_crawled_text(event.id, page_text[:_MAX_PAGE_CHARS])
    else:
        logger.warning("No content fetched for {}, falling back to raw_scraped_text", event.url)
        page_text = event.raw_scraped_text or ""

    contact = _extract_contact(page_text, event.name, api_key)
    logger.info("Contact extracted: name={}, email={}", contact.organizer_name, contact.organizer_email)

    email_verified = False
    if contact.organizer_email:
        if repo.is_suppressed(contact.organizer_email):
            logger.info("Email suppressed: {}", contact.organizer_email)
            return {"skipped": True, "reason": "suppressed"}
        email_verified = _verify_domain(contact.organizer_email)

    repo.save_contact(
        event.id,
        organizer_name=contact.organizer_name,
        organizer_email=contact.organizer_email,
        email_domain_verified=email_verified,
        source_url=event.url,
    )

    return {
        "organizer_name": contact.organizer_name,
        "organizer_email": contact.organizer_email,
        "email_domain_verified": email_verified,
        "source_note": contact.source_note,
    }
