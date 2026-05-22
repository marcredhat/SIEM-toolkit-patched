# Stormshield ingest verifier

End-to-end regression test for the SDL Stormshield parser. Sends raw syslog
events to `/api/uploadLogs`, waits for ingest, and confirms the OCSF rewrites
(`src_endpoint.ip`, `dst_endpoint.ip`, `actor.user.name`, ...) populated by
the parser at ingest time.

## Setup

```bash
cp config.example.json config.json
chmod 600 config.json
# Fill in log_write_key, log_read_key — both are SDL Data Lake API keys.
# Generate them in the S1 console: Singularity Data Lake -> API Keys.
```

`config.json` is gitignored. Never commit real tokens.

## Run

```bash
# Single-event upload + 150s polling verifier (prints which OCSF fields landed)
python3 test.py

# Burst of 4 varied events with current timestamps (different users, IPs, actions)
python3 send_burst.py

# One-shot regression: burst + 40s wait + query last 15 min
bash run_and_verify.sh
```

## How to find the events afterwards

The SDL console search field (and PowerQuery) attribute for the parser name
is **`parser`**, not `parser.name`:

```
parser="stormshield" | sort -timestamp | limit 10
```

## Behaviour quirks worth knowing

1. **`server-host` HTTP header is overwritten** to the literal string
   `uploadLogs` on this tenant. Don't try to filter by `serverHost` for
   precise event matching; use `parser='stormshield'` instead.
2. **`parser.name` is always None** on `uploadLogs`-ingested events.
   Use the bare `parser` attribute.
3. **Embedded `time="..."`** in the syslog body is taken as the event's
   canonical timestamp via `$timestamp=tsPattern$`. The scripts rewrite
   this to "now" so events appear under recent activity in the console.
4. **Ingest latency** is 5-60s. `test.py` polls for up to 150s.

## Files

- `test.py` — single upload + polling verifier
- `send_burst.py` — N varied events with current timestamps
- `verify_query.py` — query last 15 min of stormshield events
- `run_and_verify.sh` — burst + sleep + verify (regression test)
- `config.example.json` — template, copy to `config.json`
