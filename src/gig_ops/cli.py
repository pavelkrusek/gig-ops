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
def evaluate(event_name: str = typer.Argument(..., help="Event name to evaluate")) -> None:
    """Score an event A–F."""
    logger.info("Evaluating: {}", event_name)
    typer.echo(f"Evaluating: {event_name} — not yet implemented")


@app.command()
def contact(event_name: str = typer.Argument(..., help="Event name to look up organizer for")) -> None:
    """Find organizer contact for an event (only if score ≥ C)."""
    logger.info("Finding contact for: {}", event_name)
    typer.echo(f"Finding contact for: {event_name} — not yet implemented")


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
