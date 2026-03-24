# PROSPECT ENGINE — Claude Code Build Prompt

## CONTEXT

Build a unified, multi-channel prospect scraping engine for a mid-market freight brokerage. The engine runs as a single Python CLI tool that executes scraper modules in sequence, deduplicates results, enriches contacts, scores leads, persists everything to a SQLite database, and exports ranked prospect lists.

My brokerage serves fragrance companies, flavor producers, food manufacturers, pharmaceutical companies, and nutraceutical/supplement manufacturers. Target customers are middle-market shippers — large enough to need brokerage services (10+ pallets/week, LTL and FTL mix) but not so large they have direct carrier contracts. I use Walmart SQEP (Supplier Quality Excellence Program) expertise as a competitive differentiator when selling to Walmart suppliers getting hit with compliance chargebacks.

---

## PROJECT STRUCTURE

```
prospect-engine/
├── config.yaml                # Single source of truth for ALL targeting and settings
├── run.py                     # Pipeline orchestrator and CLI entry point
├── models.py                  # ProspectRecord dataclass + dedup logic
├── modules/
│   ├── __init__.py
│   ├── base.py                # Abstract base class for all scraper modules
│   ├── web_search_scraper.py  # Company discovery via SerpAPI or Serper.dev
│   ├── fda_scraper.py         # FDA facility registration database queries
│   ├── sqep_scraper.py        # Walmart SQEP / OTIF compliance signal scraper
│   ├── import_scraper.py      # Import/export customs data scraper (ImportYeti + web)
│   └── apollo_module.py        # Apollo.io company + contact search
├── enrichment/
│   ├── __init__.py
│   └── hunter_enrichment.py   # Post-dedup email enrichment + verification via Hunter.io
├── scoring/
│   ├── __init__.py
│   └── scorer.py              # 5-dimension lead scoring engine
├── persistence/
│   ├── __init__.py
│   └── database.py            # SQLite persistence — upsert, status tracking, run history
├── checkpoints/               # Auto-managed crash recovery (created at runtime)
├── output/                    # Generated CSV + XLSX exports
└── prospects.db               # SQLite database (auto-created on first run)
```

## DATA FLOW

```
config.yaml
    ↓
run.py parses CLI args, resolves state list, loads config
    ↓
Modules execute in order (checkpoint saved after each):
    web_search → fda → sqep → import → apollo
    ↓
All module results combined into one list
    ↓
Deduplication & merge (domain matching + fuzzy company name matching)
    ↓ checkpoint
Hunter.io enrichment (search credits: find emails for prospects missing contact info)
    ↓ checkpoint
Lead scoring (5 dimensions × vertical multiplier → score + tier)
    ↓
Upsert to SQLite database (new inserts vs. returning merges)
    ↓
Export from database → CSV + XLSX
    (4 sheets: New This Week, Full Prospects, Pipeline Dashboard, Run Log)
```

---

## COMPLETE CONFIG.YAML

Generate a config.yaml with all of the following. This is the single source of truth — every module, the scorer, the enrichment layer, and the persistence layer read from this file.

```yaml
# ============================================================
# PROSPECT ENGINE CONFIGURATION
# ============================================================

# --- ICP Firmographic Filters ---
icp:
  revenue_min: 5000000         # $5M
  revenue_max: 500000000       # $500M
  employee_min: 25
  employee_max: 2000

# --- Named State Lists ---
# Create as many as you want. Run with: python run.py --states south_central
# Default (no flag): uses the list with "default: true"
# Nationwide: python run.py --nationwide (all 50 states, ignores lists)
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

# --- Verticals ---
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
    fda_product_categories: []
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
    fda_product_categories: ["Flavors, Extracts", "Food Additives"]
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
    fda_product_categories:
      - "Bakery Prods/Dough/Mix/Icing"
      - "Beverages"
      - "Candy w/o Choc/Special/Chew Gum"
      - "Cereal Prep/Breakfast Food"
      - "Cheese/Cheese Prod"
      - "Condiment, Seasoning, Salt"
      - "Fruit/Fruit Prod"
      - "Ice Cream/Rel Frozen Desserts"
      - "Meat, Meat Products"
      - "Snack Food Item"
      - "Soft Drink/Water"
      - "Veg/Veg Prod"
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
    fda_product_categories: ["Human Rx Drug", "Human OTC Drug", "Bulk Drug Substance"]
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
    fda_product_categories: ["Dietary Supplements", "Vitamin/Mineral"]
    sqep_product_signals: [vitamin, supplement, protein, probiotic, wellness, gummy]

# --- SQEP Search Terms (used by sqep_scraper module) ---
sqep_search_terms:
  - "Walmart SQEP supplier"
  - "Walmart OTIF penalty"
  - "Walmart chargeback supplier"
  - "Walmart supplier compliance"
  - "SQEP fine deduction"

# --- Import Keywords (used by import_scraper module) ---
import_keywords:
  fragrance: [aroma chemical, essential oil, fragrance compound]
  flavor: [flavor extract, natural flavor, food flavoring]
  food: [food ingredient, food additive, food product]
  pharma: [pharmaceutical ingredient, API bulk drug, excipient]
  nutraceutical: [dietary supplement ingredient, herbal extract, vitamin raw material]

# --- Search API ---
search_api:
  provider: "serpapi"
  api_key: ""                  # YOUR SerpAPI key here. $50/mo for 5,000 searches. serpapi.com

# --- Apollo.io ---
apollo:
  api_key: ""                  # YOUR Apollo key here. apollo.io > Settings > API
  enabled: true
  per_page: 25                 # Results per API call (max 100)
  max_pages_per_search: 4      # Pages to paginate through per keyword (25 × 4 = 100 companies)

# --- Hunter.io ---
hunter:
  api_key: ""                  # YOUR Hunter key here. hunter.io > Dashboard > API
  enabled: true
  max_searches_per_run: 100    # Domain search credits to spend per run (adjust to your plan)
  max_verifications_per_run: 50 # Verification credits per --verify-emails run

# --- Lead Scoring ---
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
    priority_state: 15
    adjacent_state: 5
    unknown_or_other: 0
  adjacent_states: [NM, MS, TN, MO, KS, CO]
  enrichment:
    verified_email_logistics_title: 15   # Apollo or Hunter email + logistics title
    email_pattern_found: 5               # Hunter pattern but no specific contact
    contact_name_no_email: 3             # Name/title but no email
    website_only: 0                      # Just a domain
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

# --- Database ---
database:
  path: "./prospects.db"
  statuses: [NEW, QUEUED, CONTACTED, ENGAGED, QUOTED, WON, LOST, PARKED]

# --- Checkpoints ---
checkpoints:
  directory: "./checkpoints"
  keep_on_success: false

# --- Output ---
output:
  directory: "./output"
  filename_prefix: "prospects"
  formats: [xlsx, csv]
```

---

## MODELS.PY

### ProspectRecord Dataclass

Every module outputs this same structure:

| Field | Type | Description |
|-------|------|-------------|
| company_name | str | Company name as found |
| address | str | Street address |
| city | str | City |
| state | str | State abbreviation |
| zip_code | str | ZIP code |
| phone | str | Phone number |
| website | str | Website domain (normalized, no protocol) |
| vertical | str | fragrance, flavor, food, pharma (comma-separated if multi) |
| source_channel | str | web_search, fda, sqep, import, apollo (comma-separated after merge) |
| estimated_employees | str | Employee count if available |
| estimated_revenue | str | Revenue estimate if available |
| product_keywords | str | Comma-separated keywords found |
| compliance_signals | str | walmart_supplier, sqep_mentioned, otif_mentioned, compliance_pain |
| contact_name | str | Contact name if available |
| contact_title | str | Contact title if available |
| contact_email | str | Contact email if available |
| email_verified | str | verified, invalid, accept_all, unknown, or "" |
| email_confidence | str | Hunter 0-100 score, or "" |
| registration_id | str | FDA registration number, etc. |
| import_products | str | What they import |
| notes | str | Source-specific notes |
| score | int | Lead score (default 0) |
| score_breakdown | str | Human-readable score explanation |
| tier | str | HOT, WARM, NURTURE, PARK |
| scraped_date | str | Date scraped (auto-populated) |

### Deduplication Logic

Merge duplicates by: (1) exact domain match, (2) fuzzy name match (lowercase, strip Inc/LLC/Ltd/Corp/Co./Company/International/Group/Holdings/Enterprises, collapse whitespace).

When merging: combine source_channel/keywords/signals/verticals as set unions. Single-value fields: keep non-empty, don't overwrite existing non-empty values.

---

## SCRAPER MODULES

### Base Class (base.py)
- `__init__(self, config)` — stores config, extracts states/verticals/icp
- `channel_name` property (abstract) → string identifier
- `run(self, active_verticals=None)` (abstract) → List[ProspectRecord]
- `get_active_verticals(self, requested)` → filtered vertical configs
- `log(self, msg)` → prints `[CHANNEL_NAME] msg`

### Module 1: Web Search (web_search_scraper.py)

Uses SerpAPI or Serper.dev (configured in `search_api`). Build a `search(query)` abstraction both return `List[{title, link, snippet}]`:
- **SerpAPI**: `GET https://serpapi.com/search?q={query}&api_key={key}&engine=google&num=10` → `result["organic_results"]`
- **Serper**: `POST https://google.serper.dev/search` with `{"q": query}`, header `X-API-KEY` → `result["organic"]`

For each vertical × state, search top 3 keywords. Also search SQEP product signals: `Walmart supplier "{signal}" manufacturer`. Extract company name from title (split on | - —, take first segment), domain from URL, snippet to notes. Filter out: google.com, youtube.com, wikipedia.org, linkedin.com, facebook.com, yelp.com, indeed.com, glassdoor.com, amazon.com, pinterest.com. `time.sleep(0.5)` between calls.

### Module 2: FDA (fda_scraper.py)

Free, no key. 240 req/min limit. `time.sleep(1)` between calls.
- Food/flavor: `GET https://api.fda.gov/food/enforcement.json?search=state:"{state}"&limit=100` → `recalling_firm`, `city`, `state`, `product_description`
- Pharma: `GET https://api.fda.gov/drug/ndc.json?search=_exists_:labeler_name&limit=100` → `labeler_name`, `product_type`, `brand_name`, `product_ndc`
- Pharma fallback: `GET https://api.fda.gov/drug/label.json` → `openfda.manufacturer_name`

### Module 3: SQEP (sqep_scraper.py)

Uses the shared `search()` function from Module 1. Two strategies:
1. Search config `sqep_search_terms`. Filter out consultants: 8thandwalton, carbon6, vendormint, newnexusgroup, ozarkconsulting, coldstreamlogistics, rjwgroup, 5gsales, supplypike.
2. Per vertical: `Walmart supplier "{sqep_product_signal}" {state}`. Filter out walmart.com.

Detect signals: "sqep" → sqep_mentioned, "otif" → otif_mentioned, "walmart" → walmart_supplier, "chargeback"/"fine"/"penalty" → compliance_pain. Only create record if ≥1 signal detected.

### Module 4: Import (import_scraper.py)

Uses the shared `search()` function. Two strategies:
1. `site:importyeti.com "{import_keyword}"` → parse company from ImportYeti result titles
2. `"{import_keyword}" importer {state} manufacturer` → general web results

### Module 5: Apollo (apollo_module.py)

Apollo is the richest data source in the pipeline. It returns company firmographics (revenue, employee count, industry, address, website) AND contact data (names, titles, emails, phone numbers) in the same query. Unlike the other modules that find company names and websites but rarely contacts, Apollo delivers actionable prospect records with decision-maker details.

**Company Search**: For each vertical, search using the vertical's keywords combined with ICP filters.

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

Use top 3 keywords per vertical. Paginate through `max_pages_per_search` pages (from config) to get up to 100 companies per keyword. That means 4 verticals × 3 keywords × 4 pages = 48 API calls for a priority run.

From each company result, extract: `name`, `city`, `state`, `phone`, `primary_domain` (→ website), `estimated_num_employees`, `annual_revenue_printed`, `industry`, `keywords`.

**Contact Search**: For each company found, search for logistics decision-makers.

```
POST https://api.apollo.io/api/v1/mixed_people/search
{
  "api_key": "{key}",
  "q_organization_id": "{company_apollo_id}",
  "person_titles": ["logistics", "supply chain", "transportation", "shipping",
                     "distribution", "operations", "procurement", "warehouse",
                     "plant manager"],
  "per_page": 3,
  "page": 1
}
```

From the best contact match, populate `contact_name`, `contact_title`, `contact_email`. If Apollo returns a verified email, store `email_confidence: "apollo_verified"` in the record so the scoring engine knows this is a high-quality contact.

**Credit awareness**: Apollo's free tier gives 100 credits/month. Each company search page costs 1 credit. Each people search costs 1 credit. A 4-state priority run uses ~48 company search credits + up to 100 people search credits = ~148 credits. That exceeds the free tier. With a paid plan (Basic $59/mo = 5,000 credits), you have plenty of room. The module should log credit usage: "Apollo: X company searches + Y contact searches = Z total credits used."

**Dedup value**: Apollo data is the gold standard for the merge. When a company shows up in SerpAPI results (name + website only) AND in Apollo (name + website + revenue + employees + contact email), the merged record gets all of it. Apollo-sourced contacts don't need Hunter enrichment, saving Hunter credits.

`time.sleep(0.5)` between API calls.

---

## HUNTER.IO ENRICHMENT (enrichment/hunter_enrichment.py)

Post-dedup step, NOT a scraper module. Two operations with separate credit pools:

### Domain Search (automatic, uses search credits)

Runs on every prospect where `website` is non-empty AND `contact_email` is empty AND `email_confidence` is NOT "apollo_verified" (skip companies Apollo already enriched).

For each qualifying domain, call:
```
GET https://api.hunter.io/v2/domain-search?domain={domain}&api_key={key}&type=personal
```

The response returns:
```json
{
  "data": {
    "pattern": "{first}.{last}",
    "emails": [
      {
        "value": "j.smith@acmefragrance.com",
        "first_name": "John",
        "last_name": "Smith",
        "position": "Director of Logistics",
        "department": "logistics",
        "confidence": 91,
        "type": "personal"
      },
      ...
    ]
  }
}
```

**Contact selection logic** (in priority order):
1. Filter `data.emails` to contacts whose `position` or `department` matches logistics-relevant terms: logistics, supply chain, transportation, shipping, distribution, operations, procurement, warehouse, plant manager, fulfillment
2. Among matches, pick the one with the highest `confidence` score
3. Populate on the ProspectRecord:
   - `contact_name` = "{first_name} {last_name}" (e.g., "John Smith")
   - `contact_title` = `position` (e.g., "Director of Logistics")
   - `contact_email` = `value` (e.g., "j.smith@acmefragrance.com")
   - `email_confidence` = confidence score as string (e.g., "91")
4. If NO logistics match but other personal emails exist, pick the highest-confidence one anyway. Any contact at the company is a starting point — you can ask to be transferred to the shipping department.
5. If NO emails at all but `data.pattern` exists, store in notes: "Hunter email pattern: {first}.{last}@acmefragrance.com" — the sales team can construct emails manually once they identify a contact name via LinkedIn or a phone call.
6. If the API returns nothing useful, log and move on.

`time.sleep(2)` between calls. Cap at `max_searches_per_run` from config. Log summary: "Hunter enrichment: X domains searched, Y logistics contacts found, Z non-logistics fallbacks, W patterns stored, V no data."

### Email Verification (manual trigger, uses verification credits)

```bash
python run.py --verify-emails                  # HOT + WARM tiers (default)
python run.py --verify-emails --tier hot       # HOT only
python run.py --verify-emails --all            # All emails regardless of source or tier
```

Call `GET https://api.hunter.io/v2/email-verifier?email={email}&api_key={key}`. Response returns `data.status`: "valid", "invalid", "accept_all", "unknown". Store in `email_verified` field. Cap at `max_verifications_per_run`. Works on both Hunter-sourced and Apollo-sourced emails.

---

## LEAD SCORING (scoring/scorer.py)

Pure computation after dedup + enrichment. Five dimensions:

1. **Signal Density**: 1 src=5, 2=15, 3=25, 4+=35 pts
2. **Compliance Pressure**: walmart_supplier/sqep_mentioned/otif_mentioned/compliance_pain = 10 pts each (stack, max 40)
3. **Geographic Advantage**: default-list state=15, adjacent=5, other=0
4. **Enrichment Quality**: apollo_verified email+logistics title=15, hunter email+logistics title=15, email pattern only=5, name only=3, website only=0
5. **Vertical Multiplier**: food=1.3x, fragrance=1.2x, nutraceutical=1.15x, pharma=1.1x, flavor=1.0x, unknown=0.8x

`score = round((dim1 + dim2 + dim3 + dim4) × multiplier)`

Breakdown: `"Signal:25 + Compliance:20 + Geo:15 + Enrich:15 = 75 × 1.3(food) = 98"`

Tiers: HOT ≥70, WARM ≥45, NURTURE ≥25, PARK <25. All weights in config.yaml.

---

## PERSISTENCE (persistence/database.py)

SQLite at `prospects.db`. Two tables: `prospects` and `run_history`.

### prospects table
All ProspectRecord fields plus: `normalized_name`, `domain` (for matching), `status` (default 'NEW'), `first_seen`, `last_seen`, `run_count`, `status_updated`, `status_notes`. Indexes on normalized_name, domain, status, first_seen, score.

### run_history table
One row per run: date, states/verticals/channels used, raw count, dedup count, new/updated counts, tier distribution, avg score, duration.

### Upsert Rules
1. Match by domain first, then fuzzy name
2. New → INSERT with status='NEW', first_seen=today, run_count=1
3. Returning → UPDATE last_seen, increment run_count, merge multi-value fields (union), fill empty single-value fields, recalculate score. **NEVER overwrite status, first_seen, status_notes.**

---

## CHECKPOINTS

After each module completes, serialize results to `checkpoints/run_{timestamp}/NN_module_complete.json`. On crash, folder persists. `python run.py --resume` loads completed modules, runs remaining. Delete folder on success (unless `keep_on_success: true`).

---

## CLI

```bash
# --- Scraping ---
python run.py                                    # Default state list, all modules
python run.py --states south_central             # Named list
python run.py --states south_central,southeast   # Multiple lists (union)
python run.py --nationwide                       # All 50 states
python run.py --verticals fragrance,food         # Filter verticals
python run.py --channels web_search,fda          # Filter modules
python run.py --skip-enrichment                  # Skip Hunter
python run.py --skip-scoring                     # Skip scoring
python run.py --dry-run                          # Preview
python run.py --resume                           # Resume from checkpoint

# --- Email Verification ---
python run.py --verify-emails                    # HOT + WARM (default)
python run.py --verify-emails --tier hot         # HOT only
python run.py --verify-emails --all              # All Hunter-sourced

# --- Database ---
python run.py --set-status "Acme Corp" CONTACTED --note "Left VM 3/15"
python run.py --pipeline                         # Status summary
python run.py --list-status NEW                  # List by status
python run.py --search "fragrance Texas"         # Search DB
python run.py --db-stats                         # Stats
python run.py --export-db backup.csv             # Full export
python run.py --reset-db --confirm               # Wipe DB
```

---

## OUTPUT

### Excel (4 sheets)
1. **New This Week** — first_seen = today. Sorted by score desc.
2. **Full Prospects** — entire DB. Color-coded Tier (HOT=red, WARM=orange, NURTURE=yellow, PARK=gray), Status (NEW=blue, CONTACTED=orange, ENGAGED=green, WON=dark green, LOST=red, PARKED=gray), Email Verified (verified=green, invalid=red). Navy header, alternating rows, frozen header, auto-filter.
3. **Pipeline Dashboard** — status counts, tier distribution, new vs returning.
4. **Run Log** — run_history table rows.

### CSV
All DB fields, sorted by score desc.

---

## DEPENDENCIES

```
pip install pyyaml requests openpyxl
```

---

## IMPLEMENTATION RULES

1. **Graceful failures.** Every API call in try/except. Log error, continue. Never crash mid-pipeline.
2. **Rate limits.** SerpAPI: 0.5s. FDA: 1s. Apollo: 0.5s. Hunter: 2s.
3. **Shared search function.** Build `search(query) → List[{title, link, snippet}]` in web_search_scraper.py. SQEP and import modules import and reuse it. One implementation, three modules.
4. **Config drives everything.** New state list, new vertical, retuned scores = edit yaml only.
5. **Dedup is critical.** Multi-source = real manufacturer. One record per company, all sources merged.
6. **Apollo-Hunter coordination.** Apollo finds contacts as part of its company search. Hunter fills in contacts for companies found by other modules (SerpAPI, FDA, ImportYeti) that returned no contact info. Hunter should skip any prospect that already has an Apollo-sourced email. This prevents double-spending credits on the same company.
7. **Credit logging.** Every module that uses paid API credits (SerpAPI, Apollo, Hunter) should log how many credits it consumed during the run. Print a credit summary at the end: "Credits used — SerpAPI: 56, Apollo: 148, Hunter searches: 75, Hunter verifications: 0."
8. **Professional Excel.** Shareable with sales team as-is. Navy headers, alternating rows, auto-filter, frozen header.
9. **Scraper never touches user fields.** status, first_seen, status_notes are user-controlled. Set on insert only.
