# Prospect Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python CLI tool that scrapes 4 data sources for mid-market manufacturer prospects, deduplicates, enriches contacts, scores leads, and exports ranked lists.

**Architecture:** Sequential pipeline — config-driven modules produce ProspectRecords, which are deduplicated, enriched via Hunter.io, scored, upserted to SQLite, and exported to XLSX/CSV. All API keys in `.env`, all targeting/weights in `config.yaml`.

**Tech Stack:** Python 3.10+, requests, pyyaml, python-dotenv, openpyxl, thefuzz, SQLite3 (stdlib), argparse (stdlib)

**Spec:** `docs/design.md`

---

## File Map

| File | Responsibility |
|------|---------------|
| `.env.example` | API key template |
| `.gitignore` | Ignore .env, prospects.db, checkpoints/, output/, __pycache__ |
| `config.yaml` | All targeting, scoring, and operational config |
| `requirements.txt` | Python dependencies |
| `run.py` | CLI entry point, argument parsing, pipeline orchestration |
| `models.py` | ProspectRecord dataclass, domain normalization, name normalization, dedup/merge |
| `utils/__init__.py` | Empty |
| `utils/search.py` | Shared SerpAPI/Serper search abstraction with credit tracking |
| `modules/__init__.py` | Empty |
| `modules/base.py` | Abstract base class for scraper modules |
| `modules/web_search.py` | Web search module — keyword + SQEP signal searches |
| `modules/sqep.py` | SQEP module — Walmart compliance signal detection |
| `modules/import_search.py` | Import module — ImportYeti + general import searches |
| `modules/apollo.py` | Apollo module — company + contact search with ICP filtering |
| `enrichment/__init__.py` | Empty |
| `enrichment/hunter.py` | Hunter domain search + email verification |
| `scoring/__init__.py` | Empty |
| `scoring/scorer.py` | 4-dimension lead scoring + vertical multiplier + tier assignment |
| `persistence/__init__.py` | Empty |
| `persistence/database.py` | SQLite schema creation, upsert, status management, run history, queries |
| `output/__init__.py` | Empty |
| `output/exporter.py` | XLSX (4 sheets, formatted) + CSV export |
| `utils/checkpoints.py` | Checkpoint serialization, loading, resume, cleanup |
| `utils/credits.py` | Credit estimation formulas and summary formatting |
| `tests/__init__.py` | Empty (ensures test package recognition) |
| `tests/test_models.py` | ProspectRecord, normalization, dedup, to_dict tests |
| `tests/test_scoring.py` | Scorer tests |
| `tests/test_database.py` | DB upsert, status, query tests |
| `tests/test_search.py` | Search utility tests (mocked API) |
| `tests/test_modules.py` | Module tests (mocked search/API) |
| `tests/test_enrichment.py` | Hunter enrichment tests (mocked API) |
| `tests/test_exporter.py` | Excel/CSV export tests |
| `tests/test_checkpoints.py` | Checkpoint save/load/resume tests |
| `tests/test_credits.py` | Credit estimation formula tests |
| `tests/test_cli.py` | CLI argument parsing, DB commands, dry-run tests |
| `tests/test_pipeline.py` | Integration test — full pipeline with mocked APIs |

---

## Task 1: Project Scaffolding

**Files:**
- Create: `.env.example`, `.gitignore`, `requirements.txt`, `config.yaml`
- Create: `utils/__init__.py`, `modules/__init__.py`, `enrichment/__init__.py`, `scoring/__init__.py`, `persistence/__init__.py`, `output/__init__.py`, `tests/__init__.py`

- [ ] **Step 1: Create `.gitignore`**

```
.env
prospects.db
checkpoints/
output/
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] **Step 2: Create `.env.example`**

```
SERPAPI_KEY=your_key_here
APOLLO_API_KEY=your_key_here
HUNTER_API_KEY=your_key_here
```

- [ ] **Step 3: Create `requirements.txt`**

```
pyyaml
requests
openpyxl
python-dotenv
thefuzz[speedup]
pytest
```

- [ ] **Step 4: Create full `config.yaml`**

Write the complete config.yaml with all sections from the spec: `icp`, `state_lists`, `verticals` (all 5 with full keyword lists), `sqep_search_terms`, `import_keywords`, `search_api`, `apollo`, `hunter`, `scoring` (all weights), `database`, `checkpoints`, `output`. This is the single source of truth — copy every value from the spec.

- [ ] **Step 5: Create empty `__init__.py` files**

Create empty `__init__.py` in: `utils/`, `modules/`, `enrichment/`, `scoring/`, `persistence/`, `output/`, `tests/`.

- [ ] **Step 6: Install dependencies**

Run: `pip install -r requirements.txt`

- [ ] **Step 7: Commit**

```bash
git add .gitignore .env.example requirements.txt config.yaml utils/__init__.py modules/__init__.py enrichment/__init__.py scoring/__init__.py persistence/__init__.py output/__init__.py tests/__init__.py
git commit -m "chore: project scaffolding with config, dependencies, and package structure"
```

---

## Task 2: Data Model — ProspectRecord and Dedup

**Files:**
- Create: `models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write failing tests for ProspectRecord**

```python
# tests/test_models.py
import pytest
from models import ProspectRecord, normalize_domain, normalize_company_name, deduplicate

def test_prospect_record_defaults():
    p = ProspectRecord(company_name="Acme Corp")
    assert p.company_name == "Acme Corp"
    assert p.score == 0
    assert p.estimated_employees is None
    assert p.website == ""
    assert p.scraped_date != ""  # auto-populated

def test_normalize_domain():
    assert normalize_domain("https://www.acme.com/about") == "acme.com"
    assert normalize_domain("http://ACME.COM") == "acme.com"
    assert normalize_domain("www.acme.com") == "acme.com"
    assert normalize_domain("") == ""

def test_normalize_company_name():
    assert normalize_company_name("Acme Corporation, Inc.") == "acme corporation"
    assert normalize_company_name("The  Acme  Group LLC") == "the acme group"
    assert normalize_company_name("Acme International Holdings") == "acme"

def test_dedup_exact_domain_merge():
    p1 = ProspectRecord(company_name="Acme", website="acme.com", source_channel="web_search", vertical="food")
    p2 = ProspectRecord(company_name="Acme Inc", website="acme.com", source_channel="apollo", vertical="pharma",
                        contact_name="John", contact_email="j@acme.com", contact_source="apollo")
    results = deduplicate([p1, p2])
    assert len(results) == 1
    assert "web_search" in results[0].source_channel
    assert "apollo" in results[0].source_channel
    assert "food" in results[0].vertical
    assert "pharma" in results[0].vertical
    assert results[0].contact_name == "John"
    assert results[0].contact_source == "apollo"

def test_dedup_fuzzy_name_merge():
    p1 = ProspectRecord(company_name="Acme Fragrance Co", source_channel="web_search")
    p2 = ProspectRecord(company_name="Acme Fragrance Company", source_channel="sqep",
                        compliance_signals="sqep_mentioned")
    results = deduplicate([p1, p2])
    assert len(results) == 1
    assert "sqep_mentioned" in results[0].compliance_signals

def test_dedup_no_merge_different_companies():
    p1 = ProspectRecord(company_name="Acme Corp", website="acme.com", source_channel="web_search")
    p2 = ProspectRecord(company_name="Beta Inc", website="beta.com", source_channel="apollo")
    results = deduplicate([p1, p2])
    assert len(results) == 2

def test_merge_apollo_contact_priority():
    """Apollo contacts should take priority over Hunter contacts."""
    p1 = ProspectRecord(company_name="Acme", website="acme.com",
                        contact_name="Hunter Guy", contact_source="hunter")
    p2 = ProspectRecord(company_name="Acme", website="acme.com",
                        contact_name="Apollo Guy", contact_source="apollo")
    results = deduplicate([p1, p2])
    assert results[0].contact_source == "apollo"
    assert results[0].contact_name == "Apollo Guy"

def test_to_dict_roundtrip():
    p = ProspectRecord(company_name="Acme", website="acme.com", estimated_employees=100)
    d = p.to_dict()
    assert d["company_name"] == "Acme"
    assert d["estimated_employees"] == 100
    assert isinstance(d, dict)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_models.py -v`
Expected: FAIL — `models` module not found

- [ ] **Step 3: Implement models.py**

Create `models.py` with:
- `ProspectRecord` dataclass with all fields from spec, defaults for str fields = `""`, defaults for Optional[int] = `None`, `score` default = 0, `scraped_date` auto-set to `date.today().isoformat()` via `field(default_factory=...)`
- `normalize_domain(url: str) -> str` — strip protocol, strip www, lowercase, strip path
- `normalize_company_name(name: str) -> str` — lowercase, strip suffixes (Inc, LLC, Ltd, Corp, Co., Company, International, Group, Holdings, Enterprises — with optional trailing period/comma), collapse whitespace, strip
- `merge_records(existing: ProspectRecord, new: ProspectRecord) -> ProspectRecord` — set-union for multi-value fields (source_channel, vertical, product_keywords, compliance_signals), fill blank single-value fields, apollo contact_source takes priority
- `deduplicate(records: list[ProspectRecord]) -> list[ProspectRecord]` — build domain index, iterate records, match by domain first then fuzzy name (token_sort_ratio >= 85), merge or append
- `to_dict(self) -> dict` — return all fields as a dict (for checkpoint serialization and DB operations). Use `dataclasses.asdict` or manual dict comprehension.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_models.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add models.py tests/test_models.py
git commit -m "feat: add ProspectRecord dataclass with dedup and normalization"
```

---

## Task 3: Shared Search Utility

**Files:**
- Create: `utils/search.py`
- Create: `tests/test_search.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_search.py
import pytest
from unittest.mock import patch, MagicMock
from utils.search import search, SearchClient

def test_serpapi_search(monkeypatch):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "organic_results": [
            {"title": "Acme Fragrance | Home", "link": "https://acmefragrance.com", "snippet": "Leading fragrance maker"},
            {"title": "Beta Scents - About", "link": "https://beta.com/about", "snippet": "Another company"}
        ]
    }
    config = {"search_api": {"provider": "serpapi"}}

    with patch("utils.search.requests.get", return_value=mock_response) as mock_get:
        client = SearchClient(config, api_key="test_key")
        results = client.search("fragrance manufacturer TX")

    assert len(results) == 2
    assert results[0]["title"] == "Acme Fragrance | Home"
    assert results[0]["link"] == "https://acmefragrance.com"
    assert client.call_count == 1

def test_serper_search(monkeypatch):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "organic": [
            {"title": "Acme Pharma", "link": "https://acmepharma.com", "snippet": "Drug maker"}
        ]
    }
    config = {"search_api": {"provider": "serper"}}

    with patch("utils.search.requests.post", return_value=mock_response) as mock_post:
        client = SearchClient(config, api_key="test_key")
        results = client.search("pharma manufacturer TX")

    assert len(results) == 1
    assert client.call_count == 1

def test_search_handles_api_error():
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.raise_for_status.side_effect = Exception("Server error")
    config = {"search_api": {"provider": "serpapi"}}

    with patch("utils.search.requests.get", return_value=mock_response):
        client = SearchClient(config, api_key="test_key")
        results = client.search("test query")

    assert results == []
    assert client.call_count == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_search.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement `utils/search.py`**

Create `SearchClient` class:
- `__init__(self, config, api_key)` — store provider type, api_key, init `call_count = 0`
- `search(self, query) -> list[dict]` — dispatch to `_serpapi_search` or `_serper_search` based on config. Wrap in try/except. Increment call_count. `time.sleep(0.5)` after each call. Return `list[{title, link, snippet}]`.
- `_serpapi_search(query)` — `GET https://serpapi.com/search` with params `q`, `api_key`, `engine=google`, `num=10`. Parse `organic_results`.
- `_serper_search(query)` — `POST https://google.serper.dev/search` with json `{"q": query}`, header `X-API-KEY`. Parse `organic`.
- Error handling per spec: try/except, return empty list on failure, log error.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_search.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add utils/search.py tests/test_search.py
git commit -m "feat: add shared search utility with SerpAPI/Serper support"
```

---

## Task 4: Module Base Class

**Files:**
- Create: `modules/base.py`

- [ ] **Step 1: Implement `modules/base.py`**

```python
from abc import ABC, abstractmethod
from models import ProspectRecord

class BaseModule(ABC):
    def __init__(self, config: dict, states: list[str]):
        self.config = config
        self.states = states
        self.verticals = config.get("verticals", {})
        self.icp = config.get("icp", {})

    @property
    @abstractmethod
    def channel_name(self) -> str:
        pass

    @abstractmethod
    def run(self, active_verticals: list[str] | None = None) -> list[ProspectRecord]:
        pass

    def get_active_verticals(self, requested: list[str] | None) -> dict:
        if requested:
            return {k: v for k, v in self.verticals.items() if k in requested}
        return self.verticals

    def log(self, msg: str):
        print(f"[{self.channel_name.upper()}] {msg}")
```

- [ ] **Step 2: Commit**

```bash
git add modules/base.py
git commit -m "feat: add abstract base class for scraper modules"
```

---

## Task 5: Database Persistence Layer

**Files:**
- Create: `persistence/database.py`
- Create: `tests/test_database.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_database.py
import pytest
import sqlite3
import os
from persistence.database import ProspectDB
from models import ProspectRecord

@pytest.fixture
def db(tmp_path):
    db_path = str(tmp_path / "test.db")
    return ProspectDB(db_path)

def test_db_creates_tables(db):
    conn = sqlite3.connect(db.path)
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}
    conn.close()
    assert "prospects" in tables
    assert "run_history" in tables

def test_upsert_new_prospect(db):
    p = ProspectRecord(company_name="Acme Corp", website="acme.com",
                       source_channel="web_search", vertical="food")
    new_count, updated_count = db.upsert([p])
    assert new_count == 1
    assert updated_count == 0
    results = db.search("Acme")
    assert len(results) == 1
    assert results[0]["status"] == "NEW"
    assert results[0]["run_count"] == 1

def test_upsert_returning_prospect_merges(db):
    p1 = ProspectRecord(company_name="Acme", website="acme.com",
                        source_channel="web_search", vertical="food")
    db.upsert([p1])
    p2 = ProspectRecord(company_name="Acme Inc", website="acme.com",
                        source_channel="apollo", vertical="pharma",
                        contact_name="John", contact_email="j@acme.com")
    new_count, updated_count = db.upsert([p2])
    assert new_count == 0
    assert updated_count == 1
    results = db.search("Acme")
    assert len(results) == 1
    assert results[0]["run_count"] == 2
    assert "web_search" in results[0]["source_channel"]
    assert "apollo" in results[0]["source_channel"]
    assert results[0]["contact_name"] == "John"

def test_upsert_never_overwrites_status(db):
    p = ProspectRecord(company_name="Acme", website="acme.com", source_channel="web_search")
    db.upsert([p])
    db.set_status("Acme", "CONTACTED", note="Called 3/15")
    p2 = ProspectRecord(company_name="Acme", website="acme.com", source_channel="apollo")
    db.upsert([p2])
    results = db.search("Acme")
    assert results[0]["status"] == "CONTACTED"
    assert results[0]["status_notes"] == "Called 3/15"

def test_set_status(db):
    p = ProspectRecord(company_name="Acme Corp", website="acme.com", source_channel="web_search")
    db.upsert([p])
    matches = db.set_status("Acme Corp", "CONTACTED", note="Left VM")
    assert matches == 1
    results = db.search("Acme")
    assert results[0]["status"] == "CONTACTED"

def test_search_multi_term(db):
    p1 = ProspectRecord(company_name="Acme Fragrance", state="TX", vertical="fragrance",
                        website="acme.com", source_channel="web_search")
    p2 = ProspectRecord(company_name="Beta Food Co", state="CA", vertical="food",
                        website="beta.com", source_channel="web_search")
    db.upsert([p1, p2])
    results = db.search("fragrance TX")
    assert len(results) == 1
    assert results[0]["company_name"] == "Acme Fragrance"

def test_pipeline_stats(db):
    p1 = ProspectRecord(company_name="A", website="a.com", source_channel="web_search", score=80, tier="HOT")
    p2 = ProspectRecord(company_name="B", website="b.com", source_channel="web_search", score=50, tier="WARM")
    db.upsert([p1, p2])
    stats = db.get_pipeline_stats()
    assert stats["status_counts"]["NEW"] == 2
    assert stats["tier_counts"]["HOT"] == 1
    assert stats["tier_counts"]["WARM"] == 1

def test_get_for_verification(db):
    p1 = ProspectRecord(company_name="A", website="a.com", source_channel="web_search",
                        contact_email="j@a.com", score=80, tier="HOT")
    p2 = ProspectRecord(company_name="B", website="b.com", source_channel="web_search",
                        contact_email="j@b.com", score=50, tier="WARM")
    p3 = ProspectRecord(company_name="C", website="c.com", source_channel="web_search",
                        contact_email="", score=90, tier="HOT")  # no email
    p4 = ProspectRecord(company_name="D", website="d.com", source_channel="web_search",
                        contact_email="j@d.com", score=20, tier="PARK")
    db.upsert([p1, p2, p3, p4])
    # HOT + WARM default
    results = db.get_for_verification(tiers=["HOT", "WARM"], limit=100)
    assert len(results) == 2  # C excluded (no email), D excluded (PARK)
    # HOT only
    results = db.get_for_verification(tiers=["HOT"], limit=100)
    assert len(results) == 1

def test_run_history(db):
    db.record_run(states="TX,LA", verticals="food,pharma", channels="web_search,apollo",
                  raw_count=100, dedup_count=60, new_count=50, updated_count=10,
                  hot=10, warm=20, nurture=15, park=15, avg_score=55.0,
                  duration=120, serpapi=50, apollo=100, hunter_search=30, hunter_verify=0)
    history = db.get_run_history()
    assert len(history) == 1
    assert history[0]["new_count"] == 50
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_database.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement `persistence/database.py`**

Create `ProspectDB` class:
- `__init__(self, path)` — store path, call `_init_db()` to create tables + indexes using DDL from spec
- `_init_db()` — `CREATE TABLE IF NOT EXISTS` for prospects (full DDL from spec) and run_history
- `_find_match(prospect) -> dict | None` — search by domain first, then fuzzy name (threshold 85)
- `upsert(prospects: list[ProspectRecord]) -> tuple[int, int]` — for each prospect: find match, if none INSERT (status=NEW, first_seen=today, run_count=1), if match UPDATE (last_seen, run_count++, merge multi-value fields via set union, fill empty single-value fields, never overwrite status/first_seen/status_notes/status_updated). Return (new_count, updated_count).
- `set_status(name, status, note="") -> int` — match by normalized name (case-insensitive). Return match count. If 0, try fuzzy. Update status, status_updated, status_notes.
- `search(query) -> list[dict]` — split terms, LIKE on company_name, city, state, vertical, product_keywords, notes. AND logic. Sort by score desc.
- `get_pipeline_stats() -> dict` — status counts, tier counts
- `get_by_status(status) -> list[dict]`
- `get_db_stats() -> dict` — total count, tier distribution, avg score, top 10
- `get_prospects_for_export() -> list[dict]` — all records, score desc
- `get_new_this_run(run_date) -> list[dict]` — first_seen = run_date
- `record_run(...)` — INSERT into run_history
- `get_run_history() -> list[dict]`
- `reset(confirm=False)` — DROP + recreate if confirm=True
- `get_for_verification(tiers, limit) -> list[dict]` — email non-empty, email_verified empty, filter by tier
- `update_email_verified(prospect_id, status)` — update email_verified field

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_database.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add persistence/database.py tests/test_database.py
git commit -m "feat: add SQLite persistence with upsert, status tracking, and run history"
```

---

## Task 6: Lead Scoring Engine

**Files:**
- Create: `scoring/scorer.py`
- Create: `tests/test_scoring.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_scoring.py
import pytest
from scoring.scorer import score_prospect, score_prospects
from models import ProspectRecord

def load_test_config():
    """Minimal scoring config matching spec defaults."""
    return {
        "scoring": {
            "signal_density": {"1_source": 5, "2_sources": 15, "3_sources": 25, "4_plus_sources": 35},
            "compliance": {"walmart_supplier": 10, "sqep_mentioned": 10, "otif_mentioned": 10, "compliance_pain": 10},
            "geography": {"in_target_state": 15, "other": 0},
            "enrichment": {
                "verified_email_logistics_title": 15, "email_non_logistics_title": 10,
                "email_pattern_found": 5, "contact_name_no_email": 3, "website_only": 0
            },
            "vertical_multipliers": {"food": 1.3, "fragrance": 1.2, "nutraceutical": 1.15,
                                      "pharma": 1.1, "flavor": 1.0, "unknown": 0.8},
            "tiers": {"hot": 70, "warm": 45, "nurture": 25}
        }
    }

def test_hot_prospect():
    config = load_test_config()
    p = ProspectRecord(
        company_name="Acme Food",
        source_channel="web_search,apollo,sqep",    # 3 sources = 25
        compliance_signals="walmart_supplier,sqep_mentioned",  # 20
        state="TX",
        vertical="food",
        contact_email="j@acme.com",
        contact_title="Director of Logistics",
        contact_source="apollo"
    )
    result = score_prospect(p, config, target_states=["TX", "LA"])
    # 25 + 20 + 15 + 15 = 75 * 1.3 = 97.5 -> 98
    assert result.score == 98
    assert result.tier == "HOT"
    assert "Signal:25" in result.score_breakdown

def test_warm_prospect():
    config = load_test_config()
    p = ProspectRecord(
        company_name="Beta Pharma",
        source_channel="web_search,apollo",  # 2 = 15
        state="TX",
        vertical="pharma",
        contact_email="info@beta.com",
        contact_title="CEO",
        contact_source="hunter"
    )
    result = score_prospect(p, config, target_states=["TX"])
    # 15 + 0 + 15 + 10 = 40 * 1.1 = 44 -> NURTURE (just under 45)
    assert result.tier == "NURTURE"

def test_park_prospect():
    config = load_test_config()
    p = ProspectRecord(company_name="Tiny Co", source_channel="web_search", state="NY")
    result = score_prospect(p, config, target_states=["TX"])
    # 5 + 0 + 0 + 0 = 5 * 0.8 = 4 -> PARK
    assert result.tier == "PARK"

def test_multi_vertical_uses_max_multiplier():
    config = load_test_config()
    p = ProspectRecord(company_name="Combo", source_channel="web_search",
                       vertical="food,pharma", state="TX")
    result = score_prospect(p, config, target_states=["TX"])
    # 5 + 0 + 15 + 0 = 20 * 1.3(food) = 26
    assert result.score == 26

def test_score_prospects_batch():
    config = load_test_config()
    prospects = [
        ProspectRecord(company_name="A", source_channel="web_search", state="TX"),
        ProspectRecord(company_name="B", source_channel="apollo,sqep", state="TX",
                       compliance_signals="walmart_supplier")
    ]
    results = score_prospects(prospects, config, target_states=["TX"])
    assert len(results) == 2
    assert all(r.score > 0 for r in results)
    assert all(r.tier != "" for r in results)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_scoring.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `scoring/scorer.py`**

Two public functions:
- `score_prospect(prospect, config, target_states) -> ProspectRecord` — compute 4 dimensions, apply max vertical multiplier, set score/breakdown/tier, return updated copy
- `score_prospects(prospects, config, target_states) -> list[ProspectRecord]` — call score_prospect on each

Internal helpers:
- `_signal_density(prospect, weights)` — count distinct source_channel values, map to points
- `_compliance_pressure(prospect, weights)` — count matching signals, 10 pts each
- `_geography(prospect, target_states, weights)` — 15 if state in target_states, else 0
- `_enrichment_quality(prospect, weights)` — check contact_email + contact_title for logistics keywords → 15; email + non-logistics → 10; "Hunter email pattern" in notes → 5; contact_name non-empty → 3; else 0
- `_get_multiplier(prospect, multipliers)` — parse vertical field, return max multiplier
- `_get_tier(score, tiers)` — HOT >= 70, WARM >= 45, NURTURE >= 25, PARK < 25

Logistics title keywords for enrichment scoring: logistics, supply chain, transportation, shipping, distribution, freight, warehouse, procurement, fulfillment, operations, COO, plant manager, general manager

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_scoring.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add scoring/scorer.py tests/test_scoring.py
git commit -m "feat: add lead scoring engine with 4 dimensions and vertical multiplier"
```

---

## Task 7: Web Search Module

**Files:**
- Create: `modules/web_search.py`
- Create: `tests/test_modules.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_modules.py
import pytest
from unittest.mock import MagicMock, patch
from modules.web_search import WebSearchModule

def make_config(states=None):
    return {
        "verticals": {
            "fragrance": {
                "keywords": ["fragrance manufacturer", "aroma chemical"],
                "sqep_product_signals": ["candle", "air freshener"]
            }
        },
        "icp": {"employee_min": 25, "employee_max": 2000},
        "search_api": {"provider": "serpapi"}
    }

def test_web_search_produces_records():
    config = make_config()
    mock_client = MagicMock()
    mock_client.search.return_value = [
        {"title": "Acme Fragrance | Leading Manufacturer", "link": "https://acmefragrance.com/about", "snippet": "Top fragrance maker in TX"},
        {"title": "YouTube - Fragrance", "link": "https://youtube.com/watch?v=123", "snippet": "video"}
    ]

    module = WebSearchModule(config, states=["TX"], search_client=mock_client)
    results = module.run(active_verticals=["fragrance"])

    assert len(results) >= 1
    assert results[0].website == "acmefragrance.com"
    assert results[0].source_channel == "web_search"
    assert results[0].vertical == "fragrance"
    # youtube.com should be filtered out
    assert not any(r.website == "youtube.com" for r in results)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_modules.py::test_web_search_produces_records -v`
Expected: FAIL

- [ ] **Step 3: Implement `modules/web_search.py`**

`WebSearchModule(BaseModule)`:
- `__init__(config, states, search_client)` — accept injected SearchClient for testing
- `channel_name` = "web_search"
- `run(active_verticals)`:
  1. For each vertical x state: search top 3 keywords as `"{keyword} {state}"`
  2. For each vertical: search SQEP product signals globally as `Walmart supplier "{signal}" manufacturer`
  3. For each result: extract company name from title (split on `|`, `-`, `—`, take first segment, strip), extract domain from URL via `normalize_domain`, skip filtered domains
  4. Return list of ProspectRecords with source_channel="web_search", vertical set, snippet in notes

Filtered domains list: google.com, youtube.com, wikipedia.org, linkedin.com, facebook.com, yelp.com, indeed.com, glassdoor.com, amazon.com, pinterest.com, twitter.com, instagram.com

Helper: `extract_company_name(title) -> str` — split on `|`, ` - `, ` — `, take first segment, strip whitespace.
Helper: `extract_domain(url) -> str` — use `normalize_domain` from models.py.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_modules.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add modules/web_search.py tests/test_modules.py
git commit -m "feat: add web search scraper module"
```

---

## Task 8: SQEP Module

**Files:**
- Create: `modules/sqep.py`
- Modify: `tests/test_modules.py` (append tests)

- [ ] **Step 1: Write failing test**

Append to `tests/test_modules.py`:

```python
from modules.sqep import SQEPModule

def test_sqep_detects_signals():
    config = {
        "verticals": {"food": {"sqep_product_signals": ["snack", "food"]}},
        "sqep_search_terms": ["Walmart SQEP supplier"],
        "icp": {}
    }
    mock_client = MagicMock()
    mock_client.search.return_value = [
        {"title": "Acme Foods - Walmart Supplier", "link": "https://acmefoods.com",
         "snippet": "We are a Walmart vendor struggling with SQEP compliance and OTIF penalties"},
        {"title": "8th and Walton Consulting", "link": "https://8thandwalton.com",
         "snippet": "We help with SQEP"}
    ]

    module = SQEPModule(config, states=["TX"], search_client=mock_client)
    results = module.run(active_verticals=["food"])

    assert len(results) >= 1
    acme = [r for r in results if "acmefoods" in r.website]
    assert len(acme) == 1
    assert "walmart_supplier" in acme[0].compliance_signals
    assert "sqep_mentioned" in acme[0].compliance_signals
    assert "otif_mentioned" in acme[0].compliance_signals
    # consultant should be filtered
    assert not any("8thandwalton" in r.website for r in results)

def test_sqep_requires_signal():
    config = {"verticals": {"food": {"sqep_product_signals": ["snack"]}},
              "sqep_search_terms": [], "icp": {}}
    mock_client = MagicMock()
    mock_client.search.return_value = [
        {"title": "Random Company", "link": "https://random.com", "snippet": "No signals here"}
    ]
    module = SQEPModule(config, states=["TX"], search_client=mock_client)
    results = module.run(active_verticals=["food"])
    assert len(results) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_modules.py::test_sqep_detects_signals -v`
Expected: FAIL

- [ ] **Step 3: Implement `modules/sqep.py`**

`SQEPModule(BaseModule)`:
- `channel_name` = "sqep"
- `run(active_verticals)`:
  1. Strategy 1: search each `sqep_search_terms` globally
  2. Strategy 2: per vertical per state: `Walmart supplier "{signal}" {state}`
  3. For each result: detect signals in title+snippet (case-insensitive), filter consultant domains, only keep if >= 1 signal detected
  4. Return ProspectRecords with source_channel="sqep", compliance_signals populated

Signal detection: `_detect_signals(text) -> list[str]`:
- "sqep" → sqep_mentioned
- "otif" → otif_mentioned
- ("walmart" and ("supplier" or "vendor")) → walmart_supplier
- any of ("chargeback", "fine", "penalty", "deduction") → compliance_pain

Consultant filter list: 8thandwalton, carbon6, vendormint, newnexusgroup, ozarkconsulting, coldstreamlogistics, rjwgroup, 5gsales, supplypike

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_modules.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add modules/sqep.py tests/test_modules.py
git commit -m "feat: add SQEP compliance signal scraper module"
```

---

## Task 9: Import Search Module

**Files:**
- Create: `modules/import_search.py`
- Modify: `tests/test_modules.py` (append tests)

- [ ] **Step 1: Write failing test**

Append to `tests/test_modules.py`:

```python
from modules.import_search import ImportSearchModule

def test_import_search_produces_records():
    config = {
        "verticals": {"pharma": {"keywords": ["pharma"]}},
        "import_keywords": {"pharma": ["pharmaceutical ingredient", "API bulk drug"]},
        "icp": {}
    }
    mock_client = MagicMock()
    mock_client.search.return_value = [
        {"title": "Acme Pharma - ImportYeti", "link": "https://importyeti.com/company/acme-pharma",
         "snippet": "Imports pharmaceutical ingredients"},
        {"title": "Beta Drug Imports | US Importer", "link": "https://betadrug.com",
         "snippet": "Leading importer of API bulk drug substances in TX"}
    ]

    module = ImportSearchModule(config, states=["TX"], search_client=mock_client)
    results = module.run(active_verticals=["pharma"])

    assert len(results) >= 1
    assert any(r.source_channel == "import" for r in results)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_modules.py::test_import_search_produces_records -v`
Expected: FAIL

- [ ] **Step 3: Implement `modules/import_search.py`**

`ImportSearchModule(BaseModule)`:
- `channel_name` = "import"
- `run(active_verticals)`:
  1. Strategy 1: for each vertical, each import_keyword: `site:importyeti.com "{keyword}"`
  2. Strategy 2: for each vertical, each import_keyword, each state: `"{keyword}" importer {state} manufacturer`
  3. Parse company name from title, domain from URL. For ImportYeti results, extract company name from title (strip " - ImportYeti" suffix).
  4. Return ProspectRecords with source_channel="import", import_products from keyword, snippet in notes.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_modules.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add modules/import_search.py tests/test_modules.py
git commit -m "feat: add import/export data search module"
```

---

## Task 10: Apollo Module

**Files:**
- Create: `modules/apollo.py`
- Modify: `tests/test_modules.py` (append tests)

- [ ] **Step 1: Write failing test**

Append to `tests/test_modules.py`:

```python
from modules.apollo import ApolloModule

def test_apollo_produces_records_with_contacts():
    config = {
        "verticals": {"pharma": {"keywords": ["pharmaceutical manufacturer", "CDMO", "drug manufacturer"]}},
        "icp": {"employee_min": 25, "employee_max": 2000, "revenue_min": 5000000, "revenue_max": 500000000},
        "apollo": {"per_page": 25, "max_pages_per_search": 1, "plan_limit": 30000}
    }

    mock_company_response = MagicMock()
    mock_company_response.status_code = 200
    mock_company_response.json.return_value = {
        "organizations": [{
            "id": "abc123", "name": "Acme Pharma", "city": "Houston", "state": "Texas",
            "phone": "555-1234", "primary_domain": "acmepharma.com",
            "estimated_num_employees": 150, "annual_revenue_printed": "$10M-$50M",
            "industry": "Pharmaceuticals", "keywords": ["pharma", "drug"]
        }]
    }

    mock_people_response = MagicMock()
    mock_people_response.status_code = 200
    mock_people_response.json.return_value = {
        "people": [{
            "first_name": "Jane", "last_name": "Doe",
            "title": "VP of Logistics", "email": "jane@acmepharma.com"
        }]
    }

    with patch("modules.apollo.requests.post") as mock_post:
        mock_post.side_effect = [mock_company_response, mock_people_response]
        module = ApolloModule(config, states=["TX"], api_key="test_key")
        results = module.run(active_verticals=["pharma"])

    assert len(results) >= 1
    acme = results[0]
    assert acme.website == "acmepharma.com"
    assert acme.contact_name == "Jane Doe"
    assert acme.contact_title == "VP of Logistics"
    assert acme.contact_source == "apollo"
    assert acme.estimated_revenue == 10000000  # lower bound
    assert acme.source_channel == "apollo"

def test_apollo_filters_revenue_outside_icp():
    config = {
        "verticals": {"pharma": {"keywords": ["pharma"]}},
        "icp": {"employee_min": 25, "employee_max": 2000, "revenue_min": 5000000, "revenue_max": 500000000},
        "apollo": {"per_page": 25, "max_pages_per_search": 1, "plan_limit": 30000}
    }

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "organizations": [{
            "id": "xyz", "name": "Mega Pharma", "primary_domain": "mega.com",
            "estimated_num_employees": 100, "annual_revenue_printed": "$1B+"
        }]
    }

    with patch("modules.apollo.requests.post", return_value=mock_response):
        module = ApolloModule(config, states=["TX"], api_key="test_key")
        results = module.run(active_verticals=["pharma"])

    assert len(results) == 0  # $1B+ exceeds $500M max
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_modules.py::test_apollo_produces_records_with_contacts -v`
Expected: FAIL

- [ ] **Step 3: Implement `modules/apollo.py`**

`ApolloModule(BaseModule)`:
- `__init__(config, states, api_key)` — store api_key, init credit counters
- `channel_name` = "apollo"
- `run(active_verticals)`:
  1. For each vertical, top 3 keywords: POST company search, paginate up to max_pages
  2. Parse revenue (`_parse_revenue`), filter by ICP revenue range (keep None)
  3. For each company: POST people search for logistics/operations contacts
  4. Apply contact fallback priority
  5. Return ProspectRecords with source_channel="apollo", contact_source="apollo"

`_parse_revenue(s: str | None) -> int | None`:
- Handle: "$10M-$50M" → 10000000, "$1M-$10M" → 1000000, "$100K-$500K" → 100000, "$1B+" → 1000000000
- Regex: extract first dollar amount, parse multiplier (K=1000, M=1000000, B=1000000000)
- Return None if null/unparseable

`_select_contact(people: list) -> dict | None`:
- Priority 1: title matches logistics keywords (logistics, supply chain, transportation, shipping, distribution, freight)
- Priority 2: title matches operations keywords (operations, COO, VP Operations, General Manager, Plant Manager)
- Priority 3: return None

Credit tracking: `company_search_credits`, `people_search_credits` — increment on each API call, log at end.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_modules.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add modules/apollo.py tests/test_modules.py
git commit -m "feat: add Apollo company and contact search module"
```

---

## Task 11: Hunter Enrichment

**Files:**
- Create: `enrichment/hunter.py`
- Create: `tests/test_enrichment.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_enrichment.py
import pytest
from unittest.mock import MagicMock, patch
from enrichment.hunter import HunterEnrichment
from models import ProspectRecord

def test_hunter_finds_logistics_contact():
    config = {"hunter": {"max_searches_per_run": 100, "max_verifications_per_run": 50}}
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": {
            "pattern": "{first}.{last}",
            "emails": [
                {"value": "j.smith@acme.com", "first_name": "John", "last_name": "Smith",
                 "position": "Director of Logistics", "department": "logistics",
                 "confidence": 91, "type": "personal"},
                {"value": "m.jones@acme.com", "first_name": "Mary", "last_name": "Jones",
                 "position": "Marketing Manager", "department": "marketing",
                 "confidence": 95, "type": "personal"}
            ]
        }
    }

    prospects = [
        ProspectRecord(company_name="Acme", website="acme.com", source_channel="web_search")
    ]

    with patch("enrichment.hunter.requests.get", return_value=mock_response):
        enricher = HunterEnrichment(config, api_key="test_key")
        results = enricher.enrich(prospects)

    assert results[0].contact_name == "John Smith"
    assert results[0].contact_title == "Director of Logistics"
    assert results[0].email_confidence == 91
    assert results[0].contact_source == "hunter"

def test_hunter_skips_apollo_contacts():
    config = {"hunter": {"max_searches_per_run": 100}}
    prospects = [
        ProspectRecord(company_name="Acme", website="acme.com",
                       contact_email="j@acme.com", contact_source="apollo")
    ]

    enricher = HunterEnrichment(config, api_key="test_key")
    with patch("enrichment.hunter.requests.get") as mock_get:
        results = enricher.enrich(prospects)
        mock_get.assert_not_called()

    assert results[0].contact_source == "apollo"

def test_hunter_stores_pattern_when_no_match():
    config = {"hunter": {"max_searches_per_run": 100}}
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": {"pattern": "{first}.{last}", "emails": []}
    }

    prospects = [ProspectRecord(company_name="Acme", website="acme.com")]

    with patch("enrichment.hunter.requests.get", return_value=mock_response):
        enricher = HunterEnrichment(config, api_key="test_key")
        results = enricher.enrich(prospects)

    assert "Hunter email pattern" in results[0].notes

def test_hunter_verify_emails():
    config = {"hunter": {"max_verifications_per_run": 50}}
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": {"status": "valid"}}

    with patch("enrichment.hunter.requests.get", return_value=mock_response):
        enricher = HunterEnrichment(config, api_key="test_key")
        status = enricher.verify_email("j@acme.com")

    assert status == "valid"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_enrichment.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `enrichment/hunter.py`**

`HunterEnrichment`:
- `__init__(config, api_key)` — store config, api_key, init `search_credits_used = 0`
- `enrich(prospects) -> list[ProspectRecord]`:
  1. Filter to prospects where website non-empty, contact_email empty, contact_source != "apollo"
  2. For each (up to max_searches_per_run): call domain search API
  3. Apply contact selection logic per spec (logistics first, then operations/COO, then blank, then pattern in notes)
  4. `time.sleep(2)` between calls
  5. Log summary
- `verify_email(email) -> str` — call verifier API, return status
- `verify_batch(emails, limit) -> dict[str, str]` — verify up to limit emails

Contact selection: `_select_contact(emails, pattern, domain)`:
- Filter by logistics/operations titles
- Pick highest confidence among matches
- If no match: leave blank
- If no emails but pattern: store in notes
- Return updated fields

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_enrichment.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add enrichment/hunter.py tests/test_enrichment.py
git commit -m "feat: add Hunter.io email enrichment and verification"
```

---

## Task 12: Excel and CSV Export

**Files:**
- Create: `output/exporter.py`
- Create: `tests/test_exporter.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_exporter.py
import pytest
import os
from openpyxl import load_workbook
from output.exporter import export_xlsx, export_csv

def test_export_xlsx_creates_4_sheets(tmp_path):
    prospects = [
        {"company_name": "Acme", "state": "TX", "score": 80, "tier": "HOT",
         "status": "NEW", "email_verified": "valid", "first_seen": "2026-03-24",
         "vertical": "food", "contact_email": "j@acme.com", "source_channel": "web_search"},
        {"company_name": "Beta", "state": "CA", "score": 30, "tier": "NURTURE",
         "status": "NEW", "email_verified": "", "first_seen": "2026-03-24",
         "vertical": "pharma", "contact_email": "", "source_channel": "apollo"}
    ]
    run_history = [{"run_date": "2026-03-24", "new_count": 2, "dedup_count": 2}]
    pipeline_stats = {"status_counts": {"NEW": 2}, "tier_counts": {"HOT": 1, "NURTURE": 1}}

    path = str(tmp_path / "test.xlsx")
    export_xlsx(path, prospects, run_history, pipeline_stats, run_date="2026-03-24")

    wb = load_workbook(path)
    assert len(wb.sheetnames) == 4
    assert wb.sheetnames[0] == "New This Run"
    assert wb.sheetnames[1] == "Full Prospects"
    assert wb.sheetnames[2] == "Pipeline Dashboard"
    assert wb.sheetnames[3] == "Run Log"

    # Check New This Run has data
    ws = wb["New This Run"]
    assert ws.max_row >= 2  # header + at least 1 data row

def test_export_csv_creates_file(tmp_path):
    prospects = [
        {"company_name": "Acme", "state": "TX", "score": 80, "tier": "HOT"}
    ]
    path = str(tmp_path / "test.csv")
    export_csv(path, prospects)
    assert os.path.exists(path)
    with open(path) as f:
        lines = f.readlines()
    assert len(lines) == 2  # header + 1 row
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_exporter.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `output/exporter.py`**

`export_xlsx(path, prospects, run_history, pipeline_stats, run_date)`:
- Sheet 1 "New This Run": filter prospects where first_seen = run_date, write with headers, apply formatting
- Sheet 2 "Full Prospects": all prospects, full formatting per spec (navy headers, alternating rows, color-coded tier/status/verified, frozen pane, auto-filter, score gradient)
- Sheet 3 "Pipeline Dashboard": summary tables laid out vertically per spec (rows 1-2 title, 4-12 status counts, 14-19 tier counts, 21-23 run summary, 25-36 top 10 new)
- Sheet 4 "Run Log": run_history rows with headers

Color constants:
- Navy header: `003366` with white text
- HOT: `FF4444`, WARM: `FF8C00`, NURTURE: `FFD700`, PARK: `C0C0C0`
- Status: NEW=`4A90D9`, CONTACTED=`FF8C00`, ENGAGED=`28A745`, WON=`1B5E20`, LOST=`DC3545`, PARKED=`C0C0C0`
- Verified: valid=`28A745`, invalid=`DC3545`, accept_all=`FFD700`
- Alternating rows: `F2F2F2`

`export_csv(path, prospects)`:
- Write all fields as CSV, sorted by score desc.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_exporter.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add output/exporter.py tests/test_exporter.py
git commit -m "feat: add formatted Excel (4 sheets) and CSV export"
```

---

## Task 13: Checkpoint System

**Files:**
- Create: `utils/checkpoints.py`
- Create: `tests/test_checkpoints.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_checkpoints.py
import pytest
import json
from utils.checkpoints import CheckpointManager
from models import ProspectRecord

def test_save_and_load(tmp_path):
    config = {"checkpoints": {"directory": str(tmp_path), "keep_on_success": False}}
    mgr = CheckpointManager(config)
    mgr.start_run()

    prospects = [ProspectRecord(company_name="Acme", website="acme.com").to_dict()]
    mgr.save("web_search", prospects, credits_used=50)

    completed = mgr.get_completed_modules()
    assert "web_search" in completed

    loaded = mgr.load("web_search")
    assert len(loaded) == 1
    assert loaded[0]["company_name"] == "Acme"

def test_canonical_numbering(tmp_path):
    config = {"checkpoints": {"directory": str(tmp_path), "keep_on_success": False}}
    mgr = CheckpointManager(config)
    mgr.start_run()

    mgr.save("apollo", [ProspectRecord(company_name="A").to_dict()], credits_used=10)
    # Apollo should be 04, not 01
    import os
    files = os.listdir(mgr.run_dir)
    assert any("04_apollo" in f for f in files)

def test_cleanup(tmp_path):
    config = {"checkpoints": {"directory": str(tmp_path), "keep_on_success": False}}
    mgr = CheckpointManager(config)
    mgr.start_run()
    mgr.save("web_search", [], credits_used=0)
    mgr.cleanup(keep=False)
    import os
    assert not os.path.exists(mgr.run_dir)

def test_load_all_combines(tmp_path):
    config = {"checkpoints": {"directory": str(tmp_path), "keep_on_success": False}}
    mgr = CheckpointManager(config)
    mgr.start_run()
    mgr.save("web_search", [ProspectRecord(company_name="A").to_dict()], credits_used=10)
    mgr.save("sqep", [ProspectRecord(company_name="B").to_dict()], credits_used=5)
    all_prospects = mgr.load_all()
    assert len(all_prospects) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_checkpoints.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `utils/checkpoints.py`**

`CheckpointManager`:
- `__init__(config)` — read checkpoint dir from config, init run_dir as None
- `start_run()` — create `checkpoints/run_{timestamp}/` dir, store as run_dir
- `save(module_name, prospects, credits_used)` — serialize to `{order}_{module}_complete.json` using canonical numbering (01=web_search, 02=sqep, 03=import_search, 04=apollo, 05=dedup, 06=hunter). JSON schema: `{module, timestamp, credits_used, prospect_count, prospects: [dict]}`.
- `get_completed_modules() -> set[str]` — scan latest run dir for checkpoint files, return module names
- `load(module_name) -> list[dict]` — load and return prospects from checkpoint file
- `load_all() -> list[dict]` — load all checkpoint files, combine prospects
- `cleanup(keep=False)` — delete run dir if not keep

Module order map: `{"web_search": "01", "sqep": "02", "import_search": "03", "apollo": "04", "dedup": "05", "hunter": "06"}`

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_checkpoints.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add utils/checkpoints.py tests/test_checkpoints.py
git commit -m "feat: add checkpoint system for crash recovery"
```

---

## Task 14: Credit Estimator

**Files:**
- Create: `utils/credits.py`
- Create: `tests/test_credits.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_credits.py
import pytest
from utils.credits import estimate_credits, format_credit_warning, format_credit_summary

def test_estimate_south_central_all_verticals():
    """South central (4 states) x 5 verticals should match spec example range."""
    config = {
        "verticals": {
            "fragrance": {"keywords": ["a", "b", "c", "d", "e", "f", "g", "h"],
                          "sqep_product_signals": ["candle", "air freshener", "scented product", "home fragrance"]},
            "flavor": {"keywords": ["a", "b", "c", "d", "e", "f", "g", "h"],
                       "sqep_product_signals": ["seasoning", "flavoring", "extract", "spice"]},
            "food": {"keywords": ["a", "b", "c", "d", "e", "f", "g", "h"],
                     "sqep_product_signals": ["snack", "food", "beverage", "condiment", "bakery", "frozen", "dairy", "sauce"]},
            "pharma": {"keywords": ["a", "b", "c", "d", "e", "f", "g", "h"],
                       "sqep_product_signals": ["OTC", "over-the-counter", "pharmaceutical"]},
            "nutraceutical": {"keywords": ["a", "b", "c", "d", "e", "f", "g", "h"],
                              "sqep_product_signals": ["vitamin", "supplement", "protein", "probiotic", "wellness", "gummy"]}
        },
        "sqep_search_terms": ["term1", "term2", "term3", "term4", "term5"],
        "import_keywords": {"fragrance": ["a", "b", "c"], "flavor": ["a", "b", "c"],
                           "food": ["a", "b", "c"], "pharma": ["a", "b", "c"],
                           "nutraceutical": ["a", "b", "c"]},
        "search_api": {"plan_limit": 1000},
        "apollo": {"per_page": 25, "max_pages_per_search": 4, "plan_limit": 30000},
        "hunter": {"max_searches_per_run": 100, "search_credit_limit": 1000}
    }
    estimates = estimate_credits(config,
                                 active_verticals=["fragrance", "flavor", "food", "pharma", "nutraceutical"],
                                 active_states=["TX", "LA", "AR", "OK"],
                                 active_channels=["web_search", "sqep", "import_search", "apollo"])
    assert estimates["serpapi"]["estimated"] > 0
    assert estimates["apollo"]["estimated"] > 0
    assert estimates["hunter"]["estimated"] > 0

def test_estimate_skipped_channels():
    config = {
        "verticals": {"food": {"keywords": ["a", "b", "c"], "sqep_product_signals": ["snack"]}},
        "sqep_search_terms": ["term1"],
        "import_keywords": {"food": ["a"]},
        "search_api": {"plan_limit": 1000},
        "apollo": {"per_page": 25, "max_pages_per_search": 4, "plan_limit": 30000},
        "hunter": {"max_searches_per_run": 100, "search_credit_limit": 1000}
    }
    estimates = estimate_credits(config,
                                 active_verticals=["food"],
                                 active_states=["TX"],
                                 active_channels=["web_search"])  # only web_search
    assert estimates["serpapi"]["estimated"] > 0
    assert estimates["apollo"]["estimated"] == 0  # not active

def test_format_warning_highlights_over_limit():
    estimates = {
        "serpapi": {"estimated": 1200, "limit": 1000},
        "apollo": {"estimated": 100, "limit": 30000},
        "hunter": {"estimated": 50, "limit": 1000}
    }
    warning = format_credit_warning(estimates)
    assert "WARNING" in warning or "⚠" in warning  # over-limit flagged

def test_format_summary():
    actuals = {"serpapi": 115, "apollo": 283, "hunter_search": 75, "hunter_verify": 0}
    limits = {"serpapi": 1000, "apollo": 30000, "hunter_search": 1000, "hunter_verify": 1000}
    summary = format_credit_summary(actuals, limits)
    assert "115" in summary
    assert "283" in summary
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_credits.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `utils/credits.py`**

`estimate_credits(config, active_verticals, active_states, active_channels) -> dict`:
- Calculate per spec formulas:
  - SerpAPI (only count channels in active_channels):
    - web_search: `len(active_verticals) * len(active_states) * 3` (top 3 keywords) + `sum(len(signals) for v)` (global SQEP signals)
    - sqep: `len(sqep_search_terms)` + `sum(len(signals) for v) * len(active_states)`
    - import: `sum(len(import_keywords[v]) for v) * 2` (strategy 1 global + strategy 2 per-state is approximated as *2 per the spec formula)
  - Apollo (only if in active_channels): `len(active_verticals) * 3 * max_pages` (company) + upper bound people
  - Hunter: "up to {max_searches_per_run}" (always shown unless enrichment skipped)
- Return `{"serpapi": {"estimated": N, "limit": M}, "apollo": {...}, "hunter": {...}}`

`format_credit_warning(estimates) -> str`:
- Format as spec shows, highlight any over-limit with warning

`format_credit_summary(actuals: dict, limits: dict) -> str`:
- Format actual usage: "Credits used — SerpAPI: 115/1000, Apollo: 283/30000, ..."

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_credits.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add utils/credits.py
git commit -m "feat: add credit estimation and summary utilities"
```

---

## Task 15: CLI Argument Parsing and Database Commands

**Files:**
- Create: `run.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write failing tests for CLI parsing and DB commands**

```python
# tests/test_cli.py
import pytest
import os
import yaml
from unittest.mock import patch, MagicMock
from run import parse_args, resolve_states, check_api_keys, handle_db_command, load_config

ALL_STATES = ["AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA",
              "KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ",
              "NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT",
              "VA","WA","WV","WI","WY"]

def test_parse_args_defaults():
    args = parse_args([])
    assert args.states is None
    assert args.nationwide is False
    assert args.dry_run is False

def test_parse_args_states():
    args = parse_args(["--states", "south_central,southeast"])
    assert args.states == "south_central,southeast"

def test_resolve_states_named_list():
    config = {"state_lists": {"south_central": {"default": True, "states": ["TX", "LA", "AR", "OK"]}}}
    states = resolve_states(config, states_arg="south_central", nationwide=False)
    assert states == ["TX", "LA", "AR", "OK"]

def test_resolve_states_nationwide():
    config = {"state_lists": {}}
    states = resolve_states(config, states_arg=None, nationwide=True)
    assert len(states) == 50

def test_resolve_states_nonexistent_errors():
    config = {"state_lists": {"south_central": {"states": ["TX"]}}}
    with pytest.raises(SystemExit):
        resolve_states(config, states_arg="nonexistent", nationwide=False)

def test_resolve_states_default():
    config = {"state_lists": {"south_central": {"default": True, "states": ["TX", "LA"]}}}
    states = resolve_states(config, states_arg=None, nationwide=False)
    assert states == ["TX", "LA"]

def test_check_api_keys_all_missing():
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(SystemExit):
            check_api_keys()

def test_check_api_keys_partial(capsys):
    with patch.dict(os.environ, {"SERPAPI_KEY": "test"}, clear=True):
        keys = check_api_keys()
    assert keys["serpapi"] == "test"
    assert keys["apollo"] is None
    captured = capsys.readouterr()
    assert "APOLLO_API_KEY not set" in captured.out

def test_handle_db_search(tmp_path):
    from persistence.database import ProspectDB
    from models import ProspectRecord
    db = ProspectDB(str(tmp_path / "test.db"))
    p = ProspectRecord(company_name="Acme Food", state="TX", vertical="food",
                       website="acme.com", source_channel="web_search", score=80)
    db.upsert([p])
    results = handle_db_command("search", db, query="Acme TX")
    assert len(results) >= 1

def test_handle_db_export(tmp_path):
    from persistence.database import ProspectDB
    from models import ProspectRecord
    db = ProspectDB(str(tmp_path / "test.db"))
    p = ProspectRecord(company_name="Acme", website="acme.com", source_channel="web_search")
    db.upsert([p])
    export_path = str(tmp_path / "export.csv")
    handle_db_command("export_db", db, export_path=export_path)
    assert os.path.exists(export_path)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `run.py` — argument parsing, config loading, state resolution, API key check, DB commands**

Using `argparse` for CLI. This step implements:

1. `parse_args(argv=None)` — all argparse setup with groups:
   - Scraping: `--states`, `--nationwide`, `--verticals`, `--channels`, `--skip-enrichment`, `--skip-scoring`, `--dry-run`, `--resume`
   - Verification: `--verify-emails`, `--tier`, `--all`
   - Database: `--set-status`, `--pipeline`, `--list-status`, `--search`, `--db-stats`, `--export-db`, `--reset-db`, `--confirm`, `--note`

2. `load_config(path="config.yaml")` — load yaml, load .env

3. `resolve_states(config, states_arg, nationwide)` — lookup named lists, union multiples, all 50 for nationwide, error on nonexistent

4. `check_api_keys()` — check env vars, warn on missing, error if all missing. Return dict of available keys.

5. `handle_db_command(command, db, **kwargs)` — dispatch to DB methods for: set_status, pipeline, list_status, search, db_stats, export_db, reset_db

6. `main()` — entry point that routes to pipeline, verification, or DB command based on args

All 50 states constant:
```python
ALL_STATES = ["AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA",
              "KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ",
              "NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT",
              "VA","WA","WV","WI","WY"]
```

Leave `run_pipeline()` and `run_verification()` as stubs that print "Not implemented yet" — Task 16 fills these in.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cli.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add run.py tests/test_cli.py
git commit -m "feat: add CLI argument parsing, config loading, and database commands"
```

---

## Task 16: Pipeline Orchestration

**Files:**
- Modify: `run.py` (fill in `run_pipeline` and `run_verification`)
- Create: `tests/test_pipeline.py`

- [ ] **Step 1: Write failing integration tests**

```python
# tests/test_pipeline.py
import pytest
import os
import yaml
from unittest.mock import MagicMock, patch
from run import run_pipeline, run_verification

def write_test_config(tmp_path):
    config = {
        "icp": {"revenue_min": 5000000, "revenue_max": 500000000, "employee_min": 25, "employee_max": 2000},
        "state_lists": {"test": {"default": True, "states": ["TX"]}},
        "verticals": {"food": {"keywords": ["food manufacturer"], "sqep_product_signals": ["snack"]}},
        "sqep_search_terms": ["Walmart SQEP supplier"],
        "import_keywords": {"food": ["food ingredient"]},
        "search_api": {"provider": "serpapi", "plan_limit": 1000},
        "apollo": {"enabled": True, "per_page": 25, "max_pages_per_search": 1, "plan_limit": 30000},
        "hunter": {"enabled": True, "max_searches_per_run": 10, "max_verifications_per_run": 5,
                   "search_credit_limit": 1000, "verification_credit_limit": 1000},
        "scoring": {
            "signal_density": {"1_source": 5, "2_sources": 15, "3_sources": 25, "4_plus_sources": 35},
            "compliance": {"walmart_supplier": 10, "sqep_mentioned": 10, "otif_mentioned": 10, "compliance_pain": 10},
            "geography": {"in_target_state": 15, "other": 0},
            "enrichment": {"verified_email_logistics_title": 15, "email_non_logistics_title": 10,
                          "email_pattern_found": 5, "contact_name_no_email": 3, "website_only": 0},
            "vertical_multipliers": {"food": 1.3, "unknown": 0.8},
            "tiers": {"hot": 70, "warm": 45, "nurture": 25}
        },
        "database": {"path": str(tmp_path / "test.db")},
        "checkpoints": {"directory": str(tmp_path / "checkpoints"), "keep_on_success": False},
        "output": {"directory": str(tmp_path / "output"), "filename_prefix": "test", "formats": ["xlsx", "csv"]}
    }
    config_path = str(tmp_path / "config.yaml")
    with open(config_path, "w") as f:
        yaml.dump(config, f)
    return config_path, config

def test_pipeline_dry_run(tmp_path, capsys):
    config_path, _ = write_test_config(tmp_path)
    with patch.dict(os.environ, {"SERPAPI_KEY": "test", "APOLLO_API_KEY": "test", "HUNTER_API_KEY": "test"}):
        run_pipeline(config_path=config_path, dry_run=True, states_arg="test")
    captured = capsys.readouterr()
    assert "Estimated credit usage" in captured.out

def test_pipeline_with_mocked_modules(tmp_path):
    from models import ProspectRecord
    config_path, config = write_test_config(tmp_path)
    os.makedirs(str(tmp_path / "output"), exist_ok=True)

    mock_prospects = [
        ProspectRecord(company_name="Acme Food", website="acme.com",
                       state="TX", vertical="food", source_channel="web_search")
    ]

    with patch.dict(os.environ, {"SERPAPI_KEY": "test", "APOLLO_API_KEY": "test", "HUNTER_API_KEY": "test"}):
        with patch("run.WebSearchModule") as MockWS, \
             patch("run.SQEPModule") as MockSQ, \
             patch("run.ImportSearchModule") as MockIM, \
             patch("run.ApolloModule") as MockAP, \
             patch("run.HunterEnrichment") as MockHU:
            MockWS.return_value.run.return_value = mock_prospects
            MockSQ.return_value.run.return_value = []
            MockIM.return_value.run.return_value = []
            MockAP.return_value.run.return_value = []
            MockHU.return_value.enrich.return_value = mock_prospects

            run_pipeline(config_path=config_path, states_arg="test")

    # Check output was generated
    assert os.path.exists(str(tmp_path / "output"))

def test_pipeline_missing_key_disables_module(tmp_path, capsys):
    config_path, _ = write_test_config(tmp_path)
    with patch.dict(os.environ, {"SERPAPI_KEY": "test"}, clear=True):
        # Apollo and Hunter keys missing — should warn and continue
        with patch("run.WebSearchModule") as MockWS, \
             patch("run.SQEPModule") as MockSQ, \
             patch("run.ImportSearchModule") as MockIM:
            MockWS.return_value.run.return_value = []
            MockSQ.return_value.run.return_value = []
            MockIM.return_value.run.return_value = []
            run_pipeline(config_path=config_path, states_arg="test")

    captured = capsys.readouterr()
    assert "APOLLO_API_KEY not set" in captured.out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pipeline.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `run_pipeline` and `run_verification` in `run.py`**

**`run_pipeline(config_path, states_arg, nationwide, verticals, channels, skip_enrichment, skip_scoring, dry_run, resume)`:**
1. Load config + check API keys
2. Resolve states
3. Determine active verticals and channels
4. Estimate credits, print warning, prompt user (or exit for dry_run)
5. Init checkpoint manager
6. If resume: load checkpoints, skip completed modules
7. Run modules in order (skip if missing API key):
   - web_search, sqep, import_search (need SERPAPI_KEY)
   - apollo (needs APOLLO_API_KEY)
   - Checkpoint after each
8. Combine results, deduplicate (checkpoint)
9. Hunter enrichment if not skipped and HUNTER_API_KEY present (checkpoint). Warn if Apollo aborted.
10. Score prospects
11. Upsert to DB, record run history
12. Export XLSX + CSV
13. Print credit summary
14. Clean up checkpoints

**`run_verification(config_path, tier, all_tiers)`:**
1. Load config + .env
2. Open DB, query for_verification with tier filter
3. Run Hunter verify_batch
4. Update DB for each result
5. Print summary

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pipeline.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add run.py tests/test_pipeline.py
git commit -m "feat: add pipeline orchestration with module sequencing and resume"
```

---

## Task 17: End-to-End Smoke Test

**Files:**
- No new files — validate everything works together

- [ ] **Step 1: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 2: Test CLI help**

Run: `python run.py --help`
Expected: Shows all flags and usage

- [ ] **Step 3: Test dry run**

Create a `.env` with test keys (or real keys if available). Run:
```bash
python run.py --dry-run --states south_central --verticals fragrance
```
Expected: Credit estimates printed, no API calls made

- [ ] **Step 4: Test DB commands with empty DB**

```bash
python run.py --db-stats
python run.py --pipeline
```
Expected: Shows zeroes, no errors

- [ ] **Step 5: Commit any fixes**

```bash
git add -A
git commit -m "fix: address issues found in smoke testing"
```

- [ ] **Step 6: Push to GitHub**

```bash
git push origin master
```

---

**Total: 17 tasks. Estimated implementation time depends on execution approach chosen below.**
