#!/usr/bin/env python3
"""Query SDL to verify recent Stormshield events landed and were parsed."""
import json, time, urllib.request, sys

CFG = json.load(open("./config.json"))
BASE = CFG["base_url"].rstrip("/")
READ_KEY = CFG["log_read_key"]

now_ms   = int(time.time() * 1000)
start_ms = now_ms - 15 * 60 * 1000    # last 15 minutes

QUERY = (
    "parser='stormshield' "
    "| columns timestamp, dataSource.name, parser, "
    "src_endpoint.ip, src_endpoint.port, dst_endpoint.ip, dst_endpoint.port, "
    "actor.user.name, unmapped.action, unmapped.proto, unmapped.fw, unmapped.rulename "
    "| sort -timestamp | limit 10"
)

body = json.dumps({
    "query": QUERY,
    "startTime": str(start_ms),
    "endTime":   str(now_ms),
}).encode()

req = urllib.request.Request(
    f"{BASE}/api/powerQuery",
    method="POST",
    data=body,
    headers={
        "Authorization": f"Bearer {READ_KEY}",
        "Content-Type":  "application/json",
    },
)
with urllib.request.urlopen(req, timeout=60) as r:
    resp = json.loads(r.read())

cols    = [c["name"] for c in resp.get("columns", [])]
values  = resp.get("values", [])
total   = resp.get("matchingEvents", len(values))

print(f"query           = {QUERY}")
print(f"window          = last 15 min")
print(f"matchingEvents  = {total}")
print(f"cols            = {cols}")
print()

if not values:
    print("No events visible yet. SDL ingest can take 30-90s; re-run verify_query.py in a minute.")
    sys.exit(1)

print(f"{'timestamp(ns)':>20}  {'src':<16} {'sport':<6} -> {'dst':<16} {'dport':<6} {'user':<20} {'action':<8} {'proto':<8}")
print("-" * 110)
for row in values:
    d = dict(zip(cols, row))
    print(
        f"{d.get('timestamp',''):>20}  "
        f"{str(d.get('src_endpoint.ip','')):<16} "
        f"{str(d.get('src_endpoint.port','')):<6} -> "
        f"{str(d.get('dst_endpoint.ip','')):<16} "
        f"{str(d.get('dst_endpoint.port','')):<6} "
        f"{str(d.get('actor.user.name','')):<20} "
        f"{str(d.get('unmapped.action','')):<8} "
        f"{str(d.get('unmapped.proto','')):<8}"
    )

print()
print("✅ Events are visible in the SDL data lake under parser='stormshield'")
print("   Search in https://demo.sentinelone.net with:   parser=\"stormshield\"")
