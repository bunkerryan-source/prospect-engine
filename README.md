# Prospect Engine

Lead generation pipeline for Priority1 Logistics — finds, enriches, and scores manufacturers who ship LTL and full truckload freight across five verticals: fragrance, flavor, food, pharma, and nutraceutical.

## Quick Start

```bash
# 1. Install dependencies
python -m pip install -r requirements.txt

# 2. Set up API keys in .env
cp .env.example .env
# Edit .env with your actual keys

# 3. Run with default state list (south_central)
python run.py

# 4. Run for a specific region
python run.py --states west

# 5. Dry run — see credit estimates without executing
python run.py --states southeast --dry-run
```

## API Keys Required

| Provider | Env Variable | Purpose | Plan |
|----------|-------------|---------|------|
| SerpAPI | `SERPAPI_KEY` | Web search, SQEP, import discovery | 1,000 searches/mo |
| Apollo.io | `APOLLO_API_KEY` | Company + contact enrichment | 30,000 credits/mo |
| Hunter.io | `HUNTER_API_KEY` | Email enrichment + verification | 1,000 search + 1,000 verify credits |

## Pipeline Flow

```
Web Search → SQEP Signal Detection → Import Search → Apollo
    ↓
  Dedup & merge (domain + fuzzy name match)
    ↓
  State extraction from snippets
    ↓
  Hunter email enrichment
    ↓
  Lead scoring (4 dimensions × vertical multiplier)
    ↓
  SQLite upsert (new vs returning)
    ↓
  Export → XLSX (4 sheets) + CSV
```

## CLI Reference

### Scraping

```bash
python run.py                                    # Default state list, all modules
python run.py --states south_central             # Named state list
python run.py --states south_central,southeast   # Multiple lists (union)
python run.py --nationwide                       # All 50 states (credit warning!)
python run.py --verticals fragrance,food         # Filter verticals
python run.py --channels web_search,apollo       # Filter modules
python run.py --skip-enrichment                  # Skip Hunter
python run.py --skip-scoring                     # Skip scoring
python run.py --dry-run                          # Estimate credits only
python run.py --resume                           # Resume from last checkpoint
```

### Email Verification

```bash
python run.py --verify-emails                    # HOT + WARM tiers
python run.py --verify-emails --tier hot         # HOT only
python run.py --verify-emails --all              # All tiers
```

### Database Commands

```bash
python run.py --set-status "Acme Corp" CONTACTED --note "Left VM 3/15"
python run.py --pipeline                         # Status summary
python run.py --list-status NEW                  # List by status
python run.py --search "fragrance Texas"         # Search DB
python run.py --db-stats                         # Counts + tier distribution
python run.py --export-db backup.csv             # Full CSV export
python run.py --reset-db --confirm               # Wipe DB
```

## Configuration (config.yaml)

### State Lists

Five named regional lists. Set `default: true` on the one you use most:

```yaml
state_lists:
  south_central:
    default: true
    states: [TX, LA, AR, OK]
  west:
    states: [CA, WA, OR, AZ, CO, NV, UT]
```

### Verticals

Each vertical has keywords (used for web search + Apollo), NAICS codes, and SQEP product signals:

```yaml
verticals:
  fragrance:
    keywords:
      - fragrance manufacturer
      - candle manufacturer
    naics_codes: ["325611", "325620"]
    sqep_product_signals: [candle, air freshener]
```

### Blocked Domains

Add noise domains as you spot them in reports. These are checked alongside the built-in blocklist (200+ domains):

```yaml
blocked_domains:
  - somespamsite.com
  - anothernoisedomain.org
```

Supports subdomain matching — blocking `example.com` also blocks `sub.example.com`.

### Scoring

Four dimensions summed, then multiplied by the vertical multiplier:

| Dimension | Max Points |
|-----------|-----------|
| Signal Density (# of sources) | 35 |
| Compliance Pressure (SQEP/OTIF/Walmart signals) | 40 |
| Geography (state in target list) | 15 |
| Enrichment Quality (email + title quality) | 15 |

Vertical multipliers: food 1.3×, fragrance 1.2×, nutraceutical 1.15×, pharma 1.1×, flavor 1.0×

Tiers: **HOT** ≥70, **WARM** ≥45, **NURTURE** ≥25, **PARK** <25

## Output

Files are saved to `output/` with the state list label in the filename:

```
output/prospects_south_central_2026-03-24.xlsx
output/prospects_west_2026-03-24.csv
```

### Excel Sheets

1. **New This Run** — prospects first seen in the current run, sorted by score
2. **Full Prospects** — entire database with color-coded tiers and statuses
3. **Pipeline Dashboard** — status counts, tier distribution, top 10 new prospects
4. **Run Log** — history of all runs with credit usage

## Project Structure

```
prospect-engine/
├── run.py                  # CLI entry point + pipeline orchestration
├── config.yaml             # All configuration (edit this)
├── models.py               # ProspectRecord dataclass, dedup, merge
├── modules/
│   ├── web_search.py       # SerpAPI web search + inline SQEP detection
│   ├── sqep.py             # Dedicated SQEP compliance signal search
│   ├── import_search.py    # ImportYeti + general import/manufacturer search
│   └── apollo.py           # Apollo.io company + contact search
├── enrichment/
│   └── hunter.py           # Hunter.io email enrichment + verification
├── scoring/
│   └── scorer.py           # 4-dimension lead scoring engine
├── persistence/
│   └── database.py         # SQLite storage, upsert, run history
├── output/
│   └── exporter.py         # XLSX (4 sheets) + CSV export
├── utils/
│   ├── search.py           # SerpAPI/Serper abstraction
│   ├── domain_filter.py    # 200+ blocked domains, company name extraction
│   ├── checkpoints.py      # Crash recovery checkpoints
│   └── credits.py          # Credit estimation + warnings
└── tests/                  # Unit tests
```
