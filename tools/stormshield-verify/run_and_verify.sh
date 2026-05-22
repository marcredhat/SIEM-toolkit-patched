#!/usr/bin/env bash
set -e
cd /tmp/stormshield-verify
echo "============ STEP 1: send burst ============"
python3 send_burst.py
echo
echo "============ STEP 2: wait 40s for ingest ============"
sleep 40
echo
echo "============ STEP 3: query SDL ============"
python3 verify_query.py
