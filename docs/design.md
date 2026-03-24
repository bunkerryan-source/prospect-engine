# Prospect Engine — Design Spec

## Overview

A Python CLI tool that scrapes multiple data sources to find mid-market manufacturers (fragrance, flavor, food, pharma, nutraceutical), deduplicates results, enriches contacts, scores leads, persists to SQLite, and exports ranked prospect lists for a freight brokerage sales team.

**Target customer profile:** Middle-market shippers — large enough to need brokerage services (10+ pallets/week, LTL and FTL mix) but not so large they have direct carrier contracts. Revenue $5M–$500M, 25–2,000 employees.

**Competitive differentiator:** Walmart SQEP (Supplier Quality Excellence Program) expertise — selling to Walmart suppliers getting hit with compliance chargebacks.

---

## Project Structure

```
prospect-engine/
├── .env                       # API keys (never committed)
├── .env.example               # Template with empty keys
├── .gitignore
├── config.yaml                # Targeting, scoring, settings (no secrets)
├── requirements.txt           # pyyaml, requests, openpyxl, python-dotenv, thefuzz
├── run.py                     # CLI entry point + pipeline orchestrator
├── models.py                  # ProspectRecord dataclass + dedup logic
├── utils/
│   ├── __init__.py
│   └── search.py              # Shared search() function (SerpAPI/Serper)
├── modules/
│   ├── __init__.py
│   ├── base.py                # Abstract base class
│   ├── web_search.py          # Company discovery via search API
│   ├── sqep.py                # Walmart SQEP/OTIF signal scraper
│   ├── import_search.py       # Import/export data (ImportYeti + web)
│   └── apollo.py              # Apollo.io company + contact search
├── enrichment/
│   ├── __init__.py
│   └── hunter.py              # Email enrichment + verification
├── scoring/
│   ├── __init__.py
│   └── scorer.py              # Lead scoring engine
├── persistence/
│   ├── __init__.py
│   └── database.py            # SQLite upsert, status tracking, run history
├── checkpoints/               # Auto-managed crash recovery
├── output/                    # CSV + XLSX exports
└── prospects.db               # Auto-created on first run
```

---

## Configuration

### .env (secrets)

```
SERPAPI_KEY=your_key_here
APOLLO_API_KEY=your_key_here
HUNTER_API_KEY=your_key_here
```

### config.yaml (targeting + settings, no secrets)

Single source of truth for all targeting, scoring weights, and operational settings. Every module, the scorer, the enrichment layer, and the persistence layer read from this file.

#### ICP Firmographic Filters

```yaml
icp:
  revenue_min: 5000000       # $5M
  revenue_max: 500000000     # $500M
  employee_min: 25
  employee_max: 2000
```

#### State Lists

Named geographic groups for scoping runs. Run with `--states south_central` or `--nationwide`.

```yaml
state_lists:
  south_central:
    default: true
    states: [TX, LA, AR, OK]
  southeast:
    states: [FL, GA, NC, SC, TN, AL, MS]
  northeast:
    states: [NJ, NY, PA, CT, MA, MD, VA]
  midwest:
    states: [OH, IL, IN, MI, WI, MN, MO, IA]
  west:
    states: [CA, WA, OR, AZ, CO, NV, UT]
```

#### Verticals

Each vertical defines: keywords (for web search and Apollo), NAICS codes (reserved for future use), SQEP product signals, and import keywords.

```yaml
verticals:
  fragrance:
    keywords:
      - fragrance manufacturer
      - fragrance company
      - aroma chemical
      - essential oil manufacturer
      - perfume compound
      - candle manufacturer
      - air freshener manufacturer
      - scent company
    naics_codes: ["325611", "325620", "325998"]
    sqep_product_signals: [candle, air freshener, scented product, home fragrance]

  flavor:
    keywords:
      - flavor manufacturer
      - flavor company
      - flavor producer
      - flavoring extract
      - seasoning manufacturer
      - food ingredient supplier
      - natural flavor
      - flavor house
    naics_codes: ["311942", "311999"]
    sqep_product_signals: [seasoning, flavoring, extract, spice]

  food:
    keywords:
      - food manufacturer
      - food producer
      - food processor
      - co-packer
      - contract food manufacturer
      - snack manufacturer
      - beverage manufacturer
      - condiment manufacturer
    naics_codes: ["3111", "3112", "3113", "3114", "3115", "3116", "3117", "3118", "3119"]
    sqep_product_signals: [snack, food, beverage, condiment, bakery, frozen, dairy, sauce]

  pharma:
    keywords:
      - pharmaceutical manufacturer
      - pharma company
      - CDMO
      - contract drug manufacturer
      - API manufacturer
      - OTC manufacturer
      - drug manufacturer
      - excipient manufacturer
    naics_codes: ["325411", "325412", "325413", "325414"]
    sqep_product_signals: [OTC, over-the-counter, pharmaceutical]

  nutraceutical:
    keywords:
      - supplement manufacturer
      - nutraceutical manufacturer
      - vitamin manufacturer
      - dietary supplement producer
      - protein powder manufacturer
      - supplement contract manufacturer
      - probiotic manufacturer
      - herbal supplement company
    naics_codes: ["311514", "325411", "325199"]
    sqep_product_signals: [vitamin, supplement, protein, probiotic, wellness, gummy]

sqep_search_terms:
  - "Walmart SQEP supplier"
  - "Walmart OTIF penalty"
  - "Walmart chargeback supplier"
  - "Walmart supplier compliance"
  - "SQEP fine deduction"

import_keywords:
  fragrance: [aroma chemical, essential oil, fragrance compound]
  flavor: [flavor extract, natural flavor, food flavoring]
  food: [food ingredient, food additive, food product]
  pharma: [pharmaceutical ingredient, API bulk drug, excipient]
  nutraceutical: [dietary supplement ingredient, herbal extract, vitamin raw material]
```

#### API Provider Settings

```yaml
search_api:
  provider: "serpapi"              # or "serper"
  plan_limit: 1000                 # Monthly search limit ($25/mo plan)

apollo:
  enabled: true
  per_page: 25
  max_pages_per_search: 4
  plan_limit: 30000                # Monthly credit limit ($49/mo plan)

hunter:
  enabled: true
  max_searches_per_run: 100
  max_verifications_per_run: 50
  search_credit_limit: 1000        # Total search credits available
  verification_credit_limit: 1000  # Total verification credits available
```

#### Scoring Weights

```yaml
scoring:
  signal_density:
    1_source: 5
    2_sources: 15
    3_sources: 25
    4_plus_sources: 35
  compliance:
    walmart_supplier: 10
    sqep_mentioned: 10
    otif_mentioned: 10
    compliance_pain: 10
  geography:
    in_target_state: 15
    other: 0
  enrichment:
    verified_email_logistics_title: 15
    email_non_logistics_title: 10
    email_pattern_found: 5
    contact_name_no_email: 3
    website_only: 0
  vertical_multipliers:
    food: 1.3
    fragrance: 1.2
    nutraceutical: 1.15
    pharma: 1.1
    flavor: 1.0
    unknown: 0.8
  tiers:
    hot: 70
    warm: 45
    nurture: 25
```

#### Database, Checkpoints, Output

```yaml
database:
  path: "./prospects.db"
  statuses: [NEW, QUEUED, CONTACTED, ENGAGED, QUOTED, WON, LOST, PARKED]

checkpoints:
  directory: "./checkpoints"
  keep_on_success: false

output:
  directory: "./output"
  filename_prefix: "prospects"
  formats: [xlsx, csv]
```

---

## Data Model

### ProspectRecord Dataclass

Every module outputs this structure. Properly typed for sorting/filtering.

| Field | Type | Description |
|-------|------|-------------|
| company_name | `str` | Company name as found |
| address | `str` | Street address |
| city | `str` | City |
| state | `str` | State abbreviation |
| zip_code | `str` | ZIP code |
| phone | `str` | Phone number |
| website | `str` | Domain only, normalized (no protocol, no www) |
| vertical | `str` | Comma-separated: fragrance, flavor, food, pharma, nutraceutical |
| source_channel | `str` | Comma-separated: web_search, sqep, import, apollo |
| estimated_employees | `Optional[int]` | Employee count |
| estimated_revenue | `Optional[int]` | Revenue in dollars |
| product_keywords | `str` | Comma-separated keywords found |
| compliance_signals | `str` | Comma-separated: walmart_supplier, sqep_mentioned, otif_mentioned, compliance_pain |
| contact_name | `str` | Best contact found |
| contact_title | `str` | Contact's title |
| contact_email | `str` | Contact's email |
| contact_source | `str` | `apollo` or `hunter` — tracks origin |
| email_verified | `str` | verified, invalid, accept_all, unknown, or empty |
| email_confidence | `Optional[int]` | Hunter 0-100 score or None |
| registration_id | `str` | Source-specific ID if any |
| import_products | `str` | What they import |
| notes | `str` | Source-specific notes |
| score | `int` | Lead score (default 0) |
| score_breakdown | `str` | Human-readable explanation |
| tier | `str` | HOT, WARM, NURTURE, PARK |
| scraped_date | `str` | ISO date (YYYY-MM-DD), auto-set to today. On DB insert, becomes `first_seen`. On DB update, becomes `last_seen`. When hydrating from DB (e.g., for `--verify-emails`), populate from `last_seen`. Not stored as its own DB column. |

### Deduplication Logic

1. Normalize domain: strip protocol, strip www, lowercase
2. Exact domain match → merge
3. If no domain match, fuzzy company name match using `thefuzz.fuzz.token_sort_ratio` with threshold 85 → merge
4. Name normalization before fuzzy match: lowercase, strip Inc/LLC/Ltd/Corp/Co./Company/International/Group/Holdings/Enterprises, collapse whitespace

**Merge rules:**
- Multi-value fields (source_channel, vertical, product_keywords, compliance_signals): set union
- Single-value fields: keep existing non-empty value, fill blanks from new record
- `contact_source=apollo` takes priority over `hunter` if both exist

---

## Pipeline Flow

```
config.yaml + .env loaded
    |
CLI args parsed -> resolve state list, verticals, channels
    |
Credit estimation + warning (abort if user declines)
    |
Modules execute in order (checkpoint after each):
    web_search -> sqep -> import_search -> apollo
    |
All results combined into one list
    |
Dedup & merge (domain + fuzzy name)
    | checkpoint
Hunter enrichment (skip prospects with apollo-sourced contacts)
    | checkpoint
Lead scoring (4 dimensions x vertical multiplier)
    |
Upsert to SQLite (new inserts vs returning merges)
    |
Export -> CSV + XLSX (4 sheets)
    |
Credit summary printed
```

---

## Module Specifications

### Shared Search Utility (`utils/search.py`)

Abstracts SerpAPI vs Serper behind a single interface:

```python
def search(query: str, config: dict) -> list[dict]:
    """Returns list of {title, link, snippet}"""
```

- SerpAPI: `GET https://serpapi.com/search?q={query}&api_key={key}&engine=google&num=10` → `result["organic_results"]`
- Serper: `POST https://google.serper.dev/search` with `{"q": query}`, header `X-API-KEY` → `result["organic"]`

Tracks call count for credit logging.

### Base Class (`modules/base.py`)

- `__init__(self, config)` — stores config, extracts states/verticals/ICP
- `channel_name` property (abstract) → string identifier
- `run(self, active_verticals=None)` (abstract) → `list[ProspectRecord]`
- `get_active_verticals(self, requested)` → filtered vertical configs
- `log(self, msg)` → prints `[CHANNEL_NAME] msg`

### Module 1: Web Search (`web_search.py`)

For each vertical x state, search top 3 keywords (e.g., `"fragrance manufacturer TX"`). Also search SQEP product signals globally (not per-state): `Walmart supplier "{signal}" manufacturer`. These global SQEP queries cast a wide net; the SQEP module adds state-specific searches.

Extract company name from title (split on `| - —`, take first segment), domain from URL, snippet to notes.

**Filtered domains:** google.com, youtube.com, wikipedia.org, linkedin.com, facebook.com, yelp.com, indeed.com, glassdoor.com, amazon.com, pinterest.com, twitter.com, instagram.com

Rate limit: 0.5s between calls.

### Module 2: SQEP (`sqep.py`)

Uses shared `search()`. Two strategies:
1. Search `sqep_search_terms` from config
2. Per vertical: `Walmart supplier "{sqep_product_signal}" {state}`

**Filtered consultant domains:** 8thandwalton, carbon6, vendormint, newnexusgroup, ozarkconsulting, coldstreamlogistics, rjwgroup, 5gsales, supplypike

**Signal detection** from title + snippet text (case-insensitive):
- "sqep" → `sqep_mentioned`
- "otif" → `otif_mentioned`
- "walmart" + ("supplier" or "vendor") → `walmart_supplier`
- "chargeback" or "fine" or "penalty" or "deduction" → `compliance_pain`

Only create a record if at least 1 signal detected. Rate limit: 0.5s.

### Module 3: Import Search (`import_search.py`)

Uses shared `search()`. Two strategies:
1. `site:importyeti.com "{import_keyword}"` → parse company name from result title
2. `"{import_keyword}" importer {state} manufacturer` → general web results

Discovery only — no ImportYeti page parsing. Rate limit: 0.5s.

### Module 4: Apollo (`apollo.py`)

**Base URL:** `https://api.apollo.io`

**Company search:** For each vertical, use top 3 keywords. Paginate up to `max_pages_per_search` pages (default 4).

```
POST https://api.apollo.io/api/v1/mixed_companies/search
{
  "api_key": "{key}",
  "q_organization_keyword_tags": ["{keyword}"],
  "organization_num_employees_ranges": ["{employee_min},{employee_max}"],
  "organization_locations": ["{state1}", "{state2}", ...],
  "per_page": 25,
  "page": 1
}
```

Extract from each result: `name`, `city`, `state`, `phone`, `primary_domain` (-> website), `estimated_num_employees`, `annual_revenue_printed`, `industry`, `keywords`.

**Revenue parsing:** `annual_revenue_printed` is a string like "$10M-$50M", "$1B+", or null. Parse using lower bound: "$10M-$50M" -> 10000000, "$1M-$10M" -> 1000000, "$100K-$500K" -> 100000. If null, unparseable, or missing: set `estimated_revenue = None`.

**ICP filtering:** Apollo's API handles employee filtering via `organization_num_employees_ranges`. Revenue filtering is done post-call: discard companies where `estimated_revenue` is not None and falls outside `icp.revenue_min`/`icp.revenue_max`. Companies with unknown revenue are kept (better to include and manually filter than to miss prospects).

**Contact search:** For each company found:

```
POST https://api.apollo.io/api/v1/mixed_people/search
{
  "api_key": "{key}",
  "q_organization_id": "{company_apollo_id}",
  "person_titles": ["logistics", "supply chain", "transportation", "shipping",
                     "distribution", "operations", "procurement", "warehouse",
                     "plant manager", "COO", "General Manager"],
  "per_page": 3,
  "page": 1
}
```

**Contact fallback priority:**
1. Title contains: logistics, supply chain, transportation, shipping, distribution, freight
2. Title contains: operations, COO, VP Operations, General Manager, Plant Manager
3. Leave blank

Set `contact_source = "apollo"` on all Apollo-sourced contacts.

**Credit logging:** Track company searches + people searches separately. Log running total.

Rate limit: 0.5s between calls.

---

## Credit Warning System

Before executing any API calls, the pipeline estimates credit usage:

```
Estimated credit usage:
  SerpAPI:  ~115 searches (plan: 1,000/month)
  Apollo:   ~283 credits  (plan: 30,000/month)
  Hunter:   ~100 searches (plan: 1,000 search credits)

Proceed? [y/N]
```

If any estimate exceeds plan limits, highlight with a warning. User must confirm to proceed. `--dry-run` shows the estimate without executing.

### Estimation Formula

```
SerpAPI credits = web_search queries + sqep queries + import queries
  web_search queries = (active_verticals * active_states * 3)    -- top 3 keywords per vertical per state
                     + sum(len(sqep_product_signals[v]) for v)   -- global SQEP signal queries (NOT per-state)
  sqep queries       = len(sqep_search_terms)                    -- global SQEP terms
                     + sum(len(sqep_product_signals[v]) for v) * active_states  -- per-state per-signal
  import queries     = sum(len(import_keywords[v]) for v) * 2   -- two strategies per keyword

Apollo credits = company_searches + people_searches
  company_searches = active_verticals * 3 (keywords) * max_pages_per_search
  people_searches  = estimated_companies_found (use company_searches * per_page as upper bound)

Hunter credits = min(prospects_needing_enrichment, max_searches_per_run)
  (estimated as: total_deduped - apollo_sourced_with_contacts)
```

Since Hunter runs post-dedup and the exact count is unknown upfront, show "up to {max_searches_per_run}" for Hunter.

---

## Hunter Enrichment (`enrichment/hunter.py`)

Post-dedup step. Runs on prospects where:
- `website` is non-empty
- `contact_email` is empty
- `contact_source` is NOT `apollo`

### Domain Search

`GET https://api.hunter.io/v2/domain-search?domain={domain}&api_key={key}&type=personal`

**Contact selection logic (priority order):**
1. Filter `data.emails` to contacts whose `position` or `department` matches: logistics, supply chain, transportation, shipping, distribution, operations, procurement, warehouse, plant manager, fulfillment, COO
2. Among matches, pick highest `confidence` score
3. Populate: contact_name, contact_title, contact_email, email_confidence, contact_source="hunter"
4. If no logistics/operations match: leave contact fields blank
5. If no emails but `data.pattern` exists: store in notes ("Hunter email pattern: {first}.{last}@domain.com")
6. If nothing useful: log and move on

Rate limit: 2s between calls. Capped at `max_searches_per_run`.

### Error Handling

All API calls (Hunter, Apollo, SerpAPI) follow the same pattern:
- **HTTP 429 (rate limit):** Wait 60s, retry once. If still 429, skip and log.
- **HTTP 401/403 (auth):** Log error with "Check your API key in .env", abort module (not full pipeline). Record that the module was aborted so downstream steps can adjust (e.g., if Apollo aborts, Hunter should still respect `max_searches_per_run` but the pipeline should warn: "Apollo aborted — Hunter may process more prospects than usual").
- **HTTP 5xx (server error):** Skip this call, log, continue to next prospect.
- **Timeout (10s):** Skip, log, continue.
- **Empty/malformed response:** Log, continue.

No infinite retries. At most one retry per call (for 429 only).

### Email Verification (separate CLI command)

`GET https://api.hunter.io/v2/email-verifier?email={email}&api_key={key}`

Store `data.status` (valid, invalid, accept_all, unknown) in `email_verified`. Works on both Hunter and Apollo-sourced emails.

```bash
python run.py --verify-emails                  # HOT + WARM tiers (default)
python run.py --verify-emails --tier hot       # HOT only
python run.py --verify-emails --all            # All tiers
```

Capped at `max_verifications_per_run`.

**Tier filtering for `--verify-emails`:** Query DB for prospects where `contact_email` is non-empty AND `email_verified` is empty. Then filter by tier: default = HOT + WARM, `--tier hot` = HOT only, `--all` = all tiers. Process up to `max_verifications_per_run`.

---

## Lead Scoring (`scoring/scorer.py`)

Four dimensions plus a vertical multiplier. All weights configurable in config.yaml.

### Dimensions

| Dimension | Logic | Max |
|-----------|-------|-----|
| Signal Density | Count distinct values in `source_channel` (e.g., "web_search,apollo" = 2 sources). 1=5, 2=15, 3=25, 4=35 | 35 |
| Compliance Pressure | 10 pts each signal (walmart_supplier, sqep_mentioned, otif_mentioned, compliance_pain) | 40 |
| Geography | In selected state list=15, else=0 | 15 |
| Enrichment Quality | Verified email + logistics title=15, email + non-logistics title=10, email pattern only=5, name only=3, website only=0 | 15 |

**Max raw score:** 105. With highest multiplier (1.3x food), max final score is 137. Tier thresholds are calibrated against the post-multiplier score intentionally — HOT at 70 means a prospect needs strong signals across multiple dimensions even with the best multiplier.

### Vertical Multiplier

Applied to raw score. When multiple verticals tagged, use the highest multiplier.

| Vertical | Multiplier |
|----------|-----------|
| food | 1.3 |
| fragrance | 1.2 |
| nutraceutical | 1.15 |
| pharma | 1.1 |
| flavor | 1.0 |
| unknown | 0.8 |

### Formula

`score = round((signal + compliance + geography + enrichment) * max_vertical_multiplier)`

### Score Breakdown

Human-readable string stored on each record:
`"Signal:25 + Compliance:20 + Geo:15 + Enrich:15 = 75 x 1.3(food) = 98 -> HOT"`

### Tiers

| Tier | Threshold |
|------|-----------|
| HOT | >= 70 |
| WARM | >= 45 |
| NURTURE | >= 25 |
| PARK | < 25 |

---

## Persistence (`persistence/database.py`)

SQLite at `prospects.db`.

### prospects table DDL

```sql
CREATE TABLE prospects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,       -- lowercased, suffix-stripped, for fuzzy matching
    domain TEXT DEFAULT '',              -- normalized website domain, for exact matching
    address TEXT DEFAULT '',
    city TEXT DEFAULT '',
    state TEXT DEFAULT '',
    zip_code TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    website TEXT DEFAULT '',
    vertical TEXT DEFAULT '',            -- comma-separated
    source_channel TEXT DEFAULT '',      -- comma-separated
    estimated_employees INTEGER,         -- NULL if unknown
    estimated_revenue INTEGER,           -- NULL if unknown, in dollars
    product_keywords TEXT DEFAULT '',    -- comma-separated
    compliance_signals TEXT DEFAULT '',  -- comma-separated
    contact_name TEXT DEFAULT '',
    contact_title TEXT DEFAULT '',
    contact_email TEXT DEFAULT '',
    contact_source TEXT DEFAULT '',      -- 'apollo' or 'hunter'
    email_verified TEXT DEFAULT '',      -- verified, invalid, accept_all, unknown
    email_confidence INTEGER,            -- NULL if unknown, 0-100
    registration_id TEXT DEFAULT '',
    import_products TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    score INTEGER DEFAULT 0,
    score_breakdown TEXT DEFAULT '',
    tier TEXT DEFAULT 'PARK',
    status TEXT DEFAULT 'NEW',           -- user-controlled via CLI
    first_seen TEXT NOT NULL,            -- ISO date, set on insert, never overwritten
    last_seen TEXT NOT NULL,             -- ISO date, updated each run
    run_count INTEGER DEFAULT 1,
    status_updated TEXT DEFAULT '',      -- ISO timestamp of last status change
    status_notes TEXT DEFAULT ''         -- user notes
);

CREATE INDEX idx_normalized_name ON prospects(normalized_name);
CREATE INDEX idx_domain ON prospects(domain);
CREATE INDEX idx_status ON prospects(status);
CREATE INDEX idx_first_seen ON prospects(first_seen);
CREATE INDEX idx_score ON prospects(score);
```

### run_history table

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PRIMARY KEY | Auto-increment |
| run_date | TEXT | ISO 8601 timestamp |
| states_used | TEXT | Comma-separated state abbreviations |
| verticals_used | TEXT | Comma-separated vertical names |
| channels_used | TEXT | Comma-separated module names |
| raw_count | INTEGER | Total results before dedup |
| dedup_count | INTEGER | Results after dedup |
| new_count | INTEGER | New inserts this run |
| updated_count | INTEGER | Existing records updated |
| hot_count | INTEGER | HOT tier prospects |
| warm_count | INTEGER | WARM tier prospects |
| nurture_count | INTEGER | NURTURE tier prospects |
| park_count | INTEGER | PARK tier prospects |
| avg_score | REAL | Average score this run |
| duration_seconds | INTEGER | Total run time |
| serpapi_credits | INTEGER | SerpAPI calls made |
| apollo_credits | INTEGER | Apollo credits used |
| hunter_search_credits | INTEGER | Hunter domain searches |
| hunter_verify_credits | INTEGER | Hunter verifications |

### Upsert Rules

1. Match by domain first, then fuzzy name (threshold 85)
2. New → INSERT with status=NEW, first_seen=today, run_count=1
3. Returning → UPDATE last_seen, increment run_count, merge multi-value fields (union), fill empty single-value fields, recalculate score
4. **Never overwrite:** status, first_seen, status_notes, status_updated

---

## Checkpoints

After each module completes, serialize results to `checkpoints/run_{timestamp}/01_web_search_complete.json`, etc.

### Checkpoint File Schema

Each checkpoint file is a JSON object:

```json
{
  "module": "web_search",
  "timestamp": "2026-03-24T14:30:00",
  "credits_used": 115,
  "prospect_count": 142,
  "prospects": [
    {
      "company_name": "Acme Fragrance Co",
      "website": "acmefragrance.com",
      ...all ProspectRecord fields as dict...
    }
  ]
}
```

### Checkpoint Numbering

Files use canonical order numbers regardless of which modules run: 01=web_search, 02=sqep, 03=import_search, 04=apollo, 05=dedup, 06=hunter. If `--channels web_search,apollo` is used, the files are `01_web_search_complete.json` and `04_apollo_complete.json`. This way `--resume` knows which modules completed.

On crash, folder persists. `python run.py --resume` loads completed modules, runs remaining. Checkpoint folder deleted on success (unless `keep_on_success: true`).

**Known tradeoff:** Checkpoints are module-level, not intra-module. If Apollo crashes after 50 of 200 API calls, those 50 results and credits are lost on `--resume`. This is acceptable for v1 — the simplicity of module-level checkpoints outweighs the rare credit loss from mid-module crashes.

---

## CLI Reference

```bash
# --- Scraping ---
python run.py                                    # Default state list, all modules
python run.py --states south_central             # Named list
python run.py --states south_central,southeast   # Multiple lists (union)
python run.py --nationwide                       # All 50 states (with credit warning)
python run.py --verticals fragrance,food         # Filter verticals
python run.py --channels web_search,sqep         # Filter modules
python run.py --skip-enrichment                  # Skip Hunter
python run.py --skip-scoring                     # Skip scoring
python run.py --dry-run                          # Estimate credits, show plan, don't execute
python run.py --resume                           # Resume from last checkpoint

# --- Email Verification ---
python run.py --verify-emails                    # HOT + WARM tiers
python run.py --verify-emails --tier hot         # HOT only
python run.py --verify-emails --all              # All tiers

# --- Database ---
python run.py --set-status "Acme Corp" CONTACTED --note "Left VM 3/15"
python run.py --pipeline                         # Status summary table
python run.py --list-status NEW                  # List prospects by status
python run.py --search "fragrance Texas"         # Search DB (see below)
python run.py --db-stats                         # Counts, tier distribution, top scores
python run.py --export-db backup.csv             # Full CSV export
python run.py --reset-db --confirm               # Wipe DB (requires --confirm)
```

### CLI Details

**`--set-status`**: Matches by normalized company name (case-insensitive, suffix-stripped). If multiple records match, lists them and asks user to pick. If no match, tries fuzzy match (threshold 85) and confirms with user.

**`--search`**: Splits query into terms, runs case-insensitive LIKE on: company_name, city, state, vertical, product_keywords, notes. All terms must match (AND logic). Returns results sorted by score desc.

**`--nationwide`**: Uses all 50 US states (no territories/DC). Overrides `--states` if both provided. If `--states` references a nonexistent list name, print error and exit.

**`--pipeline`**: Prints a table of status counts with tier breakdown per status.

### Status Workflow

Statuses represent the sales pipeline. QUEUED is for prospects you've identified as worth contacting but haven't reached out to yet — a staging area between NEW (just scraped) and CONTACTED (outreach made).

```
NEW -> QUEUED -> CONTACTED -> ENGAGED -> QUOTED -> WON
                                    \-> LOST
                          \-> PARKED (revisit later)
```

---

## Output

### Excel (4 sheets)

**Sheet 1: New This Run** — query DB for prospects where `first_seen` = today's date (date-only comparison, YYYY-MM-DD). Sorted by score desc. Primary sheet for reviewing new finds after each run.

**Sheet 2: Full Prospects** — entire DB. Formatting:
- Navy header row, white text, frozen top row, auto-filter on all columns
- Alternating row shading (white / light gray)
- Tier column: HOT=red fill, WARM=orange, NURTURE=yellow, PARK=gray
- Status column: NEW=blue, CONTACTED=orange, ENGAGED=green, WON=dark green, LOST=red, PARKED=gray
- Email Verified: verified=green, invalid=red, accept_all=yellow
- Score column: conditional formatting gradient (green high, red low)

**Sheet 3: Pipeline Dashboard** — summary tables laid out vertically:
- **Row 1-2:** Title "Pipeline Dashboard" + run date
- **Rows 4-12:** Status breakdown table (2 columns: Status, Count) for each status in order
- **Rows 14-19:** Tier distribution table (2 columns: Tier, Count) for HOT/WARM/NURTURE/PARK
- **Rows 21-23:** This Run summary (2 columns): New Prospects, Returning Prospects, Total Processed
- **Rows 25-36:** Top 10 new prospects table (columns: Company, State, Vertical, Score, Tier, Contact Email)
- Same navy header + alternating row formatting as other sheets

**Sheet 4: Run Log** — run_history table rows.

### CSV

All DB fields, sorted by score desc. Flat format for future CRM import.

---

## Dependencies

```
pyyaml
requests
openpyxl
python-dotenv
thefuzz[speedup]
```

Python 3.10+.

---

## Implementation Rules

1. **Graceful failures.** Every API call in try/except. Log error, continue. Never crash mid-pipeline.
2. **Rate limits.** SerpAPI: 0.5s. Apollo: 0.5s. Hunter: 2s.
3. **Shared search function.** `utils/search.py` — one implementation, three modules (web_search, sqep, import_search).
4. **Config drives everything.** New state list, new vertical, retuned scores = edit YAML only.
5. **Dedup is critical.** Multi-source = real manufacturer. One record per company, all sources merged.
6. **Apollo-Hunter coordination.** Apollo finds contacts during company search. Hunter fills in contacts for companies found by other modules. Hunter skips any prospect with `contact_source=apollo`.
7. **Credit logging.** Every module logs credits consumed. Print summary at end.
8. **Credit warning.** Estimate before executing. Warn if approaching plan limits.
9. **Professional Excel.** Shareable with sales team as-is. Navy headers, alternating rows, auto-filter, frozen header, color-coded tiers/statuses.
10. **Scraper never touches user fields.** status, first_seen, status_notes are user-controlled. Set on insert only.
11. **ICP filtering.** Apollo filters employees via API and revenue post-call. Web search, SQEP, and import modules do not have firmographic data — ICP filtering only applies at the Apollo stage and during future enrichment. Non-Apollo prospects are kept regardless of unknown size.
12. **Missing API keys.** On startup, check which modules are enabled and which keys are present. If a required key is missing, disable that module and warn (e.g., "SERPAPI_KEY not set — skipping web_search, sqep, import_search modules"). If ALL keys are missing, error and exit.

---

## Decisions Log

| Decision | Rationale |
|----------|-----------|
| Dropped FDA module | No reliable API for facility registrations by state. openFDA enforcement endpoint returns recalls, not registrations. Can add later if data source found. |
| API keys in .env, not config.yaml | Prevents accidental commits of secrets |
| Shared search in utils/, not in web_search module | Avoids coupling between peer modules |
| Typed fields (Optional[int]) instead of all-strings | Enables proper sorting/filtering on employees, revenue, score |
| Added contact_source field | Clean tracking of Apollo vs Hunter origin instead of overloading email_confidence |
| thefuzz for dedup | Battle-tested fuzzy matching library vs rolling our own |
| Contact fallback: logistics → operations/COO → blank | No random contacts. Blank is better than wrong person. |
| Multi-vertical multiplier: use max | Simple, favorable to the prospect |
| Geography: in-list=15, else=0 | Removed adjacency concept. State lists are just run-scoping convenience. |
| Sequential module execution | Simplicity and reliability over speed for weekly/monthly runs |
| SerpAPI $25/mo (1,000), Apollo $49/mo (30,000), Hunter 1,000+1,000 credits | Plan limits baked into credit warning system |
