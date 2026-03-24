import time
import logging
import requests

logger = logging.getLogger(__name__)


class SearchClient:
    """Shared search abstraction supporting SerpAPI and Serper providers."""

    def __init__(self, config: dict, api_key: str):
        self.provider = config["search_api"]["provider"]
        self.api_key = api_key
        self.call_count = 0

    def search(self, query: str) -> list[dict]:
        """Dispatch search to the configured provider and return normalized results."""
        try:
            if self.provider == "serpapi":
                results = self._serpapi_search(query)
            elif self.provider == "serper":
                results = self._serper_search(query)
            else:
                logger.error("Unknown search provider: %s", self.provider)
                results = []
        except Exception as exc:
            logger.error("Search failed for query %r: %s", query, exc)
            results = []
        finally:
            self.call_count += 1
            time.sleep(0.5)

        return results

    def _serpapi_search(self, query: str) -> list[dict]:
        response = requests.get(
            "https://serpapi.com/search",
            params={
                "q": query,
                "api_key": self.api_key,
                "engine": "google",
                "num": 10,
            },
        )
        response.raise_for_status()
        raw = response.json().get("organic_results", [])
        return [
            {
                "title": item.get("title", ""),
                "link": item.get("link", ""),
                "snippet": item.get("snippet", ""),
            }
            for item in raw
        ]

    def _serper_search(self, query: str) -> list[dict]:
        response = requests.post(
            "https://google.serper.dev/search",
            json={"q": query},
            headers={"X-API-KEY": self.api_key},
        )
        response.raise_for_status()
        raw = response.json().get("organic", [])
        return [
            {
                "title": item.get("title", ""),
                "link": item.get("link", ""),
                "snippet": item.get("snippet", ""),
            }
            for item in raw
        ]
