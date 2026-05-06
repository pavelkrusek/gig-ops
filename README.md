# gig-ops

AI-powered gig pipeline for a caricature artist. Scans Danish festivals and events, scores their fit, finds the right
contact, and drafts a personalized outreach email. Dagmar reviews and sends — the system never sends automatically.

---

## Pipeline

```
scan → evaluate (A–F) → [drop if < C] → find contact → draft email → tracker
```

Evaluation runs before contact lookup, so low-scoring events are dropped before spending API calls on them.

---

## Setup

```bash
cp .env.example .env   # fill in keys
uv sync
```

**.env**

```
ANTHROPIC_API_KEY=      # required
TAVILY_API_KEY=         # required for scan
PERPLEXITY_API_KEY=     # optional — deep research mode
```

---

## Usage

```bash
uv run gig-ops scan                          # scan all sources for new events
uv run gig-ops scan --source tavily          # specific source only
uv run gig-ops evaluate "Odense Flower Fest" # score an event A–F
uv run gig-ops contact "Odense Flower Fest"  # find organizer (score ≥ C only)
uv run gig-ops mail "Odense Flower Fest"     # generate 2–3 email variants
uv run gig-ops followup                      # list events needing follow-up
uv run gig-ops tracker                       # open TUI dashboard
uv run gig-ops deep "Roskilde Festival"      # deep research mode
uv run gig-ops suppress contact@example.dk  # add to do-not-contact list
```

---

## Data

SQLite database at `data/events.db`. Mail drafts as Markdown in `data/mails/`.
Both are gitignored — Dagmar's data stays local.

Daily backup: `cp data/events.db data/backups/events-$(date +%Y%m%d).db`

---

## Development

```bash
make check   # lint (ruff) + types (pyright) + tests (pytest)
```

Requires Python 3.12+ and [uv](https://github.com/astral-sh/uv).
