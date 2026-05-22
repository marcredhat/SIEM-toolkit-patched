# Changes vs upstream `mickbrowns1/SIEM-Toolkit`

All edits are confined to a handful of files; everything else is untouched.

## `backend/services/s1_client.py`

### PowerQuery client
- All raised exceptions now include the request body / status / query so the
  UI never shows a blank `"PowerQuery error: "`.
- Non-JSON responses (HTML 5xx gateway pages) surface as a readable error
  string instead of crashing on `resp.json()`.

### Detection library: site-scope fallback (`get_platform_rules`)
- Upstream hardcoded **account scope** which 403s with site-scoped API
  tokens. Added `get_scope_for_platform_rules()` that probes `/accounts`
  first, then `/sites`, returning whichever scope the token can access.
- `get_account_id()` now also reads `accountId` from the `/sites` payload as
  a fallback for site-scoped tokens.

### SDL parser sync helpers
- `list_sdl_parsers()` — rewritten to use the real **SDL Configuration File
  API** (`POST /api/listFiles` with `pathPrefix=/logParsers/`). Previously
  it hit a 404 path on the mgmt console.
- `get_sdl_parser()` — rewritten to `POST /api/getFile` with `{path}`.
- New `_sdl_config_headers()` helper that uses `SDL_CONFIG_READ_KEY` (a
  separate scope from `SDL_LOG_READ_KEY`).

## `backend/routers/ingest.py`

- `/api/ingest/simulate-filter`:
  * Rebuilt the query into valid SDL syntax — was generating
    `| group events=count()` (dangling pipe) for empty bodies; now uses a
    proper base expression and falls back to `dataSource.name!=''` baseline.
  * Field name corrected from `src.name` → `dataSource.name`.
  * Surfaces both `result["error"]` and exception text so blank
    `"PowerQuery error: "` messages are gone.

## `backend/routers/quality.py`

- `GET /api/quality/parsers`: lists actual parser filenames in
  `/app/parsers/` (drives the Test Runner dropdown).
- **New `POST /api/quality/sync-from-sdl`**: downloads every parser file
  under `/logParsers/` on the SDL tenant into `/app/parsers/`. After this
  call returns, the Parser Test Runner dropdown automatically reflects all
  tenant parsers (including custom OCSF parsers like
  `Avelios-Medical-OCSF`). Requires `SDL_CONFIG_READ_KEY` in `.env`.
- `_flatten_event`: when a PowerQuery row only carries a JSON-stringified
  payload in `message` (i.e. the parser isn't applied at query time), parse
  and flatten that JSON inline so the Field Population tool can measure real
  coverage.
- `POST /api/quality/test-parser`:
  * Detects SDL JSON-mode parsers (`$=json{parse=json}$`) and parses log
    lines as JSON.
  * Applies parser `rewrites: [{input,output,match,replace}]` blocks with
    correct `$0/$N` backreference translation (`$0` was being mangled to a
    null byte).
  * Accepts single JSON object, JSON array, or NDJSON multi-line input.
  * Returns mode badge data + per-payload counters for the UI.

## `frontend/index.html`

- Parser Test Runner dropdown now loads from `/api/quality/parsers` instead
  of filtering the coverage map (which only has `detected in data`
  placeholders).
- Field Population and Sample Events: added **Last 7d** lookback option.
- Parser Test Runner UI: mode badge (`JSON auto-extract` vs `regex format`),
  payload counter for multi-line input, separate tables for extracted vs
  derived/rewritten fields.

## `docker-compose.yml`

- Pass `SDL_CONFIG_READ_KEY` through to the backend container.

## `.env.example` / `.gitignore`

- Document the new `SDL_CONFIG_READ_KEY` variable.
- Broaden `.gitignore` so `parsers/*` (tenant-specific synced content) is
  not committed.

## New helper scripts (`tools/`)

- `sync_sdl_parsers.py` — pull all `/logParsers/*` from the tenant.
- `probe_pq_syntax.py` — probe which PowerQuery syntaxes the tenant accepts.
- `probe_avelios{,_wide,_fields}.py` — inspect a source's event presence,
  columns, and embedded JSON fields.
- `test_avelios_parser.py`, `test_avelios_multi.py` — smoke-test the patched
  `/api/quality/test-parser` endpoint with single-line and multi-line input.
- `probe_simulate_filter.py` — smoke-test the patched
  `/api/ingest/simulate-filter` endpoint with progressively larger windows.
- `probe_sync_from_sdl.py` — call `/api/quality/sync-from-sdl` and verify
  that `/api/quality/parsers` then reflects the downloaded parsers.
- `sdl_config.example.json` — template config (the toolkit's `.env` is
  separate from the SDL config used by these helper scripts).

## New `.env` knobs

```bash
# PowerQuery transport tuning (both optional; defaults work for most tenants)
SDL_PQ_TIMEOUT=600              # PowerQuery read timeout in seconds (default 600)
SDL_PQ_TIMEOUT_RETRIES=1        # extra retries on ReadTimeout (default 1)

# Required for /api/quality/sync-from-sdl
SDL_CONFIG_READ_KEY=...         # Data Lake API key with Configuration Read scope
```
