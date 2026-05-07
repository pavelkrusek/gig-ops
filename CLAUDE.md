# gig-ops

AI-powered gig search system for a caricature artist. Finds festivals, conferences, and events in Denmark, locates the
right contact person, and generates personalized outreach emails.

Built on Claude Code with a Python-first stack. Inspired by the career-ops architecture.

**This is a single-user tool for Dagmar.** Not a product, not multi-tenant, no scale concerns. Architectural decisions
reflect that.

---

## What This Does

Dagmar is a caricature artist based in Odense, Denmark. She offers:

- **Live caricatures** at events, festivals, corporate parties, weddings
- **Studio portraits** (pastel, charcoal)
- **Animal portraits**

Her website: https://dagmarstudio.dk

She currently finds gigs manually — browsing festival websites and event listings, then writing outreach emails herself.
gig-ops automates this pipeline.

---

## Pipeline

```
URL / event name / search query
        ↓
Event Scanner       ← finds festivals, conferences, events in Denmark
        ↓
Fit Evaluation      ← scores the event A–F (cheap, runs on scan metadata only)
        ↓
   if score < C → DROPPED (no further work)
        ↓
Contact Finder      ← locates organizer name + email (only for events ≥ C)
        ↓
Mail Generator      ← writes a personalized outreach email (DK or EN)
        ↓
Outreach Tracker    ← records everything in events.db
```

**Pipeline order matters.** Evaluation runs *before* contact lookup, so events scored D/F are dropped before spending
Crawl4AI/Tavily calls on finding their organizer. This typically cuts contact-lookup work by 50–70%.

**Human-in-the-loop is intentional.** gig-ops never sends emails automatically. Dagmar always reviews and sends herself.

---

## Tech Stack

| Layer        | Technology                                                 |
|--------------|------------------------------------------------------------|
| Language     | Python 3.12+ (src layout, uv package manager)              |
| CLI          | Typer                                                      |
| Terminal UI  | Textual (dashboard)                                        |
| Web scraping | Crawl4AI (handles JS, dynamic content)                     |
| AI           | Anthropic SDK (claude-sonnet-4-5 or latest)                |
| Search       | Tavily API (primary), Perplexity (deep research mode)      |
| Config       | PyYAML                                                     |
| Data         | SQLite (events.db) + Markdown (mail drafts)                |
| Search index | SQLite FTS5 (built-in, for keyword search over event text) |

**No Go. No Node.js.** Everything is Python.

### Why SQLite, not Postgres

Single-user, single-writer, no network access. Postgres would be operational overhead solving problems we don't have.
SQLite with WAL mode handles concurrent dashboard reads + scanner writes fine. Backup is `cp events.db backup/`. If the
project ever needs Postgres (multi-user web app), the SQL is portable enough that migration is an afternoon, not a
rewrite.

### Why no vector database

Scale is too small (hundreds of events), queries are mostly structured, and SQLite FTS5 covers keyword search at zero
added complexity. Revisit only when there's a real RAG use case (e.g. retrieval over past successful emails after 20+
bookings). At that point, `sqlite-vec` extension keeps everything in one database — no second storage layer needed.

---

## Project Structure

```
gig-ops/
├── CLAUDE.md                        # you are here
├── GEMINI.md                        # Gemini CLI equivalent (optional)
├── profile.yml                      # Dagmar's profile (style, prices, zone, languages)
├── pitch.md                         # her "CV" — bio, services, references, proof points
├── portals.yml                      # list of websites/sources to scan regularly
├── suppression.yml                  # do-not-contact list (organizers + domains)
│
├── modes/                           # prompt instruction files (one per operation)
│   ├── _shared.md                   # shared context loaded by all modes
│   ├── scan.md                      # find events
│   ├── evaluate.md                  # score event fit (A–F, multi-dimensional)
│   ├── contact.md                   # find organizer contact
│   ├── mail.md                      # generate outreach email (with grounding rules)
│   ├── followup.md                  # follow-up after N days
│   └── deep.md                      # deep research on a specific event/organizer
│
├── src/
│   └── gig_ops/
│       ├── __init__.py
│       ├── cli.py                   # Typer CLI entry point
│       ├── db.py                    # SQLite connection, migrations, schema
│       ├── scanner/
│       │   ├── __init__.py
│       │   ├── tavily.py            # Tavily search (festivals, events)
│       │   ├── crawl4ai.py          # Crawl4AI scraper (Eventbrite, custom sites)
│       │   └── portals.py           # scrape sites listed in portals.yml
│       ├── evaluator.py             # AI scoring via Claude API (multi-dim)
│       ├── finder.py                # contact finder (name + email + verification)
│       ├── mailer.py                # mail draft generator (grounded)
│       ├── tracker.py               # SQLite read/write, dedup, status state machine
│       └── dashboard.py             # Textual TUI
│
├── .claude/
│   └── commands/                    # slash commands for Claude Code (wrap CLI)
│       ├── gig-ops.md
│       ├── gig-ops-scan.md
│       ├── gig-ops-mail.md
│       ├── gig-ops-evaluate.md
│       ├── gig-ops-contact.md
│       ├── gig-ops-tracker.md
│       └── gig-ops-deep.md
│
├── templates/
│   ├── mail_dk.md                   # outreach email template (Danish)
│   └── mail_en.md                   # outreach email template (English)
│
├── data/                            # gitignored — Dagmar's data
│   ├── events.db                    # SQLite database (master tracker)
│   ├── backups/                     # daily db copies
│   └── mails/                       # generated email drafts (one .md per event)
│
├── examples/                        # sample files to guide the AI
│   ├── example-event.md
│   └── example-mail.md
│
├── tests/                           # pytest suite (incl. evaluator eval set)
│
├── pyproject.toml
├── .env.example
└── .gitignore
```

**Slash commands wrap CLI, not duplicate logic.** Each `.claude/commands/*.md` calls the corresponding
`uv run gig-ops ...` command via `!` execution. One source of truth.

---

## CLI Commands

```bash
uv run gig-ops scan                          # scan all sources for new events
uv run gig-ops scan --source tavily          # specific source
uv run gig-ops evaluate "Odense Flower Fest" # score a specific event
uv run gig-ops contact "Odense Flower Fest"  # find organizer (only if score ≥ C)
uv run gig-ops mail "Odense Flower Fest"     # generate outreach email
uv run gig-ops followup                      # check who needs a follow-up
uv run gig-ops tracker                       # open Textual TUI dashboard
uv run gig-ops deep "Roskilde Festival"      # deep research mode
uv run gig-ops suppress <email|domain>       # add to do-not-contact list
```

```
# Claude Code slash commands (same operations, wrap CLI)
/gig-ops
/gig-ops-scan
/gig-ops-evaluate
/gig-ops-contact
/gig-ops-mail
/gig-ops-tracker
/gig-ops-deep
```

---

## Event Evaluation (Multi-Dimensional Scoring)

The evaluator does **not** return a single A–F directly. It scores each dimension separately, stores all scores in the
database, and only then aggregates to a final A–F. This makes it possible to spot evaluator hallucinations (e.g. "
audience size = 5000" when no such info exists in the source).

Dimensions:

1. **Event type** — festival / corporate party / conference / wedding / private
2. **Audience size** — estimated number of attendees (bigger = better fit for live caricature)
3. **Date** — is it in the future? Realistic to reach in time?
4. **Geography** — distance from Odense (travel costs apply beyond ~50km)
5. **Contactability** — is there a named organizer with a reachable email?
6. **Budget signal** — commercial company vs. community/volunteer event
7. **Fit with Dagmar's style** — fun, social, creative > formal/academic
8. **Competition** — any sign they already have entertainment booked?

**Score A** = strong fit, reach out immediately.
**Score F** = not worth pursuing.
**Recommend against contacting anything below C.**

Each dimension score must reference a specific scraped fact (a URL or quoted text). No supporting fact = score that
dimension as `unknown`, **not** as a guess.

---

## Source Citations (Mandatory)

Every fact extracted from external sources by AI — organizer name, email, audience size, date, event type — **must** be
paired with the source URL it came from. The evaluator and contact finder enforce this in their prompts (
`modes/evaluate.md`, `modes/contact.md`).

**If a fact has no citation, it is not written to the database.** This is the primary defense against hallucinated
organizers and fabricated event details.

The mail generator receives the **full scraped text** of the event page as context, not just the event name. If it lacks
a concrete detail to reference, it writes a slightly more generic email — never invented details.

---

## Mail Generation Rules

- Always write in **Danish** unless the event is clearly international
- Keep it **short** — 3–4 paragraphs max
- Mention the specific event by name
- Reference one concrete thing about the event, **grounded in scraped text** (no invention)
- Include a link to dagmarstudio.dk
- Include a clear opt-out line (GDPR — see below)
- Never oversell — Dagmar's tone is warm, personal, professional
- End with a clear but soft call to action ("Er der mulighed for at høre mere?")
- Never use generic templates that sound copy-pasted

For each event, the mailer generates **2–3 variants** so Dagmar can pick. At her scale, the API cost is trivial and the
quality lift is real.

---

## GDPR & Legal Posture

Operating in Denmark/EU. Non-negotiable:

1. **No LinkedIn scraping.** Against their ToS, against GDPR, risk of account ban. LinkedIn may be used for **manual**
   research only, never via Crawl4AI.

2. **B2B only by default.** Cold outreach to companies, festivals, and event organizers under legitimate interest is
   defensible. **B2C outreach (private weddings, individuals) is excluded** unless there is a clear public business
   contact.

3. **Suppression list is mandatory.** Anyone who replies "not interested," anyone Dagmar manually flags, and any domain
   marked do-not-contact goes into the `suppression` table. **Every scan and every mail action checks suppression first.
   ** No exceptions.

4. **Opt-out line in every email.** A single sentence, e.g.: *"Hvis du foretrækker ikke at modtage flere henvendelser
   fra mig, så lad mig venligst vide det, og jeg fjerner dig fra min liste."*

5. **Email verification.** Before saving an extracted email as `organizer_email`, run an MX-record check on the domain.
   Hallucinated emails or addresses on dead domains never reach the tracker.

---

## Database Schema (SQLite)

Key tables:

```sql
events (
    id, name, url, date, location, type,
    score_final,                            -- aggregated A–F
    score_dimensions_json,                   -- per-dimension scores + citations
    raw_scraped_text,                        -- for grounding mail generation
    status, source, found_at, updated_at,
    mode_versions_json                       -- which modes/*.md versions produced this
)

contacts (
    id, event_id, organizer_name, organizer_email,
    email_verified,                          -- MX check passed
    source_url,                              -- citation: where it came from
    found_at
)

mails (
    id, event_id, draft_path, language,
    variant_label,                           -- A / B / C
    generated_at, mode_version
)

replies (
    id, event_id, received_at, snippet, marked_by
)

suppression (
    pattern,                                 -- email or domain
    reason, added_at
)
```

### Status state machine

```
NEW → EVALUATED → (score < C) → DROPPED
              ↓
              (score ≥ C) → CONTACT_FOUND → MAIL_DRAFTED → SENT
                                                         ↓
                                    REPLIED / NO_REPLY / BOOKED / REJECTED
```

Transitions enforced in `tracker.py`. No direct status writes from elsewhere.

### SQLite settings

```python
PRAGMA
journal_mode = WAL;  # concurrent reads during writes
PRAGMA
foreign_keys = ON;  # enforce FK constraints
PRAGMA
synchronous = NORMAL;  # safe with WAL, faster
```

**Backup:** `cp data/events.db data/backups/events-$(date +%Y%m%d).db` daily via launchd.

---

## Mode Versioning

`modes/*.md` files are the source of truth for AI behavior. Each file starts with frontmatter:

```yaml
---
version: 1.2
updated: 2025-11-15
---
```

When the evaluator, contact finder, or mailer runs, it records the version of the mode file used into
`events.mode_versions_json`. This makes it possible to look at any AI output later and know exactly which prompt
produced it. Without this, debugging "why did the mails suddenly start sounding weird in November?" is guesswork. **Bump
the version on every meaningful edit.**

---

## Reply Handling

For v1: **manual marking in the TUI dashboard.** When Dagmar gets a reply in her inbox, she opens the dashboard, finds
the event, and marks `REPLIED` (with optional outcome: `BOOKED` / `REJECTED`).

This is a small friction point but the only option that doesn't require building IMAP integration or routing all of
Dagmar's mail through a sending service. The `followup` mode reads the `replies` table — if no reply within N days,
suggest a follow-up; if there is, skip.

Future option (only if the friction becomes painful): IMAP polling against Dagmar's inbox with subject-line/thread
matching against event names.

---

## Search Sources

### Tavily (primary scanner)

Used for broad discovery queries like:

- `"festival Danmark 2025 underholdning"`
- `"firmafest Fyn 2025"`
- `"konference Odense 2025"`
- `"bryllupsmesse Danmark"` (B2B vendor side only)

Free tier (~1000 calls/month) is more than enough for this project's volume.

### Crawl4AI (deep scraping)

Used for:

- Eventbrite Denmark (public events)
- Facebook Events (public pages only)
- Specific portal sites defined in `portals.yml`

**Not used for:** LinkedIn (see GDPR section).

### portals.yml (regular scans)

A curated list of Danish event listing sites to check regularly:

- visitfyn.dk/events
- odense.dk/oplevelser/arrangementer
- eventbrite.dk
- municipal event pages

---

## Environment Variables

```bash
ANTHROPIC_API_KEY=        # required
TAVILY_API_KEY=           # required for scan
PERPLEXITY_API_KEY=       # optional, used in deep mode
```

Store in `.env` (gitignored). See `.env.example`.

---

## Cost Reality

Single-user side project. Realistic monthly cost:

- **Tavily:** 0 DKK (free tier)
- **Anthropic API:** ~70 DKK at 200 events/month, halved further by evaluate-first ordering
- **Crawl4AI:** 0 DKK (self-hosted)

**~70 DKK/month total.** No token logging, no cost dashboards, no caching needed. If costs ever start to matter, that
means Dagmar is doing way more outreach than human-in-the-loop can sustain — at which point the constraint isn't budget,
it's her time.

---

## Key Principles

1. **Never send emails automatically.** Always save as draft, let Dagmar review.
2. **Quality over quantity.** Better to find 5 great events than 50 mediocre ones.
3. **Personalization is everything, but never invented.** A generic email is worse than no email; a fabricated email is
   worse than a generic one.
4. **Dagmar's time is the constraint.** She can realistically handle 3–5 new outreach emails per week. Optimize for
   *her* time.
5. **modes/*.md files are the source of truth for AI behavior.** Edit them to tune how Claude evaluates and writes. Bump
   version on every change.
6. **Source citations or no fact.** AI-extracted information without a source URL doesn't get written to the database.
7. **Suppression list is checked first, always.** Before scan dedup, before contact lookup, before mail generation.
8. **The system is designed to be adapted by Claude itself.** If Dagmar says "focus more on corporate events" or "I
   don't do weddings anymore," update `profile.yml` and `_shared.md`.

---

## Dagmar's Profile (summary — full details in profile.yml)

- Based in **Odense, Denmark** (Czech origin, fluent in Danish and English)
- Offers: live event caricatures, studio portraits, animal portraits
- Typical event rate: from **2,600 DKK** (2h private) / **6,000 DKK** (corporate)
- Travel: available across Denmark, travel costs added beyond ~50km from Odense
- Style: warm, humorous, fast (one portrait ~5 minutes live)
- Languages: Danish, English, Czech
- Website: https://dagmarstudio.dk

---

## Development Notes

- Package manager: **uv** (`uv run`, `uv add`, `uv sync`)
- Project layout: **src/** (`src/gig_ops/`)
- Entry point in `pyproject.toml` under `[project.scripts]`
- Python version: 3.12+
- Async code uses `asyncio` + `async/await` (Crawl4AI is async-native)
- Database: SQLite with WAL mode, accessed via stdlib `sqlite3` or SQLAlchemy core (no ORM — overkill for this size)
- Textual dashboard runs as a separate command (`uv run gig-ops tracker`)
- Tests in `tests/` (pytest), including:
    - **Snapshot tests** for mode prompt outputs (catch unintended drift)
    - **Evaluator eval set** — labeled events with expected A–F scores; regression-test the evaluator when modes change
    - **Suppression check** — every code path that contacts an organizer must pass through suppression filter

---

## Review Comments / Suggested Improvements

These notes are not blockers. The overall design is solid and well-scoped for a single-user, human-in-the-loop outreach
tool. The following points are recommended clarifications before implementation.

### 1. Treat Facebook Events as best-effort only

The document allows Crawl4AI for Facebook Events public pages. This should be handled carefully because Facebook is
technically brittle and may restrict automated access.

Suggested clarification:

```md
Facebook Events are best-effort only. Do not bypass login, rate limits, bot protection, or access controls. Prefer
public organizer websites over Facebook pages when available.
```

### 2. Clarify what `email_verified` means

The current GDPR/legal section says extracted emails should pass an MX-record check before being saved as
`organizer_email`. This is useful, but MX verification only proves that the domain can receive email. It does **not**
prove that the specific mailbox exists.

Suggested clarification:

```md
email_verified means domain-level MX verification passed, not mailbox-level verification.
```

Possible alternative field name:

```sql
email_domain_verified
```

This would avoid overpromising what the verification step actually proves.

### 3. Avoid two sources of truth for suppression

The project structure includes `suppression.yml`, while the database schema also includes a `suppression` table. This
can become ambiguous unless the responsibility of each is clearly defined.

Recommended approach:

- Use `suppression.yml` only as an optional seed/import file or manually maintained bootstrap list.
- Use the SQLite `suppression` table as the runtime source of truth.
- All scan, contact, mail, and follow-up operations should check the database table.

Suggested clarification:

```md
suppression.yml is optional seed/config input. The SQLite suppression table is the runtime source of truth. All
operational checks use the database table.
```

### 4. Add an explicit deduplication strategy

Events will appear from multiple sources: Tavily, Eventbrite, municipal portals, organizer websites, and possibly
listing aggregators. Without a dedup rule, the tracker may quickly collect duplicate events.

Suggested rule:

```md
Dedup key: normalized event name + normalized date + normalized location/domain.
If uncertain, keep both records but mark them as possible_duplicate.
```

Possible schema addition:

```sql
possible_duplicate_of
```

or:

```sql
dedupe_key
```

Useful normalization examples:

- lowercase event names
- strip punctuation
- normalize Danish characters consistently
- normalize dates to ISO format
- compare organizer/event domains when available

### 5. Store source confidence separately from event fit

The evaluator scores how good an event is for Dagmar. That is different from how trustworthy the source is.

Recommended source-confidence levels:

- `high`: official event website, municipality site, VisitFyn, venue website
- `medium`: Eventbrite, known event portals, organizer social pages
- `low`: search snippet only, generic aggregator, incomplete listing

Suggested schema addition:

```sql
source_confidence
```

Suggested rule:

```md
AI-generated mails should not be created from low-confidence search snippets alone. Low-confidence events must be
confirmed by crawling an event page or organizer page first.
```

### 6. Add minimal run metadata logging

The cost reality section says no token logging, no cost dashboards, and no caching needed. That is reasonable. However,
minimal operational run logging would still be useful for debugging scanner/evaluator behavior.

Suggested table:

```sql
runs (
    id,
    mode,
    started_at,
    finished_at,
    status,
    input_summary,
    result_summary,
    error
)
```

This does not need to track tokens or cost. It only answers questions like:

- What ran?
- When did it run?
- Did it fail?
- How many events were found/evaluated/dropped?

### 7. Rename or narrow the `Contactability` evaluation dimension

The pipeline intentionally evaluates events before running contact lookup. But the evaluation dimensions currently
include:

> Contactability — is there a named organizer with a reachable email?

That may conflict with the pipeline order, because the contact finder has not run yet.

Recommended rename:

```md
Visible contact signal — does the scanned page mention an organizer, contact page, or contact email?
```

Then, after the Contact Finder runs, the system can store actual contactability based on whether it found a usable
organizer name/email.

Suggested distinction:

- `visible_contact_signal`: cheap scan/evaluation metadata
- `contact_found`: result of the Contact Finder step

### 8. Make year-based search queries dynamic

The Tavily query examples currently include hardcoded `2025`. Search queries should be generated dynamically using the
current year and next year.

Suggested clarification:

```md
Search queries should use the current year and next year dynamically, not hardcoded years.
```

Example:

```text
"festival Danmark {current_year} underholdning"
"festival Danmark {next_year} underholdning"
"konference Odense {current_year}"
"konference Odense {next_year}"
```

### 9. Keep the human-in-the-loop boundary explicit everywhere

The document already says emails are never sent automatically. This is important enough that it should also be reflected
in command behavior and status transitions.

Suggested clarification:

```md
The system may generate mail drafts and mark them as MAIL_DRAFTED, but only a human can mark an outreach as SENT. No CLI
command or slash command may send email directly.
```

This keeps the safety boundary visible both architecturally and operationally.

### 10. Consider adding a `needs_review` flag

Some events will be ambiguous: maybe the event is relevant, but the source is weak, contact info is unclear, or the AI
score has unknown dimensions.

Suggested schema addition:

```sql
needs_review BOOLEAN DEFAULT FALSE
review_reason TEXT
```

Useful cases:

- low source confidence
- possible duplicate
- missing date
- missing location
- unknown budget signal
- uncertain B2B/B2C classification
- contact found but email domain does not match organizer domain

This helps keep the dashboard focused and prevents borderline cases from silently moving forward.

### 11. Define B2B/B2C classification more concretely

The GDPR section says B2B is default and B2C/private weddings are excluded unless there is a clear public business
contact. This is good. It may help to encode this into event metadata.

Possible values:

```text
business
public_organization
festival
municipality
private_individual
unknown
```

Suggested rule:

```md
Events classified as private_individual or unknown should not proceed to mail generation unless manually approved.
```

### 12. Keep scraped text retention modest

The schema stores `raw_scraped_text`. This is valuable for grounding, but it is worth keeping retention modest and
purposeful.

Suggested clarification:

```md
Store only event-relevant scraped text needed for citations, evaluation, and mail grounding. Avoid storing unrelated
page content, personal profiles, comments, or social media discussion threads.
```

This aligns well with the existing GDPR posture.

---

## Summary of Recommended Changes

Highest-priority edits before implementation:

1. Clarify `suppression.yml` vs. the SQLite `suppression` table.
2. Rename or clarify `email_verified` as domain-level MX verification only.
3. Rename `Contactability` to `Visible contact signal` in pre-contact evaluation.
4. Add an explicit deduplication strategy.
5. Treat Facebook Events as best-effort and do not bypass access controls.
6. Add minimal `runs` logging for debugging.
7. Make Tavily search years dynamic.
8. Add `needs_review` for ambiguous or weakly sourced events.

None of these change the overall architecture. They mainly make the existing design safer, clearer, and easier to debug.

---

## Architecture Decisions

Decisions made during development. Record here so future sessions don't relitigate settled choices.

### Light DDD over flat functions

The codebase moved from a flat-function style to a light Domain-Driven Design structure:

```
src/gig_ops/
  domain/        # pure data models (Event, Contact, MailDraft) — no I/O
  protocol/      # Python Protocols (structural interfaces) — no ABCs
  infrastructure/sqlite/  # SQLite implementations of the protocols
```

**Why:** Protocols make unit testing trivial — any object that matches the shape works, no `unittest.mock.patch` needed.
The domain layer stays free of database concerns. This is the right level of structure for a project this size; a full
DDD with aggregates/repositories/services would be over-engineering.

**Rule:** Keep domain models pure (no imports from `db`, `infrastructure`, or `protocol`). Infrastructure depends on
domain, never the reverse.

### Protocols over ABCs

`protocol/repository.py` defines `Repository` as a `typing.Protocol`, not an `ABC`.

**Why:** `Protocol` supports structural subtyping — test doubles don't need to inherit from anything. `ABC` would force
every mock/stub to explicitly subclass, adding coupling with no benefit at this scale.

### MCP: deferred, but protocol-ready

The `deep` mode (deep research on a specific event/organizer) is a candidate for MCP (Model Context Protocol) tooling —
it involves multi-step browsing, research, and synthesis where MCP's tool-calling architecture fits well.

Tavily (primary scanner) stays as a direct API call for now — the volume and simplicity don't justify MCP overhead.

**The protocol layer keeps this option open.** If MCP is added later (e.g. for deep mode), it plugs in as a new
`infrastructure/mcp/` implementation of the same `Repository` protocol. No domain or CLI changes needed.

**Rule:** Do not add MCP for Tavily or standard scanning. Revisit MCP only for `deep` mode if/when deep research becomes
a bottleneck.

---

## Collaboration Rules (AI assistant instructions)

- **Run `make check` after every batch of changes.** This runs lint (ruff), type checking (pyright), and tests (pytest,
  excluding slow). Fix all issues before considering a batch done.
- **Write pytest tests for new code where it makes sense.** Keep tests basic — unit tests over logic, not
  over-engineered fixtures. Mark slow/integration tests with `@pytest.mark.slow`.
- **Work directly in the project.** Do not create git worktrees. Edit files in place.
- **Never commit immediately after making changes.** Show the changes, let the user read them in the IDE, and wait for
  explicit "commitni". Then prepare the commit and let the user approve via the tool permission UI. Use conventional
  prefixes: `feat`, `fix`, `chore`, `refactor`, `test`, `docs`. Do not amend published commits.
- **The user handles branching and rebase.** Do not create branches, rebase, or force-push. Commit to the current branch
  and push — that's it.
- **Language:** Code, comments, and docstrings in English. Content config (`queries.yml`, templates, `profile.yml`) in
  the language of the market — Danish for Danish-facing content, English where international.
