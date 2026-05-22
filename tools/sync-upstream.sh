#!/usr/bin/env bash
# tools/sync-upstream.sh
# Pull the latest changes from upstream (mickbrowns1/SIEM-Toolkit) while
# preserving the fork's improvements, then verify the fork invariants
# still hold. Designed to be safe to run repeatedly.
#
# Usage:
#   ./tools/sync-upstream.sh                  # rebase (clean linear history)
#   ./tools/sync-upstream.sh --merge          # merge-commit instead of rebase
#   ./tools/sync-upstream.sh --no-rebuild     # skip docker rebuild + verify
#   ./tools/sync-upstream.sh --no-push        # don't auto-push at the end
#   ./tools/sync-upstream.sh --dry-run        # show what would happen
#
# Exit codes:
#   0  fully up-to-date or sync succeeded and all invariants pass
#   1  pre-condition failed (dirty tree, wrong remote, etc.)
#   2  merge / rebase conflicts (resolve manually, then re-run with --resume)
#   3  one or more fork invariants regressed after sync

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_DIR"

# --- defaults -----------------------------------------------------------
MODE=rebase
DO_REBUILD=1
DO_PUSH=1
DRY_RUN=0
UPSTREAM_REMOTE="${UPSTREAM_REMOTE:-upstream}"
UPSTREAM_BRANCH="${UPSTREAM_BRANCH:-main}"
ORIGIN_REMOTE="${ORIGIN_REMOTE:-origin}"
BACKEND_URL="${BACKEND_URL:-http://localhost:8001}"
BACKEND_CONTAINER="${BACKEND_CONTAINER:-siem-toolkit-patched-backend-1}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --merge)      MODE=merge ;;
        --no-rebuild) DO_REBUILD=0 ;;
        --no-push)    DO_PUSH=0 ;;
        --dry-run)    DRY_RUN=1; DO_REBUILD=0; DO_PUSH=0 ;;
        -h|--help)
            sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *) echo "unknown arg: $1" >&2; exit 1 ;;
    esac
    shift
done

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
red()  { printf '\033[31m%s\033[0m\n' "$*"; }
green(){ printf '\033[32m%s\033[0m\n' "$*"; }
yellow(){ printf '\033[33m%s\033[0m\n' "$*"; }

# --- 1. pre-conditions --------------------------------------------------
bold "== 1. pre-conditions =="
if ! git remote get-url "$UPSTREAM_REMOTE" >/dev/null 2>&1; then
    red "no '$UPSTREAM_REMOTE' remote configured. Add with:"
    echo "  git remote add upstream https://github.com/mickbrowns1/SIEM-Toolkit.git"
    exit 1
fi
echo "  upstream remote   : $(git remote get-url "$UPSTREAM_REMOTE")"
echo "  origin remote     : $(git remote get-url "$ORIGIN_REMOTE")"

if [[ -n "$(git status --porcelain)" ]]; then
    red "working tree is not clean. Commit or stash changes first:"
    git status -s
    exit 1
fi
green "  working tree clean"

CUR_BRANCH=$(git rev-parse --abbrev-ref HEAD)
echo "  current branch    : $CUR_BRANCH"

# --- 2. snapshot --------------------------------------------------------
SAFETY_TAG="safety/$(date +%Y%m%d-%H%M%S)"
bold "== 2. safety tag =="
if [[ "$DRY_RUN" == 1 ]]; then
    echo "  [dry-run] would create tag $SAFETY_TAG"
else
    git tag "$SAFETY_TAG"
    echo "  created $SAFETY_TAG"
fi

# --- 3. fetch upstream --------------------------------------------------
bold "== 3. fetch upstream =="
git fetch "$UPSTREAM_REMOTE" --quiet
echo "  fetched ${UPSTREAM_REMOTE}/${UPSTREAM_BRANCH}"

HEAD_SHA=$(git rev-parse HEAD)
UP_SHA=$(git rev-parse "${UPSTREAM_REMOTE}/${UPSTREAM_BRANCH}")
MB=$(git merge-base HEAD "${UPSTREAM_REMOTE}/${UPSTREAM_BRANCH}")

NEW_COUNT=$(git rev-list --count "${MB}..${UPSTREAM_REMOTE}/${UPSTREAM_BRANCH}")
OUR_COUNT=$(git rev-list --count "${MB}..HEAD")

echo "  HEAD              : $HEAD_SHA"
echo "  upstream/$UPSTREAM_BRANCH : $UP_SHA"
echo "  merge-base        : $MB"
echo "  upstream commits  : $NEW_COUNT new"
echo "  our commits ahead : $OUR_COUNT"

if [[ "$NEW_COUNT" == 0 ]]; then
    green "== already current with upstream =="
    NEW_SYNC=0
else
    NEW_SYNC=1
    bold "-- new upstream commits --"
    git log --oneline "${MB}..${UPSTREAM_REMOTE}/${UPSTREAM_BRANCH}"
fi

# --- 4. apply (rebase or merge) ----------------------------------------
if [[ "$NEW_SYNC" == 1 ]]; then
    bold "== 4. applying upstream changes ($MODE) =="
    if [[ "$DRY_RUN" == 1 ]]; then
        echo "  [dry-run] would $MODE $UPSTREAM_REMOTE/$UPSTREAM_BRANCH into $CUR_BRANCH"
    else
        if [[ "$MODE" == "rebase" ]]; then
            if ! git rebase "${UPSTREAM_REMOTE}/${UPSTREAM_BRANCH}"; then
                red "rebase has conflicts."
                echo "Resolve, then run: git rebase --continue"
                echo "Or abort with     : git rebase --abort"
                echo "Recover snapshot  : git reset --hard $SAFETY_TAG"
                exit 2
            fi
        else
            if ! git merge --no-ff "${UPSTREAM_REMOTE}/${UPSTREAM_BRANCH}" \
                 -m "Sync upstream $(date +%Y-%m-%d)"; then
                red "merge has conflicts."
                echo "Resolve, then commit. Recover with: git reset --hard $SAFETY_TAG"
                exit 2
            fi
        fi
        green "  ${MODE} succeeded"
    fi
fi

# --- 5. rebuild + verify invariants ------------------------------------
if [[ "$DO_REBUILD" == 1 ]]; then
    bold "== 5. rebuild backend + run invariants =="

    docker compose up -d --force-recreate --build backend 2>&1 | tail -5
    echo "  waiting 15s for startup..."
    sleep 15

    FAILS=0

    check() {
        local label="$1" cmd="$2" expect="$3"
        local got
        got="$(eval "$cmd" 2>/dev/null || echo '<error>')"
        if [[ "$got" == "$expect" ]]; then
            green "  PASS  $label  ($got)"
        else
            red   "  FAIL  $label  expected='$expect' got='$got'"
            FAILS=$((FAILS + 1))
        fi
    }

    # Invariant 1: Parser dropdown excludes ueba_* artefacts (fix 70f3f83)
    check "parser dropdown excludes ueba_*" \
        "curl -fsS $BACKEND_URL/api/quality/parsers | python3 -c 'import sys,json; d=json.load(sys.stdin); print(sum(1 for p in d[\"parsers\"] if p.lower().startswith(\"ueba\")))'" \
        "0"

    # Invariant 2: MITRE coverage is <= 100 (fix f821151)
    check "mitre_pct <= 100" \
        "curl -fsS $BACKEND_URL/api/coverage/health | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d[\"mitre_pct\"] <= 100)'" \
        "True"

    # Invariant 3: ingest cache endpoints exist (fix 0a01a56)
    check "/api/ingest/cache-stats exists" \
        "curl -fsS -o /dev/null -w '%{http_code}' $BACKEND_URL/api/ingest/cache-stats" \
        "200"

    # Invariant 4: /sample-unlabelled is registered as a POST route (port from
    # upstream sync). GET to it should return 405 Method Not Allowed (route
    # exists, wrong method) rather than 404 (route missing).
    # Note: -f is omitted because 405 is the expected non-2xx status here.
    check "/api/quality/sample-unlabelled registered" \
        "curl -sS -o /dev/null -w '%{http_code}' -X GET $BACKEND_URL/api/quality/sample-unlabelled" \
        "405"

    # Invariant 5: prewarmer scheduled (fix fec3568) — only if INGEST_PREWARM=1.
    # Poll up to 30s because the task logs 'starting' a few seconds after the
    # FastAPI startup phase finishes (postgres + lib autoload first).
    if grep -q '^INGEST_PREWARM=1' .env 2>/dev/null; then
        prewarm_ok=0
        for _ in 1 2 3 4 5 6; do
            if docker logs "$BACKEND_CONTAINER" 2>&1 | grep -q 'prewarmer:.*starting'; then
                prewarm_ok=1; break
            fi
            sleep 5
        done
        if [[ "$prewarm_ok" == 1 ]]; then
            green "  PASS  prewarmer started"
        else
            red   "  FAIL  prewarmer did not log 'starting' within 30s (INGEST_PREWARM=1 but task missing)"
            FAILS=$((FAILS + 1))
        fi
    else
        yellow "  SKIP  prewarmer (INGEST_PREWARM not enabled in .env)"
    fi

    if [[ "$FAILS" -gt 0 ]]; then
        red "== $FAILS invariant(s) regressed after sync =="
        echo "Recover the pre-sync state with: git reset --hard $SAFETY_TAG"
        exit 3
    fi
    green "  all invariants pass"
fi

# --- 6. push -----------------------------------------------------------
if [[ "$DO_PUSH" == 1 && "$NEW_SYNC" == 1 ]]; then
    bold "== 6. push to $ORIGIN_REMOTE/$CUR_BRANCH =="
    git push "$ORIGIN_REMOTE" "$CUR_BRANCH" --force-with-lease
    green "  pushed"
fi

bold "== done =="
echo "  branch        : $CUR_BRANCH"
echo "  HEAD          : $(git rev-parse --short HEAD)"
echo "  safety snapshot: $SAFETY_TAG  (delete with: git tag -d $SAFETY_TAG)"
