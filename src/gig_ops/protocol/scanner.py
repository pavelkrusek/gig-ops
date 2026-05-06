from typing import Protocol

from gig_ops.domain.models import ScanResult


class Scanner(Protocol):
    def scan(self, query: str) -> list[ScanResult]: ...
