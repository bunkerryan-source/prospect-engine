import pytest
from unittest.mock import patch, MagicMock
from utils.search import SearchClient

def test_serpapi_search():
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

def test_serper_search():
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
