import pytest
from unittest.mock import MagicMock
from modules.web_search import WebSearchModule
from modules.sqep import SQEPModule
from modules.import_search import ImportSearchModule

def test_web_search_produces_records():
    config = {
        "verticals": {
            "fragrance": {
                "keywords": ["fragrance manufacturer", "aroma chemical"],
                "sqep_product_signals": ["candle", "air freshener"]
            }
        },
        "icp": {}
    }
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
    assert not any(r.website == "youtube.com" for r in results)

def test_web_search_extracts_company_name():
    config = {"verticals": {"food": {"keywords": ["food"], "sqep_product_signals": []}}, "icp": {}}
    mock_client = MagicMock()
    mock_client.search.return_value = [
        {"title": "Acme Foods - Best in TX", "link": "https://acmefoods.com", "snippet": "test"}
    ]
    module = WebSearchModule(config, states=["TX"], search_client=mock_client)
    results = module.run(active_verticals=["food"])
    assert results[0].company_name == "Acme Foods"

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

def test_import_search_strips_importyeti_suffix():
    config = {
        "verticals": {"food": {"keywords": ["food"]}},
        "import_keywords": {"food": ["food ingredient"]},
        "icp": {}
    }
    mock_client = MagicMock()
    mock_client.search.return_value = [
        {"title": "Acme Foods Inc - ImportYeti", "link": "https://importyeti.com/company/acme-foods",
         "snippet": "Import data"}
    ]
    module = ImportSearchModule(config, states=["TX"], search_client=mock_client)
    results = module.run(active_verticals=["food"])
    assert results[0].company_name == "Acme Foods Inc"
