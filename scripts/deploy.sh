#!/usr/bin/env bash
# Full deploy: build the Lambda package, apply Terraform, publish the SPA.
#
#   ./scripts/deploy.sh            # everything
#   ./scripts/deploy.sh infra      # Terraform only (extra args go to terraform apply)
#   ./scripts/deploy.sh frontend   # SPA only
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${1:-all}"
TFVARS="$ROOT/infra/envs/prod.tfvars"

tf() { terraform -chdir="$ROOT/infra" "$@"; }

if [[ "$TARGET" == "all" || "$TARGET" == "infra" ]]; then
  "$ROOT/scripts/build_lambda.sh"
  tf init -input=false
  tf apply -input=false -var-file="$TFVARS" "${@:2}"
fi

if [[ "$TARGET" == "all" || "$TARGET" == "frontend" ]]; then
  BUCKET="$(tf output -raw site_bucket)"
  DIST="$(tf output -raw cloudfront_distribution_id)"

  echo "→ building the SPA"
  (cd "$ROOT/frontend" && npm ci --silent && npm run build)

  echo "→ publishing to s3://$BUCKET"
  # Hashed assets are immutable; index.html must never be cached.
  # config.json is owned by Terraform and must survive --delete.
  aws s3 sync "$ROOT/frontend/dist" "s3://$BUCKET" \
    --delete \
    --exclude 'index.html' --exclude 'config.json' \
    --cache-control 'public,max-age=31536000,immutable'

  aws s3 cp "$ROOT/frontend/dist/index.html" "s3://$BUCKET/index.html" \
    --cache-control 'no-cache,must-revalidate' --content-type 'text/html; charset=utf-8'

  echo "→ invalidating CloudFront"
  aws cloudfront create-invalidation --distribution-id "$DIST" --paths '/index.html' '/config.json' >/dev/null
fi

echo "✓ $(tf output -raw app_url)"
