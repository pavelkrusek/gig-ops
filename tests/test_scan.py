from gig_ops.domain.models import ScanResult
from gig_ops.infrastructure.sqlite.repository import SQLiteRepository
from gig_ops.scan import run_scan

_Q = ["test query"]


class _FakeScanner:
    def __init__(self, results: list[ScanResult]) -> None:
        self._results = results
        self.queries: list[str] = []

    def scan(self, query: str) -> list[ScanResult]:
        self.queries.append(query)
        return self._results


def test_scan_adds_new_events(tmp_path):
    repo = SQLiteRepository(tmp_path / "test.db")
    scanner = _FakeScanner([
        ScanResult(name="Odense Food Festival", url="https://example.dk/food", source="tavily", source_confidence="medium"),
        ScanResult(name="Fyn Rock Festival", url="https://example.dk/rock", source="tavily", source_confidence="medium"),
    ])

    summary = run_scan(source="tavily", repo=repo, scanner=scanner, queries=_Q)

    assert summary.added == 2
    assert len(repo.list_events()) == 2


def test_scan_deduplicates(tmp_path):
    repo = SQLiteRepository(tmp_path / "test.db")
    result = ScanResult(name="Odense Food Festival", url="https://example.dk/food", source="tavily", source_confidence="medium")
    scanner = _FakeScanner([result])

    run_scan(source="tavily", repo=repo, scanner=scanner, queries=_Q)
    summary = run_scan(source="tavily", repo=repo, scanner=scanner, queries=_Q)

    assert summary.skipped > 0
    assert len(repo.list_events()) == 1


def test_scan_skips_suppressed_url(tmp_path):
    repo = SQLiteRepository(tmp_path / "test.db")
    repo.add_suppression("example.dk")
    scanner = _FakeScanner([
        ScanResult(name="Odense Food Festival", url="https://example.dk/food", source="tavily", source_confidence="medium"),
    ])

    summary = run_scan(source="tavily", repo=repo, scanner=scanner, queries=_Q)

    assert summary.added == 0
    assert len(repo.list_events()) == 0


def test_scan_stores_raw_text(tmp_path):
    repo = SQLiteRepository(tmp_path / "test.db")
    scanner = _FakeScanner([
        ScanResult(name="Odense Food Festival", url="https://example.dk/food",
                   source="tavily", source_confidence="medium", raw_text="Great festival in Odense"),
    ])

    run_scan(source="tavily", repo=repo, scanner=scanner, queries=_Q)

    event = repo.list_events()[0]
    assert event.raw_scraped_text == "Great festival in Odense"


def test_scan_handles_scanner_error(tmp_path):
    repo = SQLiteRepository(tmp_path / "test.db")

    class _ErrorScanner:
        def scan(self, query: str) -> list[ScanResult]:  # noqa: ARG002
            raise RuntimeError("API down")

    summary = run_scan(source="tavily", repo=repo, scanner=_ErrorScanner(), queries=_Q)

    assert summary.added == 0
    assert len(summary.errors) > 0
