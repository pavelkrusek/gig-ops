from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import yaml

from gig_ops.infrastructure.scanner.tavily import TavilyScanner
from gig_ops.infrastructure.sqlite.repository import SQLiteRepository
from gig_ops.log import logger
from gig_ops.protocol.repository import Repository
from gig_ops.protocol.scanner import Scanner

_QUERIES_PATH = Path(__file__).parents[2] / "queries.yml"


def _build_queries(path: Path = _QUERIES_PATH) -> list[str]:
    year = datetime.now().year
    raw: list[str] = yaml.safe_load(path.read_text())["tavily"]
    return [q.format(year=year, next_year=year + 1) for q in raw]


@dataclass
class ScanSummary:
    added: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


def run_scan(
    source: str = "tavily",
    repo: Repository | None = None,
    scanner: Scanner | None = None,
    queries: list[str] | None = None,
) -> ScanSummary:
    if repo is None:
        repo = SQLiteRepository()

    summary = ScanSummary()

    if source in ("tavily", "all"):
        _scan_with(scanner or TavilyScanner(), queries if queries is not None else _build_queries(), repo, summary)

    logger.info("Scan done — added: {}, skipped: {}", summary.added, summary.skipped)
    return summary


def _scan_with(scanner: Scanner, queries: list[str], repo: Repository, summary: ScanSummary) -> None:
    for query in queries:
        try:
            results = scanner.scan(query)
            for r in results:
                event_id = repo.add_event(
                    name=r.name,
                    url=r.url,
                    source=r.source,
                    source_confidence=r.source_confidence,
                    raw_scraped_text=r.raw_text,
                )
                if event_id is not None:
                    summary.added += 1
                else:
                    summary.skipped += 1
        except Exception as exc:
            logger.error("Query failed '{}': {}", query, exc)
            summary.errors.append(f"{query}: {exc}")
