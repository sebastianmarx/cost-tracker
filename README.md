# Cost Tracker

Personal price tracker. Add a product with one or more shop links (Amazon or
any shop that publishes structured product data); the prices are checked at
06:00 and 18:00 (Europe/Berlin) and shown as numbers and charts per shop. When
a shop drops to your target price you get an HTML email.

Full specification: **[project.md](project.md)**

- **Live at** https://costtracker.marxai.de
- **Costs** ≈ 0 USD/month (everything stays inside the AWS free tiers)
- **Reachable by** exactly one Cognito user, with mandatory TOTP MFA

## Layout

| Path | What |
| --- | --- |
| `backend/app/api` | API Lambda (HTTP API payload v2, small regex router) |
| `backend/app/scraper` | Scraper Lambda: fetch (curl_cffi + SSRF guard), parsers, SES alerts |
| `backend/app/db.py` | DynamoDB single-table repository |
| `frontend/` | Svelte 5 + Vite SPA, Chart.js, oidc-client-ts |
| `infra/` | Terraform (state in `marx-aws-tfstates`, key `cost-tracker/prod/`) |
| `scripts/` | build, deploy, scrape-now |

## Prerequisites

| Tool | Version |
| --- | --- |
| Terraform | ≥ 1.11 (native S3 state locking) |
| Python | 3.12+ locally; the Lambda package targets 3.13 / arm64 |
| Node | 22+ |
| AWS CLI | v2, credentials for account `473197088636` |

Already present in the account and reused (not managed here):

- Route 53 hosted zone `marxai.de`
- SES domain identity `familiemarx.click` (verified, DKIM, production access)
- State bucket `marx-aws-tfstates`

## First deploy

```bash
python3 -m venv backend/.venv && backend/.venv/bin/pip install -r backend/requirements-dev.txt
./scripts/deploy.sh          # build → terraform apply → publish SPA
```

The first apply takes ~10 minutes, mostly CloudFront.

Then:

```bash
# 1. Permanent password for the single user (never enters Terraform state)
aws cognito-idp admin-set-user-password \
  --user-pool-id "$(terraform -chdir=infra output -raw cognito_user_pool_id)" \
  --username sebastian.sm.marx@gmail.com \
  --password '<long password from your password manager>' \
  --permanent

# 2. Confirm the SNS subscription email (Lambda error alarms).
```

Open the app, sign in, and complete the TOTP enrolment. Register a second
authenticator as a backup.

## Day-to-day

```bash
make test              # pytest + svelte-check
make deploy            # everything
make deploy-infra      # Terraform + Lambda code
make deploy-frontend   # SPA only
make scrape-now        # run a full price check right now
make dev               # local SPA on :5173 against the deployed API
```

## Troubleshooting

- **Link shows "Blocked"**: the shop served a captcha / bot wall (Amazon does
  this to AWS IP ranges from time to time). The last known price is kept; the
  next run or a manual refresh usually works.
- **"No price found"**: the page has no JSON-LD / meta / microdata price. Open
  the link and check it is a product page (not a search or category page).
- **Logs**: `aws logs tail /aws/lambda/cost-tracker-scraper --follow`
- **Locked out (lost MFA device)**:
  `aws cognito-idp admin-set-user-mfa-preference --user-pool-id … --username … --software-token-mfa-settings Enabled=false`
  then sign in and enrol again.
