"""
Tests for Hunter.io email enrichment (enrichment/hunter.py).
"""

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
    mock_response.raise_for_status = MagicMock()
    prospects = [ProspectRecord(company_name="Acme", website="acme.com", source_channel="web_search")]

    with patch("enrichment.hunter.requests.get", return_value=mock_response), \
         patch("enrichment.hunter.time.sleep"):
        enricher = HunterEnrichment(config, api_key="test_key")
        results = enricher.enrich(prospects)

    assert results[0].contact_name == "John Smith"
    assert results[0].contact_title == "Director of Logistics"
    assert results[0].email_confidence == 91
    assert results[0].contact_source == "hunter"


def test_hunter_skips_apollo_contacts():
    config = {"hunter": {"max_searches_per_run": 100}}
    prospects = [ProspectRecord(company_name="Acme", website="acme.com",
                                contact_email="j@acme.com", contact_source="apollo")]
    enricher = HunterEnrichment(config, api_key="test_key")
    with patch("enrichment.hunter.requests.get") as mock_get, \
         patch("enrichment.hunter.time.sleep"):
        results = enricher.enrich(prospects)
        mock_get.assert_not_called()
    assert results[0].contact_source == "apollo"


def test_hunter_stores_pattern_when_no_match():
    config = {"hunter": {"max_searches_per_run": 100}}
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": {"pattern": "{first}.{last}", "emails": []}}
    mock_response.raise_for_status = MagicMock()
    prospects = [ProspectRecord(company_name="Acme", website="acme.com")]

    with patch("enrichment.hunter.requests.get", return_value=mock_response), \
         patch("enrichment.hunter.time.sleep"):
        enricher = HunterEnrichment(config, api_key="test_key")
        results = enricher.enrich(prospects)

    assert "Hunter email pattern" in results[0].notes


def test_hunter_verify_emails():
    config = {"hunter": {"max_verifications_per_run": 50}}
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": {"status": "valid"}}
    mock_response.raise_for_status = MagicMock()

    with patch("enrichment.hunter.requests.get", return_value=mock_response), \
         patch("enrichment.hunter.time.sleep"):
        enricher = HunterEnrichment(config, api_key="test_key")
        status = enricher.verify_email("j@acme.com")

    assert status == "valid"
