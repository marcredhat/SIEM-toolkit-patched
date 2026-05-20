#!/usr/bin/env python3
"""Trigger /api/quality/sync-from-sdl and pretty-print the result.

Then re-list /api/quality/parsers to confirm the new files appear in the
Parser Test Runner dropdown.
"""
from __future__ import annotations
import json
import sys
import time
import urllib.request
import urllib.error

BACKEND = "http://localhost:8001"
TIMEOUT = 300


def call(method: str, path: str) -> tuple[int, dict | str, float]:
    req = urllib.request.Request(BACKEND + path, method=method)
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, json.loads(r.read().decode()), time.monotonic() - t0
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            return e.code, json.loads(body), time.monotonic() - t0
        except Exception:
            return e.code, body, time.monotonic() - t0
    except Exception as e:
        return -1, f"{type(e).__name__}: {e or 'no detail'}", time.monotonic() - t0


print("=" * 72)
print("POST /api/quality/sync-from-sdl")
print("=" * 72)
status, body, elapsed = call("POST", "/api/quality/sync-from-sdl")
print(f"HTTP {status}    elapsed={elapsed:.1f}s")
if isinstance(body, dict):
    if "detail" in body:
        print(f"  ERROR: {body['detail']}")
    else:
        print(f"  downloaded: {body.get('downloaded')}")
        print(f"  errors:     {len(body.get('errors') or [])}")
        print(f"  directory:  {body.get('directory')}")
        names = body.get("parsers") or []
        print(f"\n  sample of parser filenames (first 25):")
        for n in names[:25]:
            print(f"    {n}")
        if len(names) > 25:
            print(f"    ... and {len(names) - 25} more")
        # Highlight anything that looks like a customer/custom parser
        custom = [n for n in names if "avelios" in n.lower() or "ocsf" in n.lower()]
        if custom:
            print("\n  matched custom-parser patterns (avelios / ocsf):")
            for n in custom:
                print(f"    ✓ {n}")
        errs = body.get("errors") or []
        if errs:
            print(f"\n  errors (first 5 of {len(errs)}):")
            for e in errs[:5]:
                print(f"    - {e}")
else:
    print(f"  raw: {str(body)[:600]}")

print()
print("=" * 72)
print("GET /api/quality/parsers  (Parser Test Runner dropdown source)")
print("=" * 72)
status, body, elapsed = call("GET", "/api/quality/parsers")
print(f"HTTP {status}    elapsed={elapsed:.1f}s")
if isinstance(body, dict):
    print(f"  count: {body.get('count')}")
    print(f"  parsers:")
    for n in (body.get("parsers") or [])[:50]:
        print(f"    {n}")
    if (body.get("count") or 0) > 50:
        print(f"    ... and {body['count'] - 50} more")
else:
    print(f"  raw: {str(body)[:400]}")
