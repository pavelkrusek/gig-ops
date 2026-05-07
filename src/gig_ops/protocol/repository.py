from typing import Any, Protocol

from gig_ops.domain.models import Contact, Event, MailDraft


class Repository(Protocol):
    def add_event(
        self,
        *,
        name: str,
        url: str | None = None,
        source: str | None = None,
        source_confidence: str | None = None,
        raw_scraped_text: str | None = None,
    ) -> int | None: ...

    def set_status(self, event_id: int, new_status: str) -> None: ...

    def save_evaluation(
        self,
        event_id: int,
        *,
        score_final: str,
        score_dimensions: dict[str, Any],
        mode_version: str,
    ) -> None: ...

    def save_contact(
        self,
        event_id: int,
        *,
        organizer_name: str | None,
        organizer_email: str | None,
        email_domain_verified: bool,
        source_url: str | None,
    ) -> None: ...

    def save_mail_draft(
        self,
        event_id: int,
        *,
        draft_path: str,
        language: str,
        variant_label: str,
        mode_version: str,
    ) -> None: ...

    def add_suppression(self, pattern: str, reason: str | None = None) -> None: ...

    def get_event_by_id(self, event_id: int) -> Event | None: ...

    def get_event_by_name(self, name: str) -> Event | None: ...

    def find_event(self, query: str) -> Event | None: ...

    def list_events(self, status: str | None = None) -> list[Event]: ...

    def get_contact(self, event_id: int) -> Contact | None: ...

    def list_mail_drafts(self, event_id: int) -> list[MailDraft]: ...

    def is_suppressed(self, pattern: str) -> bool: ...
