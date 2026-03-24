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


# ---------------------------------------------------------------------------
# Apollo module tests
# ---------------------------------------------------------------------------

from unittest.mock import patch, MagicMock
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
    mock_company_response.raise_for_status = MagicMock()

    mock_people_response = MagicMock()
    mock_people_response.status_code = 200
    mock_people_response.json.return_value = {
        "people": [{
            "first_name": "Jane", "last_name": "Doe",
            "title": "VP of Logistics", "email": "jane@acmepharma.com"
        }]
    }
    mock_people_response.raise_for_status = MagicMock()

    with patch("modules.apollo.requests.post") as mock_post, \
         patch("modules.apollo.time.sleep"):
        mock_post.side_effect = [mock_company_response, mock_people_response]
        module = ApolloModule(config, states=["TX"], api_key="test_key")
        results = module.run(active_verticals=["pharma"])

    assert len(results) >= 1
    acme = results[0]
    assert acme.website == "acmepharma.com"
    assert acme.contact_name == "Jane Doe"
    assert acme.contact_title == "VP of Logistics"
    assert acme.contact_source == "apollo"
    assert acme.estimated_revenue == 10000000
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
    mock_response.raise_for_status = MagicMock()

    with patch("modules.apollo.requests.post", return_value=mock_response), \
         patch("modules.apollo.time.sleep"):
        module = ApolloModule(config, states=["TX"], api_key="test_key")
        results = module.run(active_verticals=["pharma"])

    assert len(results) == 0  # $1B+ exceeds $500M max

def test_apollo_parse_revenue():
    from modules.apollo import ApolloModule
    assert ApolloModule._parse_revenue("$10M-$50M") == 10000000
    assert ApolloModule._parse_revenue("$1M-$10M") == 1000000
    assert ApolloModule._parse_revenue("$100K-$500K") == 100000
    assert ApolloModule._parse_revenue("$1B+") == 1000000000
    assert ApolloModule._parse_revenue(None) is None
    assert ApolloModule._parse_revenue("unknown") is None
