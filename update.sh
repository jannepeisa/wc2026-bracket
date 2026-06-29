#!/usr/bin/env bash
# Refresh odds + results, rebuild the bracket data, and push if anything moved.
# Designed to run from cron in a git clone of the wc2026-bracket repo that has a
# local (gitignored) .env carrying ODDS_API_KEY.
set -euo pipefail
# cron runs with a bare environment — pin PATH so python3/git/gh resolve.
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:${PATH:-}"
cd "$(dirname "$0")"
echo "=== update $(date -u +%FT%TZ) ==="

[ -f .env ] && { set -a; . ./.env; set +a; }

python3 refresh.py
python3 build_bracket.py

FILES="bracket_data.js bracket_data.json odds_market.json results.json"
if git diff --quiet -- $FILES; then
  echo "no data changes — nothing to publish"
  exit 0
fi

git add $FILES
git commit -q -m "data: auto-refresh odds/results $(date -u +%FT%TZ)"
git push -q
echo "published update"
