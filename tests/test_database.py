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

def test_pipeline_stats(db):
    p1 = ProspectRecord(company_name="A", website="a.com", source_channel="web_search", score=80, tier="HOT")
    p2 = ProspectRecord(company_name="B", website="b.com", source_channel="web_search", score=50, tier="WARM")
    db.upsert([p1, p2])
    stats = db.get_pipeline_stats()
    assert stats["status_counts"]["NEW"] == 2
    assert stats["tier_counts"]["HOT"] == 1
    assert stats["tier_counts"]["WARM"] == 1

def test_run_history(db):
    db.record_run(states="TX,LA", verticals="food,pharma", channels="web_search,apollo",
                  raw_count=100, dedup_count=60, new_count=50, updated_count=10,
                  hot=10, warm=20, nurture=15, park=15, avg_score=55.0,
                  duration=120, serpapi=50, apollo=100, hunter_search=30, hunter_verify=0)
    history = db.get_run_history()
    assert len(history) == 1
    assert history[0]["new_count"] == 50
