# SIEM Toolkit — SentinelOne AI-SIEM

> *Inspired by Pineapple Boy!* 🍍

A self-hosted troubleshooting and visibility tool for SentinelOne AI-SIEM SecOps engineers. Runs as a Docker Compose stack against your SentinelOne demo or production tenant and provides real-time insight into parser coverage, ingest volume, and data quality — all without leaving a single interface.

---

## What's Inside

| Page | Purpose |
|---|---|
| **Overview** | Live health stats — coverage percentage, active sources, top uncovered sources by volume |
| **Parser Coverage Map** | Which active data sources have a parser? Which don't? |
| **Ingest Dashboard** | Event volume, top sources, cost projection, filter simulator |
| **Parser Quality** | Live event sampler, field population rate, parser test runner |
| **Onboarding Accelerator** | Prompt template for onboarding new log sources with Claude Code |
| **Settings** | Manage your `.env` credentials directly from the interface |

---

## Architecture

```
browser → nginx (port 3001) → single-page HTML/JS application
                ↓ API calls
          FastAPI backend (port 8001)
                ↓
    ┌───────────────────────────┐
    │  PostgreSQL (SQLAlchemy)  │  parser fields, active sources
    └───────────────────────────┘
                ↓
    ┌───────────────────────────┐
    │  SentinelOne APIs         │
    │  • Management API         │  
    │  • XDR PowerQuery  │  
    └───────────────────────────┘
```

All services run via Docker Compose. The `parsers/` directory is volume-mounted into the backend so SDL parser files may be loaded without rebuilding the image.

---

## Setup

### 1. Clone and Configure

```bash
git clone 
cd SIEM-Toolkit-patched
cp .env.example .env
```

Edit `.env` with your credentials:

```env
S1_BASE_URL=       # Your console URL
S1_API_TOKEN=...                             # Service user API token (account scope or higher)
SDL_XDR_URL=    #  XDR endpoint
SDL_LOG_READ_KEY=                    # Data Lake read key
ANTHROPIC_API_KEY=                              # Optional — not currently used
# SDL Configuration Read key — used by /api/quality/sync-from-sdl to
# download parser files from /logParsers/ on the SDL tenant.
# Generate in S1 console: Settings -> Integrations -> Data Lake API Keys (Configuration Read scope).
SDL_CONFIG_READ_KEY=
```

**S1_API_TOKEN** — generate at *Settings → Users → Service Users* in the console. 
Ideally, the service user API token must be at **account scope** or higher. Site-scoped tokens will have limited visibility into rules and may see reduced source counts.

**SDL_LOG_READ_KEY** 



### 2. Add Parser Files 

Place your SDL parser JSON files into the `parsers/` directory. The backend reads them directly at query time — no rebuild is necessary.

```bash
cp ~/my-parsers/*.json parsers/
```

### 3. Start the Stack

```bash
docker-compose up -d --build
```

Open **http://localhost:3001** in your browser and you're off.

---

## Features

### Overview Dashboard

The landing page gives you an at-a-glance health summary drawn live from the database:

- **Parser Coverage %** — proportion of active sources with a confirmed parser
- **Active Sources** — total number of `dataSource.name` values seen in the last 7 days
- **Covered / Need Parser** — counts for each status

If any sources are uncovered, the **Top Sources Needing a Parser** table lists the highest-volume offenders. Click any source name to jump directly to the Parser Quality page with that source pre-selected.

---

### Parser Coverage Map

Answers the question: *does each active data source have a parser running?*

**How it works:**

1. **Sync Live Sources** — executes a PowerQuery against your data lake to retrieve every `dataSource.name` seen in the last 7 days, along with event counts.
2. **Load SDL Parsers** — reads parser files from `parsers/`, extracts the `dataSource.name` attribute from each, and stores the field list in the database.

**Matching logic (three-tier):**
1. Exact `dataSource.name` match between the active source and the parser attribute
2. Normalised substring match (ignores spaces, dashes, and case) between the active source name and the parser's `dataSource.name`
3. Normalised substring match against the parser filename — catches files where the `dataSource.name` attribute is incorrect or missing

**Parser detection from data:** During sync, a parallel PowerQuery checks whether each source has events with `event.type` populated in the data lake. If so, a parser is confirmed as running — the source is marked **Covered** even without a local parser file. This handles built-in and cloud-managed parsers that are not present in your `parsers/` folder.

**Status values:**
- 🟢 **Covered** — custom parser confirmed (local file or detected via parsed events in the data lake)
- 🔴 **Parser Needed** — no parser found, or only a grok/dottedJson format (which typically indicates an incomplete parser)

**Filters:** Use the filter pills to focus on Custom Parser only, Default Parser Only (data lake detected), or No Parser.

**Deep link:** Click any source name in the table to open it directly in Parser Quality with all dropdowns pre-populated.

**Expected results:** After syncing sources and loading parsers, sources with active SDL parsers will appear as Covered. Sources sending raw, unparsed data — where only `message` and `timestamp` appear in the data lake — will appear as Parser Needed.

---

### Ingest Dashboard

Answers the question: *where is my event volume coming from, and what would happen if I filtered some of it?*

**Time range:** 1h (default), 3d, 5d, 7d

**Daily Event Volume** — bar chart of total events per day. In 1h mode, this switches to a by-source breakdown of the current hour's activity.

**Top Sources** — a table of the 25 highest-volume `dataSource.name` values with event count and estimated GB (calculated at 0.5 GB per million events).

**Filter Simulator** — enter a source name and an optional event type, then press Simulate. The backend runs a live PowerQuery counting matching events and projects:
- Matched events in the selected period
- Estimated GB that would be saved
- Projected monthly events and GB if the filter were applied permanently

This is entirely read-only — no filter is created or applied. Use the results to inform an exclusion rule you apply manually in the console.

**Expected results:** Top sources should reflect what you see in the SentinelOne console PowerQuery tool. The filter simulator provides a reasonable GB estimate assuming uniform event size across the source.

---

### Parser Quality

Three tools for diagnosing parser extraction failures.

#### Live Event Sampler

Pulls raw events from a selected source directly from the data lake and renders every field that came back. The `message` column is pinned to the right of the table, with a **⎘ copy** button on each row for convenient extraction of raw log lines.

- **Empty fields** are displayed as `∅` in grey — immediately highlighting fields the parser is failing to populate
- **Healthy source:** many fields populated (`src.ip`, `user.name`, `event.type`, etc.), with `message` present as the raw log backup
- **Unhealthy source:** only `timestamp` and `message` populated — the parser is not extracting anything of value

#### Field Population Rate

Samples up to 500 events from a source and measures what percentage of them have each field populated. Results are sorted worst-first so the most pressing gaps are immediately visible.

When you select a source, the tool automatically discovers which fields exist in that source's events and pre-fills the field list — merged with SDL schema defaults. The list is fully editable before running the analysis.

**Colour coding:**
- 🟢 ≥ 80% — healthy extraction
- 🟡 40–79% — partial extraction; check your regex patterns
- 🔴 < 40% — field is rarely populated; the parser is likely not matching this log format variant

**Healthy parser:** Key fields such as `src.ip`, `event.type`, and `user.name` should sit between 70–100%. Niche fields like `src.process.cmdline` or `tgt.file.path` will naturally be lower, as not every event type produces them.

**Broken parser:** All SDL fields at 0%, with only `timestamp` and `message` visible in the "fields seen in sample" chip list at the bottom of the results.

#### Parser Test Runner

Paste a raw log line, select a loaded parser, and press Test. The backend extracts SDL `$field=pattern$` format strings from the parser file, converts them to Python named-group regular expressions, and tries each against your log line.

- **Matched:** displays the format string that matched and every field extracted with its value
- **No match:** none of the parser's format strings apply to this log line — the log may contain a format variant the parser does not yet cover

> **Note:** Only parsers using SDL custom format strings are supported by the test runner. Grok and dottedJson parsers are not currently testable here.

---

### Onboarding Accelerator

A prompt template for using Claude Code to onboard a new log source. Copy the template, paste a sample of raw log lines, and Claude Code will generate:

- An SDL parser skeleton in augmented-JSON format
- Field mappings to the SDL common schema
- Parser test assertions

No Anthropic API key is required — this uses Claude Code directly from your terminal.

---

### Settings

Read and write your `.env` credentials from the interface. Secret fields (API tokens, keys) are masked by default with a show/hide toggle. Changes are written to the mounted `.env` file and take effect after restarting the backend:

```bash
docker-compose up -d --build backend
```

---

## Rebuilding

```bash
# Full rebuild
docker-compose up -d --build

# Backend only (after Python changes)
docker-compose up -d --build backend

# Frontend only (after HTML/JS changes)
docker-compose up -d --build frontend

# Reset the database
curl -X DELETE http://localhost:8001/api/coverage/reset
```

---

## Project Layout

```
.
├── backend/
│   ├── main.py                  # FastAPI application, router registration
│   ├── db.py                    # SQLAlchemy models
│   ├── routers/
│   │   ├── coverage.py          # Parser coverage map endpoints
│   │   ├── ingest.py            # Ingest dashboard + filter simulator
│   │   ├── quality.py           # Parser quality tools
│   │   └── settings.py          # .env read/write
│   └── services/
│       ├── s1_client.py         # SentinelOne + Scalyr API client
│       └── rule_parser.py       # SDL format string field extraction
├── frontend/
│   └── index.html               # Single-page application (Tailwind, vanilla JS)
├── parsers/                     # SDL parser files (volume-mounted)
├── db/
│   └── init.sql                 # Postgres initialisation (tables created by SQLAlchemy)
├── docker-compose.yml
├── .env.example
└── README.md
```

---

```
Nothing pushes parsers to the SDL tenant
The data flow is strictly one-way: SDL tenant → local disk.

What actually happens
┌──────────────────┐    GET /api/listFiles/logParsers/    ┌──────────────────┐
│   SDL tenant     │ ───────────────────────────────────▶ │ tools/sync_sdl_  │
│                  │    GET /api/getFile/logParsers/...   │  parsers.py      │
└──────────────────┘                                       └────────┬─────────┘
                                                                    │ writes
                                                                    ▼
                                                          ./parsers/<name>
                                                                    │
                                                                    │ bind-mount
                                                                    ▼
                                                          /app/parsers (in container)
                                                                    │
                                                                    │ read-only
                                                                    ▼
                                            ┌──────────────────────────────────┐
                                            │ POST /api/quality/test-parser    │
                                            │ POST /api/quality/sync-from-sdl  │
                                            │ GET  /api/quality/parsers        │
                                            └──────────────────────────────────┘

Endpoint / 	What it really does
Sync from SDL (POST /api/quality/sync-from-sdl)		Downloads parsers from the tenant into /app/parsers/
Load SDL Parsers (UI button)	Just re-indexes whatever files already exist in /app/parsers/
Test Parser (POST /api/quality/test-parser)		Runs the parser logic locally in Python; tenant never touched
tools/sync_sdl_parsers.py	(helper)	Downloads parsers; never uploads
```

