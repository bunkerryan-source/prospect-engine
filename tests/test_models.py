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
    assert normalize_company_name("The  Acme  Group LLC") == "the acme"
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
