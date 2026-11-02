#!/usr/bin/env bash
# Runs a full scheduled scrape immediately and prints the summary.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FUNCTION="$(terraform -chdir="$ROOT/infra" output -raw scraper_function_name)"
OUT="$(mktemp)"

aws lambda invoke \
  --function-name "$FUNCTION" \
  --cli-binary-format raw-in-base64-out \
  --cli-read-timeout 900 \
  --payload '{"source":"schedule"}' \
  "$OUT" >/dev/null

python3 -c 'import json,sys; print(json.dumps(json.load(open(sys.argv[1]))["summary"], indent=2))' "$OUT"
rm -f "$OUT"
