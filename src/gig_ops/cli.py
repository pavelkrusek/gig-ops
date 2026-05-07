import sys
from typing import Optional

import typer

from gig_ops.log import logger

app = typer.Typer(name="gig-ops", help="AI-powered gig search for Dagmar.")


@app.callback()
def configure(
        verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
        log_file: Optional[str] = typer.Option(None, "--log-file", help="Also write logs to this file"),
) -> None:
    logger.remove()
    level = "DEBUG" if verbose else "INFO"
    logger.add(sys.stderr, level=level)
    if log_file:
        logger.add(log_file, level="DEBUG", rotation="10 MB", retention="30 days")


@app.command()
def scan(source: str = typer.Option("tavily", help="Source to scan: tavily | all")) -> None:
    """Scan sources for new events."""
    from gig_ops.scan import run_scan
    typer.echo(f"Scanning [{source}]…")
    summary = run_scan(source=source)
    typer.echo(f"Done. Added: {summary.added}, skipped (dup/suppressed): {summary.skipped}")
    if summary.errors:
        for e in summary.errors:
            typer.echo(f"  Error: {e}", err=True)


@app.command()
def evaluate(
    event_name: Optional[str] = typer.Argument(None, help="Event name (omit to evaluate all NEW events)"),
) -> None:
    """Score an event A–F. Without argument, evaluates all NEW events."""
    from gig_ops.evaluate import evaluate_event
    from gig_ops.infrastructure.sqlite.repository import SQLiteRepository

    repo = SQLiteRepository()

    if event_name:
        found = repo.find_event(event_name)
        if not found:
            typer.echo(f"No event matching '{event_name}'.", err=True)
            raise typer.Exit(1)
        events = [found]
    else:
        events = repo.list_events(status="NEW")
        if not events:
            typer.echo("No NEW events to evaluate.")
            return
        typer.echo(f"Evaluating {len(events)} NEW events…")

    ok = skipped = 0
    for event in events:
        if event is None:
            continue
        typer.echo(f"  {event.name[:60]}…", nl=False)
        result = evaluate_event(event.name, repo=repo)
        if result:
            reasoning = result["dimensions"].get("reasoning", "")
            typer.echo(f" {result['score_final']} — {reasoning}")
            if event_name:
                for dim, data in result["dimensions"].items():
                    if dim == "reasoning":
                        continue
                    score = data.get("score", "?") if isinstance(data, dict) else data
                    citation = data.get("citation") if isinstance(data, dict) else None
                    line = f"    {dim}: {score}"
                    if citation:
                        line += f"  ({citation[:80]})"
                    typer.echo(line)
            ok += 1
        else:
            typer.echo(" error")
            skipped += 1

    if not event_name:
        typer.echo(f"Done. Scored: {ok}, errors: {skipped}")


@app.command(name="list")
def list_events(
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status (NEW, EVALUATED, …)"),
) -> None:
    """List events in the database."""
    from gig_ops.infrastructure.sqlite.repository import SQLiteRepository
    from rich.table import Table
    from rich.console import Console

    repo = SQLiteRepository()
    events = repo.list_events(status=status)
    if not events:
        typer.echo("No events found.")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("ID", width=5)
    table.add_column("Score", width=5)
    table.add_column("Status", width=14)
    table.add_column("Name", no_wrap=False)
    table.add_column("Source", width=8)

    for e in events:
        table.add_row(str(e.id), e.score_final or "—", e.status, e.name, e.source or "")

    Console().print(table)
    typer.echo(f"Total: {len(events)}")


@app.command()
def contact(
    event_name: Optional[str] = typer.Argument(None, help="Event name or ID (omit to process all A/B/C events)"),
) -> None:
    """Find organizer contact. Without argument, processes all scored A/B/C events."""
    from gig_ops.finder import find_contact, _ELIGIBLE_SCORES
    from gig_ops.infrastructure.sqlite.repository import SQLiteRepository

    repo = SQLiteRepository()

    if event_name:
        events_to_process = []
        found = repo.find_event(event_name)
        if not found:
            typer.echo(f"No event matching '{event_name}'.", err=True)
            raise typer.Exit(1)
        events_to_process = [found]
    else:
        all_evaluated = repo.list_events(status="EVALUATED")
        events_to_process = [e for e in all_evaluated if e.score_final in _ELIGIBLE_SCORES]
        if not events_to_process:
            typer.echo("No eligible events (A/B/C) to process.")
            return
        typer.echo(f"Finding contacts for {len(events_to_process)} events…")

    ok = skipped = errors = 0
    for event in events_to_process:
        typer.echo(f"  [{event.score_final}] {event.name[:55]}…", nl=False)
        result = find_contact(str(event.id), repo=repo)
        if result is None:
            typer.echo(" not found")
            errors += 1
        elif result.get("skipped"):
            typer.echo(f" skipped ({result.get('reason', '')})")
            skipped += 1
        else:
            name = result.get("organizer_name") or "—"
            email = result.get("organizer_email") or "—"
            verified = "✓" if result.get("email_domain_verified") else "?"
            typer.echo(f" {name} <{email}> {verified}")
            ok += 1

    if not event_name:
        typer.echo(f"Done. Found: {ok}, skipped: {skipped}, errors: {errors}")


@app.command()
def mail(event_name: str = typer.Argument(..., help="Event name to generate outreach email for")) -> None:
    """Generate outreach email draft(s) for an event."""
    logger.info("Generating mail for: {}", event_name)
    typer.echo(f"Generating mail for: {event_name} — not yet implemented")


@app.command()
def followup() -> None:
    """Check which events need a follow-up."""
    logger.info("Running follow-up check")
    typer.echo("Follow-up check — not yet implemented")


@app.command()
def tracker() -> None:
    """Open the Textual TUI dashboard."""
    logger.info("Starting dashboard")
    typer.echo("Dashboard — not yet implemented")


@app.command()
def deep(event_name: str = typer.Argument(..., help="Event or organizer to research")) -> None:
    """Deep research mode for a specific event or organizer."""
    logger.info("Deep research: {}", event_name)
    typer.echo(f"Deep research: {event_name} — not yet implemented")


@app.command()
def suppress(
        pattern: str = typer.Argument(..., help="Email or domain to suppress"),
        reason: str = typer.Option("", "--reason", "-r", help="Optional reason"),
) -> None:
    """Add an email or domain to the do-not-contact list."""
    from gig_ops.infrastructure.sqlite.repository import SQLiteRepository
    SQLiteRepository().add_suppression(pattern, reason or None)
    typer.echo(f"Suppressed: {pattern}")
