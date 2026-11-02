# Cost Tracker — Project Plan

Personal price tracker. A **product** holds one or more **links** to online shops (Amazon and others). The system checks every link twice a day, stores each price point, and shows the current price plus the price history (numbers and charts) per link/shop. Price alerts go out as HTML emails via SES.

- URL: `https://costtracker.marxai.de`
- Single user, login required (Cognito + MFA)
- AWS, fully serverless, infrastructure in Terraform
- Backend: Python 3.13 · Frontend: Svelte 5 + Vite + TypeScript + Chart.js

---

## 1. Goals and Non-Goals

### Goals
1. Add/edit/delete products; each product has 1..n shop links.
2. Automatic price checks at **06:00 and 18:00 (Europe/Berlin)**.
3. **Manual refresh** button: per link and "refresh all".
4. Show per link: current price, last checked, status, min/max/avg over 30/90/180/365 days, and a chart with one line per shop.
5. Target price per product → **HTML email alert via SES** when a link drops to or below it.
6. **Minimal cost** (target < 1 $/month, excluding the domain).
7. **Secure by default**: private storage, authenticated API, least-privilege IAM, MFA.

### Non-Goals (v1)
- Multi-user / sign-up.
- Guaranteed Amazon scraping (best effort; see Risks).
- Browser extension, mobile app, currency conversion between shops.

---

## 2. Architecture

```
                           ┌──────────────────────────────────────────────┐
 Browser ──HTTPS──────────▶│ CloudFront  costtracker.marxai.de    │
   │                       │  ACM cert (us-east-1), TLS 1.2+, sec headers │
   │                       ├───────────────┬──────────────────────────────┤
   │                       │ /*            │ /api/*                       │
   │                       ▼               ▼                              │
   │              S3 bucket (private,   API Gateway HTTP API              │
   │              OAC only): SPA +      JWT authorizer (Cognito)          │
   │              config.json              │                              │
   │                                       ▼                              │
   │                               Lambda "api" (Python, arm64)           │
   │                                 │        │ invoke (sync/async)       │
   │                                 │        ▼                           │
   │                                 │   Lambda "scraper" (Python, arm64) │
   │                                 │        │   ▲          │            │
   │                                 ▼        ▼   │          ▼            │
   │                              DynamoDB (on-demand)   SES (HTML mail)  │
   │                                              │                       │
   │                     EventBridge Scheduler ───┘                       │
   │                     cron(0 6,18 * * ? *) Europe/Berlin               │
   │                                                                      │
   └──OIDC (auth code + PKCE)──▶ Cognito User Pool (managed login, MFA)   │
                                                                          │
                                 Route53 zone marxai.de   ──────────┘
```

### Why this stack
| Choice | Reason |
|---|---|
| S3 + CloudFront for SPA | Static hosting costs cents; CloudFront free tier 1 TB/month; free TLS via ACM. |
| Same-origin `/api/*` via CloudFront | No CORS configuration, one domain, one CSP. |
| API Gateway **HTTP API** (not REST API) | ~70% cheaper, built-in JWT authorizer. |
| Lambda arm64 | ~20% cheaper than x86, pay only when running. |
| DynamoDB on-demand | No idle cost, 25 GB free storage; data volume is tiny. |
| Cognito | Free for a single user, provides MFA, hosted login, no password handling in our code. |
| EventBridge **Scheduler** | Native time-zone support (`Europe/Berlin`, DST-safe), free tier 14M invocations. |
| SES | 0.10 $ / 1000 mails; proper DKIM/SPF/DMARC → emails do not land in spam. |
| Svelte 5 + Vite | Tiny bundle, simple reactivity, static build, no SSR server needed. |
| Chart.js (+ date adapter) | Small, good time-series line charts, tooltips, responsive. |
| No VPC / NAT | NAT Gateway alone would be ~35 $/month. Lambdas run outside a VPC. |

### Region
- Main region: **`eu-central-1` (Frankfurt)**.
- `us-east-1` only for the CloudFront ACM certificate (provider alias `aws.us_east_1`).

---

## 3. Data Model (DynamoDB, single table `cost-tracker`)

- Billing: `PAY_PER_REQUEST`
- Encryption: AWS-owned key (default, free)
- PITR: off (cost); optional weekly on-demand backup can be added later
- Keys: `PK` (S), `SK` (S); GSI `GSI1` on `GSI1PK` (S) / `GSI1SK` (S), projection ALL

| Entity | PK | SK | GSI1PK | GSI1SK | Attributes |
|---|---|---|---|---|---|
| Product | `PRODUCT#<pid>` | `META` | `PRODUCT` | `<created_at>` | `name`, `image_url`, `target_price` (N, optional), `currency`, `created_at`, `updated_at` |
| Link | `PRODUCT#<pid>` | `LINK#<lid>` | `LINK` | `<lid>` | `url`, `shop` (e.g. `amazon.de`), `title`, `currency`, `last_price` (N), `last_in_stock` (BOOL), `last_checked` (ISO), `last_status` (`ok`/`blocked`/`parse_error`/`http_error`), `last_error`, `last_notified_price` (N), `product_id` |
| Price point | `LINK#<lid>` | `PRICE#<iso-ts>` | – | – | `price` (N), `currency`, `in_stock` (BOOL), `product_id` |

IDs: ULID (sortable, URL-safe). Prices stored as `Decimal` (DynamoDB Number), never float.

### Access patterns
| Pattern | Operation |
|---|---|
| List all products | Query `GSI1` `GSI1PK = PRODUCT` |
| Product + its links | Query `PK = PRODUCT#<pid>` |
| All links (scheduler) | Query `GSI1` `GSI1PK = LINK` |
| Link history for last N days | Query `PK = LINK#<lid>` and `SK BETWEEN PRICE#<from> AND PRICE#<to>` |
| Delete product | Query product items + history per link → `BatchWriteItem` delete |

Volume estimate: 50 links × 2 checks/day × 365 days ≈ 36,500 items/year ≈ a few MB. No TTL; history is kept forever.

---

## 4. Backend (Python 3.13, arm64)

### 4.1 Libraries
| Library | Use |
|---|---|
| `boto3` (from runtime) | DynamoDB, SES, Lambda invoke |
| `pydantic` v2 | Request validation / response models |
| `aws-lambda-powertools` | Router for HTTP API events, structured logging, tracing off |
| `curl_cffi` | HTTP client with browser TLS/HTTP2 fingerprint impersonation (important for Amazon) |
| `selectolax` | Fast HTML parsing (CSS selectors) |
| `jinja2` | HTML email templates |
| `python-ulid` | IDs |
| Dev: `pytest`, `moto`, `ruff`, `mypy` | Tests, lint, types |

### 4.2 Lambda `api`
- Memory 256 MB, timeout 29 s, arm64, log retention 14 days.
- Env: `TABLE_NAME`, `SCRAPER_FUNCTION_NAME`, `REFRESH_MIN_INTERVAL_SECONDS=300`.
- Every route requires a valid Cognito access token (enforced by API Gateway authorizer; the Lambda additionally checks the `sub` claim against the configured owner `sub` as defense in depth).

#### API specification
All paths under `/api`. JSON in/out. Errors: `{"error": "<code>", "message": "..."}`.

| Method | Path | Body | Response | Notes |
|---|---|---|---|---|
| GET | `/products` | – | `[ProductSummary]` | Name, image, target, best current price + shop, 30-day change %, links count, worst link status |
| POST | `/products` | `{name, target_price?, links: [url]}` | `Product` (201) | Creates product + links, triggers async scrape of new links |
| GET | `/products/{pid}` | – | `Product` with `links[]` and per-link `stats` | |
| PUT | `/products/{pid}` | `{name?, target_price?, image_url?}` | `Product` | `target_price: null` removes alert |
| DELETE | `/products/{pid}` | – | 204 | Deletes links and history |
| POST | `/products/{pid}/links` | `{url}` | `Link` (201) | Triggers async scrape |
| DELETE | `/products/{pid}/links/{lid}` | – | 204 | Deletes link and history |
| GET | `/links/{lid}/history?days=90` | – | `{link_id, currency, points: [{ts, price, in_stock}]}` | `days` ∈ {30, 90, 180, 365, 0=all} |
| POST | `/links/{lid}/refresh` | – | `Link` (updated) | **Synchronous** scrape (scraper invoked `RequestResponse`); 429 if checked < 5 min ago |
| POST | `/refresh` | – | 202 `{queued: n}` | **Async** scrape of all links (`Event` invoke); UI polls `GET /products` |

`stats` per link: `current`, `min`, `max`, `avg` for 30/90/180/365 days, `all_time_low` (+ date), `change_30d_pct`.

#### Validation rules
- `name`: 1–120 chars. `target_price`: 0 < x < 1,000,000, 2 decimals.
- `url`: max 2048 chars, scheme `https` (or `http`), hostname must not be an IP literal, max 10 links per product, max 200 links total.

### 4.3 Lambda `scraper`
- Memory 512 MB, timeout 300 s, reserved concurrency 2 (caps cost and parallel hits on shops).
- Env: `TABLE_NAME`, `SES_FROM`, `ALERT_TO`, `APP_URL`.
- Input events:
  - Scheduler: `{"source": "schedule"}` → all links.
  - API: `{"link_ids": ["..."], "mode": "manual"}`.
- Flow per link:
  1. SSRF check (see Security).
  2. Fetch with `curl_cffi` (`impersonate="chrome"`), headers `Accept-Language: de-DE,de;q=0.9,en;q=0.8`, timeout 15 s, max 3 redirects, max body 5 MB.
  3. Pick parser by hostname (`amazon.*` → Amazon parser, else generic).
  4. On success: write price point, update link (`last_*`), run alert check.
  5. On failure: keep `last_price`, set `last_status` + `last_error`, no price point written.
  6. Between links: random delay 2–6 s; links of the same shop are spread out (shuffle).
  7. One retry on network error / 5xx / captcha with a different impersonation profile.
- On first scrape of a new link: fill `title` and, if the product has none, `image_url` (from `og:image` / Amazon `#landingImage`).

### 4.4 Parsers
Each parser returns `ParseResult(price: Decimal | None, currency: str | None, in_stock: bool | None, title: str | None, image_url: str | None)` or raises `Blocked` / `ParseError`.

**Amazon parser** (`amazon.de`, `amazon.com`, …)
- Captcha / robot check detection: `form[action*="validateCaptcha"]`, title "Robot Check", `/errors/validateCaptcha` → `Blocked`.
- Price selectors (first hit wins):
  1. `#corePrice_feature_div .a-price .a-offscreen`
  2. `#corePriceDisplay_desktop_feature_div .a-price .a-offscreen`
  3. `#apex_desktop .a-price .a-offscreen`
  4. `#priceblock_ourprice`, `#priceblock_dealprice`, `#price_inside_buybox`
  5. `input#twister-plus-price-data-price` (value attribute)
- Availability: `#availability` text ("Derzeit nicht verfügbar", "Currently unavailable") → `in_stock=False`.
- Title: `#productTitle`. Image: `#landingImage[data-old-hires]` or `src`.
- URL normalization: reduce to `https://www.amazon.de/dp/<ASIN>` (strips tracking params, better cache behavior).

**Generic parser** (in this order)
1. JSON-LD `<script type="application/ld+json">`: find `@type` Product (also inside `@graph`, lists) → `offers` (Offer / AggregateOffer / list) → `price` / `lowPrice`, `priceCurrency`, `availability`.
2. Meta tags: `product:price:amount` / `og:price:amount` + `...:currency`.
3. Microdata: `[itemprop=price]` (`content` attr or text), `[itemprop=priceCurrency]`.
4. Otherwise → `ParseError("no price found")`.

**Price normalization** (`parse_price(text)`)
- Handles `1.299,99 €`, `€1,299.99`, `1 299,99`, `EUR 12,-`, `12.99`.
- Rule: the last separator followed by exactly 1–2 digits is the decimal separator; others are thousands separators.
- Currency from symbol/ISO code; default from shop TLD (`.de` → EUR).

Every parser is covered by saved HTML fixtures in `backend/tests/fixtures/`.

### 4.5 Alerts (`notify.py`)
Condition, evaluated after each successful price point:
```
if target_price is set and price <= target_price:
    if last_notified_price is None or price < last_notified_price:
        send email; last_notified_price = price
elif price > target_price:
    last_notified_price = None        # re-arm for next crossing
```
- One email per crossing / further drop, not every run.
- Email content (Jinja2 HTML + plain-text part):
  - Subject: `📉 <Product> jetzt <price> bei <shop>`
  - Header with product image and name
  - Big new price, old price struck through, drop in % and €
  - Target price, all-time low indicator
  - Small inline table of all links of the product with current prices
  - Button "Zum Angebot" (shop link) and "Im Cost Tracker öffnen" (`APP_URL/products/<pid>`)
  - Table-based layout, inline CSS (email-client safe), dark-mode friendly colors
- Optional (v1.1): mail on scraping failures for > 3 consecutive runs.

---

## 5. Frontend (Svelte 5 + Vite + TypeScript)

### 5.1 Libraries
- `svelte` 5, `vite`, `typescript`
- `oidc-client-ts` — Cognito Authorization Code + PKCE
- `chart.js` + `chartjs-adapter-date-fns` + `date-fns`
- Router: `svelte-spa-router` (hash-less via CloudFront 404→`index.html` rewrite) or small custom router
- Styling: plain CSS with CSS variables (light/dark), no heavy UI framework

### 5.2 Pages
| Route | Content |
|---|---|
| `/` Dashboard | Product cards: image, name, best current price + shop, 30-day change badge (green/red), sparkline, status badge if a link is `blocked`/`error`; button "Refresh all"; button "Add product" |
| `/products/:id` | Header (name, image, target price edit). Chart: one line per shop, range buttons 1M / 3M / 6M / 1Y / All, dashed horizontal line for target price, tooltips with date + price. Table per link: shop, current price, in stock, min/max/avg (selected range), all-time low, last checked, status, **refresh button**, open link, delete link. Form "Add link". |
| `/products/new` (modal) | Name, target price (optional), 1..n URLs |
| `/callback` | OIDC redirect handler |

### 5.3 Auth flow
1. App loads `/config.json` (written by Terraform): `{ region, userPoolId, clientId, cognitoDomain, redirectUri }`.
2. No valid session → redirect to Cognito managed login (username + password + TOTP).
3. Callback exchanges code (PKCE) → access/id/refresh token.
4. Tokens kept in `localStorage` (session survives closing the tab/browser); silent renew via refresh token until explicit sign-out.
5. API calls send `Authorization: Bearer <access_token>`; 401 → re-login.

### 5.4 Local development
- `npm run dev` with Vite proxy `/api` → deployed CloudFront URL (real Cognito, real API).
- Cognito app client includes `http://localhost:5173/callback` as an extra callback URL (variable, can be removed for prod).

---

## 6. Security

| Area | Measure |
|---|---|
| Authentication | Cognito User Pool: self-sign-up **disabled**, user created by admin (`make create-user`), password policy min 14 chars w/ all classes, **TOTP MFA required**, account recovery via email only. |
| OAuth | Public app client, **no client secret**, Authorization Code + PKCE only (implicit flow disabled), scopes `openid email`, access/id token 60 min, refresh token 3650 days (Cognito max), token revocation enabled, prevent user existence errors. |
| API | HTTP API JWT authorizer on **every** route (issuer + audience checked), default route denies; owner `sub` check in Lambda; stage throttling burst 10 / rate 5 rps; payload size limits in validation. |
| Rate limits | Manual refresh ≥ 5 min per link; scraper reserved concurrency 2. |
| S3 | Block Public Access (all four), bucket policy only for CloudFront OAC (`aws:SourceArn` = distribution), deny non-TLS (`aws:SecureTransport`), SSE-S3, versioning on. |
| CloudFront | `redirect-to-https`, min protocol `TLSv1.2_2021`, HTTP/2+3, response headers policy: HSTS (1 year, includeSubDomains, preload), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy` restrictive, CSP (below). `/api/*` behavior: caching disabled, forward `Authorization` header, all methods. |
| CSP | `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' https: data:; connect-src 'self' https://<cognito-domain>; frame-ancestors 'none'; base-uri 'self'; form-action 'self' https://<cognito-domain>; object-src 'none'` |
| SSRF (scraper fetches user URLs) | Allow only `http/https`, ports 80/443; resolve DNS and reject private, loopback, link-local (incl. `169.254.0.0/16`), CGNAT, multicast, IPv6 ULA/link-local; re-check on each redirect; max 3 redirects; 5 MB body cap; 15 s timeout. Lambda has no VPC access anyway. |
| XSS | Svelte escapes by default; no `{@html}` with scraped data; scraped titles/URLs sanitized before storage; image URLs only `https:`. |
| Email | Only sends to the configured `ALERT_TO`; HTML template autoescaping on. |
| IAM | One role per Lambda. `api`: DynamoDB CRUD on table + GSI, `lambda:InvokeFunction` on scraper only. `scraper`: DynamoDB on table + GSI, `ses:SendEmail`/`SendRawEmail` restricted to the domain identity and `ses:FromAddress` condition. Scheduler role: invoke scraper only. |
| Secrets | None required. Config via env vars/Terraform variables. No credentials in repo; `.gitignore` for `*.tfvars`, `.terraform/`, `dist/`, `build/`. |
| Terraform state | S3 bucket (versioned, SSE, public access blocked, TLS-only), native S3 locking `use_lockfile = true`. |
| Observability | CloudWatch Logs 14 days; CloudWatch alarm on scraper errors (free tier: 10 alarms) → SNS email optional. |
| Cost safety | **AWS Budget** 3 $/month with email alert at 80 % actual and 100 % forecast (first 2 budgets free). |
| Dependencies | Pinned versions (`requirements.txt` with hashes, `package-lock.json`), `pip-audit` + `npm audit` in `make check`. |
| Accepted trade-off | No AWS WAF (≥ 5 $/month + request fees). Mitigated by Cognito auth, JWT authorizer, throttling, budget alarm. |

---

## 7. SES Setup

- Domain identity: `familiemarx.click` (Terraform `aws_sesv2_email_identity`).
- Easy DKIM (RSA 2048): 3 CNAME records in Route53.
- Custom MAIL FROM: `mail.familiemarx.click` → MX `feedback-smtp.eu-central-1.amazonses.com` + SPF TXT `v=spf1 include:amazonses.com ~all`.
- DMARC TXT on `_dmarc.familiemarx.click`: `v=DMARC1; p=quarantine; rua=mailto:<alert_email>` (only if no DMARC record exists yet — check first).
- Sender: `Cost Tracker <costtracker@familiemarx.click>`.
- Recipient: `var.alert_email`, verified as email identity (confirmation link sent once).
- SES stays in **sandbox**: sending to verified addresses only is exactly our use case → no production-access request needed.
- Configuration set with bounce/complaint suppression (account-level suppression list).

---

## 8. Infrastructure (Terraform)

Requirements: Terraform ≥ 1.10, AWS provider `~> 6.0`. Default tags: `Project=cost-tracker`, `ManagedBy=terraform`.

### 8.1 Layout
```
infra/
├── bootstrap/            # one-time: state bucket (local state)
│   └── main.tf
├── versions.tf           # terraform + providers (aws, aws.us_east_1), default_tags
├── backend.tf            # s3 backend, use_lockfile = true
├── variables.tf          # region, domain, subdomain, alert_email, admin_email, extra_callback_urls, budget_amount
├── locals.tf
├── dns_cert.tf           # data aws_route53_zone, ACM cert (us-east-1) + DNS validation
├── frontend.tf           # S3 bucket + policy, OAC, CloudFront distribution, headers policy, CF function (SPA rewrite), Route53 A/AAAA alias, config.json object
├── auth.tf               # Cognito user pool, domain (prefix), app client
├── dynamodb.tf           # table + GSI1
├── lambda.tf             # IAM roles/policies, log groups, api + scraper functions
├── api.tf                # HTTP API, JWT authorizer, integration, routes, stage + throttling, lambda permission
├── scheduler.tf          # EventBridge Scheduler schedule (Europe/Berlin) + role
├── ses.tf                # domain identity, DKIM, MAIL FROM, DMARC, recipient identity, config set
├── monitoring.tf         # budget, scraper error alarm
├── outputs.tf            # url, user_pool_id, client_id, bucket, distribution_id
└── terraform.tfvars.example
```

### 8.2 Key resource notes
- **CloudFront**
  - Origins: S3 (OAC, sigv4) and API Gateway (`<api-id>.execute-api.eu-central-1.amazonaws.com`, HTTPS only).
  - Default behavior (S3): managed `CachingOptimized`, CloudFront Function on viewer-request rewrites non-file paths to `/index.html` (SPA routing).
  - `/api/*` behavior: managed `CachingDisabled`, origin request policy `AllViewerExceptHostHeader`, allowed methods all.
  - `price_class = "PriceClass_100"` (EU/NA only, cheapest).
  - `index.html` + `config.json` served with `Cache-Control: no-cache`; hashed assets `max-age=31536000, immutable`.
- **Cognito**: `user_pool_tier = "LITE"`, `mfa_configuration = "ON"`, `software_token_mfa_configuration { enabled = true }`, `admin_create_user_config { allow_admin_create_user_only = true }`, managed login (branding v2), prefix domain `costtracker-familiemarx`, callback `https://costtracker.marxai.de/callback`, logout `https://costtracker.marxai.de/`.
- **Scheduler**: `schedule_expression = "cron(0 6,18 * * ? *)"`, `schedule_expression_timezone = "Europe/Berlin"`, flexible window off, retry policy 1 attempt, input `{"source":"schedule"}`.
- **Lambda**: code from `build/api.zip`, `build/scraper.zip` (`source_code_hash = filebase64sha256(...)`), runtime `python3.13`, `architectures = ["arm64"]`.
- **Route53**: existing zone via `data "aws_route53_zone" "main" { name = "marxai.de" }` — zone is **not** managed by this project.

### 8.3 Variables (`terraform.tfvars`, not committed)
```hcl
region        = "eu-central-1"
root_domain   = "marxai.de"
subdomain     = "costtracker"
alert_email   = "you@example.com"
admin_email   = "you@example.com"
budget_amount = 3
extra_callback_urls = ["http://localhost:5173/callback"]
```

---

## 9. Repository Structure

```
cost_tracker/
├── project.md
├── README.md
├── Makefile
├── .gitignore
├── infra/                       # see 8.1
├── backend/
│   ├── pyproject.toml           # ruff, mypy, pytest config
│   ├── requirements.txt         # runtime deps (pinned, hashed)
│   ├── requirements-dev.txt
│   ├── src/
│   │   ├── common/
│   │   │   ├── db.py            # table access, key builders, repository functions
│   │   │   ├── models.py        # pydantic models
│   │   │   ├── stats.py         # min/max/avg/change calculation
│   │   │   └── config.py
│   │   ├── api/
│   │   │   └── handler.py       # powertools APIGatewayHttpResolver routes
│   │   └── scraper/
│   │       ├── handler.py
│   │       ├── fetch.py         # curl_cffi client + SSRF guard
│   │       ├── price.py         # parse_price normalization
│   │       ├── notify.py        # SES + jinja2
│   │       ├── templates/
│   │       │   ├── alert.html.j2
│   │       │   └── alert.txt.j2
│   │       └── parsers/
│   │           ├── __init__.py  # parser registry by hostname
│   │           ├── amazon.py
│   │           └── generic.py
│   └── tests/
│       ├── fixtures/            # saved HTML pages (amazon_de_*.html, jsonld_*.html, ...)
│       ├── test_price.py
│       ├── test_parsers.py
│       ├── test_ssrf.py
│       ├── test_alerts.py
│       ├── test_stats.py
│       └── test_api.py          # moto-backed
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── index.html
│   └── src/
│       ├── main.ts
│       ├── App.svelte
│       ├── lib/
│       │   ├── auth.ts          # oidc-client-ts wrapper
│       │   ├── api.ts           # typed fetch client
│       │   ├── config.ts
│       │   └── format.ts        # currency/date formatting (de-DE)
│       ├── components/
│       │   ├── ProductCard.svelte
│       │   ├── PriceChart.svelte
│       │   ├── Sparkline.svelte
│       │   ├── LinkTable.svelte
│       │   ├── StatusBadge.svelte
│       │   └── ProductForm.svelte
│       └── routes/
│           ├── Dashboard.svelte
│           ├── ProductDetail.svelte
│           └── Callback.svelte
└── scripts/
    ├── build_lambda.sh          # builds build/api.zip and build/scraper.zip for arm64
    └── create_user.sh           # admin-create-user + temp password
```

---

## 10. Build and Deploy

### Prerequisites
- AWS CLI v2 with a profile for the target account
- Terraform ≥ 1.10, Python 3.13, Node 22 LTS, `make`, `zip`
- Route53 hosted zone `marxai.de` exists in the account

### Lambda packaging (`scripts/build_lambda.sh`)
```bash
pip install -r backend/requirements.txt \
  --platform manylinux2014_aarch64 --implementation cp --python-version 3.13 \
  --only-binary=:all: --target build/scraper_pkg
cp -r backend/src/common backend/src/scraper build/scraper_pkg/
(cd build/scraper_pkg && zip -qr ../scraper.zip .)
# same for api (without curl_cffi/selectolax/jinja2)
```

### Makefile targets
| Target | Action |
|---|---|
| `make bootstrap` | `terraform -chdir=infra/bootstrap apply` (state bucket, once) |
| `make test` | `ruff`, `mypy`, `pytest`, `npm run check` |
| `make check` | `pip-audit`, `npm audit` |
| `make build` | Lambda zips + `npm run build` |
| `make plan` / `make apply` | Terraform in `infra/` |
| `make deploy-frontend` | `aws s3 sync frontend/dist s3://<bucket> --delete` with cache headers + CloudFront invalidation `/index.html /config.json` |
| `make deploy` | `build` → `apply` → `deploy-frontend` |
| `make create-user` | `aws cognito-idp admin-create-user` (temp password, MFA setup at first login) |
| `make scrape-now` | `aws lambda invoke` scraper with `{"source":"schedule"}` |

### First deployment
1. `make bootstrap`
2. Copy `infra/terraform.tfvars.example` → `terraform.tfvars`, fill values.
3. `make deploy` (ACM + SES DKIM validation may take a few minutes).
4. Click SES verification link in the alert mailbox.
5. `make create-user`, log in, set new password, scan TOTP QR code.
6. Add first product.

### CI (optional, later)
GitHub Actions with OIDC role (no long-lived keys): `test` on PR; `deploy` on `main`.

---

## 11. Cost Estimate (per month, single user, ~50 links)

| Service | Usage | Cost |
|---|---|---|
| Route53 hosted zone | existing zone | 0.50 $ (already paid) |
| Domain `familiemarx.click` | existing | already paid |
| CloudFront | < 1 GB, < 100k requests | 0 $ (always-free 1 TB / 10M req) |
| S3 | < 5 MB | ~0.00 $ |
| API Gateway HTTP API | < 10k requests | ~0.01 $ |
| Lambda | ~3,000 invocations, < 10k GB-s | 0 $ (always-free tier) |
| DynamoDB | < 100 MB, few k R/W | 0 $ (25 GB free) |
| EventBridge Scheduler | 60 invocations | 0 $ |
| Cognito (Lite) | 1 MAU | 0 $ |
| SES | < 100 mails | ~0.01 $ |
| ACM | public cert | 0 $ |
| CloudWatch Logs | < 100 MB, 14 d retention | 0 $ (5 GB free) |
| AWS Budgets | 1 budget | 0 $ |
| **Total** | | **≈ 0.02 $ + existing Route53 zone** |

Cost killers deliberately avoided: NAT Gateway, VPC endpoints, WAF, Secrets Manager (use env vars/SSM if ever needed), provisioned DynamoDB, REST API Gateway, PITR.

---

## 12. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Amazon blocks/captchas AWS IPs | No Amazon prices some runs | `curl_cffi` browser impersonation, realistic headers, low frequency (2×/day), jitter, retry; status `blocked` shown in UI, last known price kept; manual refresh. **Fallback v2**: run the same scraper locally (home IP) via `make scrape-local` writing to DynamoDB, or Amazon PA-API if an Associates account becomes available. |
| Shop HTML changes | Parse errors | Multiple selector fallbacks, JSON-LD first, fixture tests, UI error badge, alarm after repeated failures. **v2**: optional per-link custom CSS selector. |
| Price shown differs by variant/seller | Wrong price tracked | User adds the exact variant URL; Amazon URL normalized to `/dp/<ASIN>`; buy-box price used. |
| Currency mix between shops | Misleading comparisons | Store/display currency per link; no conversion; "best price" only compares same currency. |
| Legal/ToS of scraping | Account/IP block | Personal use, very low frequency, no redistribution. |
| Lost MFA device | Locked out | Admin reset via AWS CLI (`admin-set-user-mfa-preference`, `admin-set-user-password`). |

---

## 13. Milestones

### M1 — Infrastructure foundation + auth
- Bootstrap state bucket, providers, variables.
- ACM cert, S3 + CloudFront + OAC, Route53 record, security headers.
- Cognito pool/client/domain; placeholder SPA with login/logout.
- Budget alarm.
- ✅ Done when: `https://costtracker.marxai.de` shows the app only after login with MFA.

### M2 — Data + API + scraper
- DynamoDB table, api Lambda with all routes, HTTP API + JWT authorizer.
- Scraper Lambda: fetch + SSRF guard, Amazon + generic parsers, price normalization.
- Scheduler 06:00/18:00 Europe/Berlin; manual refresh (sync per link, async all).
- Tests: parsers (fixtures), price parser, SSRF, API (moto).
- ✅ Done when: product with Amazon + another shop link gets prices via schedule and manual refresh; unauthenticated `curl /api/products` → 401.

### M3 — Frontend UI + charts
- Dashboard cards with sparkline and change badge.
- Product detail: multi-line Chart.js chart with ranges, target line, stats table per link, refresh buttons, status badges.
- Add/edit/delete product and links.
- Responsive (mobile friendly), light/dark mode, de-DE number/date formatting.
- ✅ Done when: full CRUD and history viewing work in the browser.

### M4 — SES alerts
- SES domain identity, DKIM, MAIL FROM, DMARC, recipient verification.
- Jinja2 HTML + text templates, alert logic with re-arming.
- ✅ Done when: setting a target price above current price triggers exactly one well-formatted email (checked in Gmail, not in spam; DKIM/SPF/DMARC = PASS).

### M5 — Hardening + polish
- Scraper error alarm, failure email after repeated errors.
- `pip-audit`/`npm audit`, lint/type checks, README.
- Review IAM policies, CSP (securityheaders.com / Mozilla Observatory A+ target).
- Optional: GitHub Actions CI with OIDC.

---

## 14. Verification Checklist

- [ ] `make test` green (ruff, mypy, pytest, svelte-check).
- [ ] `terraform validate` and `terraform plan` clean; `apply` succeeds from scratch.
- [ ] Site reachable only via HTTPS; direct S3 URL → 403.
- [ ] Login requires password + TOTP; no sign-up option shown.
- [ ] `curl https://costtracker.marxai.de/api/products` without token → 401.
- [ ] Adding a product with an Amazon link and a generic shop link → prices appear after refresh.
- [ ] Manual refresh twice within 5 min → second returns 429.
- [ ] `make scrape-now` → new price points for all links; CloudWatch logs clean.
- [ ] Scheduler shows next runs at 06:00 and 18:00 Berlin time.
- [ ] SSRF test: link `http://169.254.169.254/` or `http://localhost` rejected.
- [ ] Target price above current → one HTML alert email; second run with same price → no new email.
- [ ] Security headers grade A/A+; CSP has no violations in browser console.
- [ ] AWS Budget exists; Cost Explorer shows ≈ 0 $ after first week.

---

## 15. Implementation Notes (deviations from the plan above)

Decided while building, after inspecting the AWS account and the sibling `people_db` project:

| Plan | Built | Why |
|---|---|---|
| Separate `bootstrap/` state bucket | Shared existing bucket `marx-aws-tfstates`, key `cost-tracker/prod/terraform.tfstate` | Same convention as the other projects in the account. |
| New SES domain identity + DKIM/MAIL FROM/DMARC records | Reuse the existing verified `familiemarx.click` identity (DKIM ok, account has production access) | Records already exist and are shared with other projects; creating them again would conflict. No DMARC record added (shared domain — add manually if wanted). |
| `make create-user` script | `aws_cognito_user.owner` in Terraform, password set once via CLI | Lets the API pin the owner's `sub` (`OWNER_SUB`). |
| Two Lambda zips | One zip, two handlers (`app.api.handler.handler`, `app.scraper.handler.handler`) | Simpler build; 18 MB zipped. |
| `aws-lambda-powertools`, `python-ulid` | Small built-in router, `uuid4().hex` IDs | Fewer dependencies. |
| AWS Budget per project | Optional (`create_budget = false`) | Account already has > 2 budgets, so each extra one costs ~0.60 USD/month; `account-monthly` already covers everything. |
| — | CloudFront geo restriction DE/AT/CH (`allowed_countries`) | Same as `people_db`; free. Set to `[]` when travelling. |
| — | `recent` (last 60 points) stored on the link item | Dashboard needs 2 queries instead of one history query per product. |
| — | `lowest_price` on link item | "Lowest price so far" badge in emails without a history query. |
| Email texts in German | English texts, German number format (1.299,99 €) | Consistent with the UI. |

### Added after launch (2026-09-26)

- **Tags**: `tags: string[]` on products (max 10, ≤ 30 chars, trimmed, case-insensitive dedupe, first spelling wins). Accepted by `POST /products` and `PUT /products/{id}` (`[]` removes all). Returned in product detail and summaries.
- **Overview**: card/list view toggle (remembered per browser); list view is a sortable table (name, best price, 30-day change, distance to target). Tag filter chips (match ANY selected tag, kept in the URL as `?tags=a,b`) plus name search. Filtering happens client-side.

### Amazon fixes (2026-10-02)

- **Share links** from the Amazon app (`amzn.eu/d/…`, `amzn.to`, `a.co`, …) are resolved to the product URL on add (`resolve_redirects`, SSRF-checked per hop) and stored as `https://www.amazon.de/dp/<ASIN>`. Links stored earlier are rewritten by the scraper on their next successful check. The parser is now chosen by the *final* URL after redirects.
- **No buy box** (Amazon doesn't sell the item itself, page only shows "Alle Angebote"): the scraper loads the all-offers panel (`/gp/product/ajax/aodAjaxMain/?asin=…`) and tracks the cheapest **new** offer; used offers are ignored.
- **Price-to-pay first**: the parser targets `.priceToPay` / `.apex-pricetopay-value` before any other `.a-price`, so a struck-through RRP is never taken; availability text ignores embedded scripts.
- **AliExpress**: product pages are fully client-rendered (no price in HTML, `isCSR: true`). Planned: AliExpress Affiliate API (`aliexpress.affiliate.productdetail.get`) once credentials exist.
