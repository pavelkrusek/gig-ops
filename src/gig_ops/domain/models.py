from dataclasses import dataclass, field
from typing import Any


@dataclass
class Event:
    id: int
    name: str
    status: str
    url: str | None = None
    date: str | None = None
    location: str | None = None
    type: str | None = None
    score_final: str | None = None
    score_dimensions: dict[str, Any] = field(default_factory=dict)
    raw_scraped_text: str | None = None
    source: str | None = None
    source_confidence: str | None = None
    dedupe_key: str | None = None
    possible_duplicate_of: int | None = None
    needs_review: bool = False
    review_reason: str | None = None
    found_at: str = ""
    updated_at: str = ""
    mode_versions: dict[str, str] = field(default_factory=dict)


@dataclass
class Contact:
    id: int
    event_id: int
    found_at: str
    organizer_name: str | None = None
    organizer_email: str | None = None
    email_domain_verified: bool = False
    source_url: str | None = None


@dataclass
class MailDraft:
    id: int
    event_id: int
    generated_at: str
    draft_path: str | None = None
    language: str | None = None
    variant_label: str | None = None
    mode_version: str | None = None


@dataclass
class ScanResult:
    name: str
    url: str | None = None
    source: str | None = None
    source_confidence: str | None = None
    raw_text: str | None = None
