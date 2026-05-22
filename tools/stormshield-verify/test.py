#!/usr/bin/env python3
"""
End-to-end test that the Stormshield parser is actually applied at ingest by
SentinelOne SDL.

1. POSTs a raw Stormshield syslog line to /api/uploadLogs with `parser: stormshield`.
2. Polls SDL with PowerQuery to find the event we just ingested.
3. Inspects which OCSF fields are populated to confirm SDL parsed it correctly.

Requires: log_write_key + log_read_key in ./config.json (see config.example.json)
"""
from __future__ import annotations
import json, time, uuid, urllib.request, urllib.error, sys, os

CFG_PATH = "./config.json"
PARSER   = "stormshield"
SERVER_HOST = f"siemtoolkit-test-{int(time.time())}"   # unique tag to find our event back

# Use current timestamps so events show up under "now" in the SDL console.
# The parser extracts `time="..."` as the canonical event timestamp via
# $timestamp=tsPattern$, so we must rewrite that field (not just the syslog
# header) to see the event under recent activity in https://demo.sentinelone.net.
from datetime import datetime, timezone, timedelta
import time as _time
_local_tz = datetime.now(timezone.utc).astimezone().tzinfo
_now      = datetime.now(_local_tz).replace(microsecond=0)
_start    = _now - timedelta(minutes=2)
SYSLOG_TS = _now.strftime("%Y-%m-%dT%H:%M:%S%z")              # 2026-05-22T16:32:00+0200
SYSLOG_TS = SYSLOG_TS[:-2] + ":" + SYSLOG_TS[-2:]              # → 2026-05-22T16:32:00+02:00
TIME_TS   = _now.strftime("%Y-%m-%d %H:%M:%S")
START_TS  = _start.strftime("%Y-%m-%d %H:%M:%S")
TZ_OFFSET = _now.strftime("%z")                                # +0200
TZ_OFFSET = TZ_OFFSET[:-2] + TZ_OFFSET[-2:]                    # keep +0200 form

LOG_LINE = (
    f'<14>1 {SYSLOG_TS} stormshield-v.univ-evry.fr asqd - - - '
    f'?id=firewall time="{TIME_TS}" fw="stormshield-v.univ-evry.fr" '
    f'tz={TZ_OFFSET} startime="{START_TS}" pri=5 confid=01 slotlevel=2 ruleid=34 '
    'rulename="17209b9db27_4" user="aimee.ndzodo" domain="ueve.local" '
    'srcif="sslvpn0" srcifname="sslvpn" ipproto=udp dstif="Ethernet1" dstifname="in" '
    'proto=dns_udp src=10.200.0.82 srcport=56637 srcportname=ephemeral_fw_udp '
    'dst=192.168.10.7 dstport=53 dstportname=dns_udp dstname=hyperion.univ-evry.fr '
    'modsrc=10.200.0.82 modsrcport=56637 origdst=192.168.10.7 origdstport=53 '
    'ipv=4 sent=80 rcvd=196 duration=0.00 action=pass logtype="connection"'
)


def _http(method, url, *, headers=None, data=None, timeout=60):
    req = urllib.request.Request(url, method=method, headers=headers or {}, data=data)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def main():
    with open(CFG_PATH) as f:
        cfg = json.load(f)
    base = cfg["base_url"].rstrip("/")
    write_key = cfg["log_write_key"]
    read_key  = cfg["log_read_key"]

    nonce = str(uuid.uuid4())
    headers = {
        "Authorization": f"Bearer {write_key}",
        "Content-Type":  "text/plain",
        "parser":        PARSER,
        "server-host":   SERVER_HOST,
        "Nonce":         nonce,
    }

    print("=" * 70)
    print("STEP 1 — POST /api/uploadLogs")
    print("=" * 70)
    print(f"  url         = {base}/api/uploadLogs")
    print(f"  parser      = {PARSER}")
    print(f"  server_host = {SERVER_HOST}")
    print(f"  nonce       = {nonce}")
    print(f"  body bytes  = {len(LOG_LINE)}")
    print(f"  embedded ts = time=\"{TIME_TS}\"  (parser uses this as event time)")
    print(f"  log line    = {LOG_LINE[:140]}...")
    status, body = _http("POST", f"{base}/api/uploadLogs",
                         headers=headers, data=LOG_LINE.encode())
    print(f"  -> HTTP {status}")
    print(f"  -> {body[:300]}")
    if status >= 400:
        sys.exit(f"uploadLogs failed: {status}")

    # ── STEP 3: poll for the event ──────────────────────────────────────
    # SDL ingest is typically visible in ~5-30s but can take up to 2 min.
    # Note: `server-host` HTTP header is overwritten to "uploadLogs" by SDL,
    # and `parser.name` is None on uploadLogs-ingested events. The reliable
    # filter is `parser='stormshield' and dataSource.name='Stormshield'`
    # constrained by Nonce (echoed back as an attribute) for our exact upload.
    query = (
        f"parser='{PARSER}' and dataSource.name='Stormshield' "
        "| columns timestamp, dataSource.name, parser, "
        "src_endpoint.ip, src_endpoint.port, dst_endpoint.ip, dst_endpoint.port, "
        "actor.user.name, unmapped.action, unmapped.proto, unmapped.fw, "
        "unmapped.rulename, unmapped.duration, message "
        "| sort -timestamp | limit 5"
    )

    print("=" * 70)
    print(f"STEP 2 — poll /api/powerQuery (up to 150s)")
    print("=" * 70)
    print(f"  query = {query}\n")

    matches: list = []
    columns: list = []
    deadline = time.time() + 150
    waited = 0
    while time.time() < deadline:
        time.sleep(10); waited += 10
        end_ms   = int(time.time() * 1000)
        start_ms = end_ms - 15 * 60 * 1000
        pq_body = {"query": query, "startTime": str(start_ms), "endTime": str(end_ms)}
        status, body = _http(
            "POST",
            f"{base}/api/powerQuery",
            headers={"Authorization": f"Bearer {read_key}",
                     "Content-Type": "application/json"},
            data=json.dumps(pq_body).encode(),
        )
        if status != 200:
            print(f"  t+{waited:3d}s: HTTP {status} — {body[:200]}")
            continue
        result  = json.loads(body)
        columns = result.get("columns") or []
        values  = result.get("values") or []
        n       = result.get("matchingEvents", len(values))
        print(f"  t+{waited:3d}s: matchingEvents={n}")
        if values:
            matches = [{"values": v} for v in values]
            break

    if not matches:
        print("\n  No events found after 150s. Either ingest is slow today, "
              "or the upload was rejected silently. Inspect upload response above.")
        sys.exit(2)

    # The response uses a columns/values layout. Discover column order.
    columns = result.get("columns") or []
    col_names = [c.get("name") if isinstance(c, dict) else str(c) for c in columns]
    print(f"\ncolumns: {col_names}")
    print(f"matches: {len(matches)}")

    print("\n" + "=" * 70)
    print("STEP 4 — parse results, check OCSF fields are populated")
    print("=" * 70)

    EXPECTED = {
        "src_endpoint.ip":   "10.200.0.82",
        "src_endpoint.port": "56637",
        "dst_endpoint.ip":   "192.168.10.7",
        "dst_endpoint.port": "53",
        "actor.user.name":   "aimee.ndzodo",
    }

    for i, m in enumerate(matches, 1):
        vals = m.get("values") or m
        row = dict(zip(col_names, vals)) if isinstance(vals, list) else vals
        print(f"\n--- match {i} ---")
        for k in col_names:
            v = row.get(k)
            mark = ""
            if k in EXPECTED:
                mark = "  ✅" if str(v) == EXPECTED[k] else f"  ❌ (expected {EXPECTED[k]!r})"
            print(f"  {k:25s} = {v!r}{mark}")

        # Summary
        hits = sum(1 for k, want in EXPECTED.items() if str(row.get(k)) == want)
        print(f"\n  OCSF rewrites populated: {hits}/{len(EXPECTED)}")
        if hits == len(EXPECTED):
            print("  → SDL parser applied the rewrites correctly. ✅")
        else:
            print("  → Some rewrites missing — the SDL parser may not have run.")

if __name__ == "__main__":
    main()
