#!/usr/bin/env bash
# Download everything the pipelines need into data/raw (runs on GitHub Actions).
# Usage: scripts/ingest_all.sh YYYY-MM-DD   (the as-of date; data up to that day)
# Requires PII_HASH_SALT; SOCRATA_APP_TOKEN is optional but avoids throttling.
set -euo pipefail
AS_OF="${1:?usage: ingest_all.sh YYYY-MM-DD}"
TO=$(date -u -d "$AS_OF + 1 day" +%F)
mkdir -p data/logs

run() {
  local name="$1"; shift
  if uv run python -m procurement_risk ingest "$@" > "data/logs/ingest-$name.log" 2>&1; then
    echo "ingest $name: ok"
  else
    echo "ingest $name: FAILED"; tail -20 "data/logs/ingest-$name.log"; return 1
  fi
}

# The three downloads are independent; run them in parallel and fail if any fails.
run contracts contracts --from 2019-01-01 --to "$TO" --out data/raw & c=$!
run amendments amendments --out data/raw & a=$!
run processes processes --from 2018-07-01 --to "$TO" --out data/raw & p=$!
status=0
for pid in $c $a $p; do wait "$pid" || status=1; done
exit $status
