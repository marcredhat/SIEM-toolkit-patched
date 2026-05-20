# SIEM-Toolkit Patches & Helper Scripts

A drop-in patch set that fixes several issues in the upstream
[`mickbrowns1/SIEM-Toolkit`](https://github.com/mickbrowns1/SIEM-Toolkit) and
adds helper scripts for syncing parsers from a SentinelOne SDL tenant and
probing PowerQuery / event data.

## What's fixed in the upstream code

| File | Fix |
|---|---|
| `backend/routers/ingest.py` | **Filter Simulator** PowerQuery rewritten — replaced legacy `count() as events` and `src.name` field with valid SDL `\| filter dataSource.name=='X' \| group events=count()` |
| `backend/routers/quality.py` | New `GET /api/quality/parsers` endpoint lists actual parser files; `_flatten_event` now JSON-parses nested `message` payloads so the **Field Population** tool reports real coverage (was always 0% for sources where the parser isn't applied at query time) |
| `backend/routers/quality.py` (Parser Test Runner) | Detects SDL JSON auto-extract format `$=json{parse=json}$` and parses log lines as JSON; applies parser `rewrites` (`input/output/match/replace` blocks) with correct `$0`/`$N` backreference handling; accepts **single JSON / JSON array / NDJSON** input |
| `frontend/index.html` | Parser dropdown now loads from `/api/quality/parsers` (was filtering `coverage/map` which only has `detected in data` placeholders); added **Last 7d** lookback to both Field Population and Sample Events; Test Runner UI now shows mode badge (`JSON auto-extract` vs `regex format`), payload count for multi-line input, and separate tables for extracted vs derived/rewritten fields |

## What's NOT fixed in the upstream code (configuration)

The repo's `docker-compose.yml` interpolates `S1_BASE_URL` etc. from
`.env` at compose-up time. **A `docker compose restart` does NOT pick up
`.env` changes** — always use `docker compose up -d --force-recreate backend`.

`S1_BASE_URL` must be the **per-tenant management console subdomain** (e.g.
`usea1-XXXX.sentinelone.net`), not the regional SDL/XDR endpoint. If you
only know the XDR URL, you can probe candidates with curl:

```bash
TOKEN=$(jq -r .api_token < ~/.../mgmt-config.json)
for H in usea1-yourtenant usea1-purple usea1-partners; do
  printf "%-45s  %s\\n" "$H" \\
    "$(curl -s -o /dev/null -w '%{http_code}' \\
       \"https://$H.sentinelone.net/web/api/v2.1/cloud-detection/rules?limit=1\" \\
       -H \"Authorization: ApiToken $TOKEN\")"
done
# 200 = correct host
```

## Contents

```
.
├── README.md                       (this file)
├── env.example                     template for the toolkit's .env
├── sdl_config.example.json         template for helper scripts' SDL config
├── patched-files/
│   ├── backend/routers/
│   │   ├── ingest.py               <- copy over upstream
│   │   └── quality.py              <- copy over upstream
│   └── frontend/
│       └── index.html              <- copy over upstream
└── scripts/
    ├── sync_sdl_parsers.py         pull all /logParsers/* from the tenant into ./parsers/
    ├── probe_pq_syntax.py          test what PowerQuery dialect the tenant accepts
    ├── probe_avelios.py            sample probe: find a source's events + columns
    ├── probe_avelios_wide.py       same, sweeping 1d/3d/7d
    ├── probe_avelios_fields.py     parse JSON `message` payloads & count fields
    ├── test_avelios_parser.py      hit /api/quality/test-parser with one JSON line
    └── test_avelios_multi.py       same, with multi-line NDJSON
```

## Applying the patches

1. Clone the upstream repo:
   ```bash
   git clone https://github.com/mickbrowns1/SIEM-Toolkit.git
   cd SIEM-Toolkit
   ```
2. Overlay the patched files:
   ```bash
   PATCH=/path/to/this/dir
   cp "$PATCH"/patched-files/backend/routers/quality.py backend/routers/quality.py
   cp "$PATCH"/patched-files/backend/routers/ingest.py  backend/routers/ingest.py
   cp "$PATCH"/patched-files/frontend/index.html        frontend/index.html
   ```
3. Configure:
   ```bash
   cp "$PATCH"/env.example .env
   $EDITOR .env                          # fill in your real values
   ```
4. Start the stack:
   ```bash
   docker compose up -d --build
   open http://localhost:3001
   ```

## Helper-script setup

The helper scripts read a small JSON config (separate from the toolkit's `.env`)
containing your SDL log-read / config-read keys:

```bash
cp sdl_config.example.json scripts/sdl_config.json
$EDITOR scripts/sdl_config.json
# or set the env var
export SDL_CONFIG=/somewhere/sdl_config.json
```

## Helper-script usage

### Sync parsers from the SDL tenant into the toolkit's `parsers/` dir

```bash
PARSERS_DIR=/path/to/SIEM-Toolkit/parsers \\
  python3 scripts/sync_sdl_parsers.py
```

By default `PARSERS_DIR` defaults to `../parsers` relative to the script.

### Probe PowerQuery syntax compatibility on your tenant

```bash
python3 scripts/probe_pq_syntax.py
```

Output tells you which command shapes (`| group ...`, `filter ...`, `count() as`, etc.)
work on the active deployment.

### Inspect what a given source's events actually look like

```bash
python3 scripts/probe_avelios.py            # finds a source's name + 1-line sample
python3 scripts/probe_avelios_wide.py       # sweeps 1d/3d/7d top sources
python3 scripts/probe_avelios_fields.py     # if `message` is JSON, flatten & count fields
```

The scripts are named `*_avelios` for the original use case but work for **any
source** — open the file and change the `dataSource.name` filter.

### Smoke-test the patched Parser Test Runner endpoint

```bash
python3 scripts/test_avelios_parser.py      # single-line JSON
python3 scripts/test_avelios_multi.py       # multi-line NDJSON
```

These hit `http://localhost:8001/api/quality/test-parser` directly so you can
verify the backend without using the UI.

## Common pitfalls

- **Parser dropdown is empty** → run `sync_sdl_parsers.py`. The upstream "Load
  SDL Parsers" button only indexes whatever already exists in `parsers/`.
- **Field Population shows 0% everywhere** → the source's parser isn't being
  applied at query time, so PowerQuery returns just `timestamp`+`message`.
  This patch's `_flatten_event` parses JSON inside `message`. Also try widening
  the window (the new **Last 7d** option) — some sources are low-volume.
- **PowerQuery 400 "Unknown command [count]"** → fixed in `ingest.py`. If you
  hit it elsewhere, the rule is: SDL PowerQuery requires `\| group events=count()`,
  never `\| count() as events`, and `count()` must be inside a `group`.
- **STAR rules → 302 to /404** → `S1_BASE_URL` is pointed at the SDL/XDR URL
  instead of the management-console subdomain.

## Verification

After applying patches and recreating containers:

```bash
curl http://localhost:8001/health
curl http://localhost:8001/api/quality/parsers | python3 -m json.tool   # count > 0
curl 'http://localhost:8001/api/ingest/top-sources?hours=24'           # real numbers
curl -X POST http://localhost:8001/api/coverage/load-star-rules        # not 502
```

In the UI:
- **Coverage Map**: shows `parsers_loaded` and `rules_loaded` > 0
- **Ingest → Filter Simulator**: returns matched events + projected GB/month
- **Parser Quality → Parser Test Runner**: dropdown lists all parsers
- **Parser Quality → Field Population**: real coverage rates (not all 0%)
