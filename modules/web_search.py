"""
Task 7: Web Search scraper module.

Searches for prospects using per-state keyword queries and global SQEP product
signal queries. Produces ProspectRecords filtered against known noise domains.
"""

import re
from models import ProspectRecord, normalize_domain
from modules.base import BaseModule

_FILTERED_DOMAINS = {
    "google.com",
    "youtube.com",
    "wikipedia.org",
    "linkedin.com",
    "facebook.com",
    "yelp.com",
    "indeed.com",
    "glassdoor.com",
    "amazon.com",
    "pinterest.com",
    "twitter.com",
    "instagram.com",
}

# Separators used to split page titles into segments
_TITLE_SEPARATORS = re.compile(r"\s*[|\-\u2014]\s*")


def _extract_company_name(title: str) -> str:
    """Return the first meaningful segment of a page title."""
    parts = _TITLE_SEPARATORS.split(title)
    return parts[0].strip() if parts else title.strip()


class WebSearchModule(BaseModule):

    def __init__(self, config: dict, states: list[str], search_client):
        super().__init__(config, states)
        self.search_client = search_client

    @property
    def channel_name(self) -> str:
        return "web_search"

    def run(self, active_verticals: list[str] | None = None) -> list[ProspectRecord]:
        verticals = self.get_active_verticals(active_verticals)
        records: list[ProspectRecord] = []
        seen_domains: set[str] = set()

        for vertical_name, vertical_cfg in verticals.items():
            keywords: list[str] = vertical_cfg.get("keywords", [])
            signals: list[str] = vertical_cfg.get("sqep_product_signals", [])

            # Strategy 1: top-3 keywords × states
            for keyword in keywords[:3]:
                for state in self.states:
                    query = f"{keyword} {state}"
                    self.log(f"Searching: {query}")
                    results = self.search_client.search(query)
                    for item in results:
                        record = self._make_record(item, vertical_name)
                        if record:
                            key = record.website
                            if key not in seen_domains:
                                seen_domains.add(key)
                                records.append(record)

            # Strategy 2: SQEP product signals globally
            for signal in signals:
                query = f'Walmart supplier "{signal}" manufacturer'
                self.log(f"Searching: {query}")
                results = self.search_client.search(query)
                for item in results:
                    record = self._make_record(item, vertical_name)
                    if record:
                        key = record.website
                        if key not in seen_domains:
                            seen_domains.add(key)
                            records.append(record)

        return records

    def _make_record(self, item: dict, vertical_name: str) -> ProspectRecord | None:
        """Parse a search result dict into a ProspectRecord, or None if filtered."""
        url = item.get("link", "")
        title = item.get("title", "")
        snippet = item.get("snippet", "")

        domain = normalize_domain(url)
        if not domain or domain in _FILTERED_DOMAINS:
            return None

        company_name = _extract_company_name(title) or domain

        return ProspectRecord(
            company_name=company_name,
            website=domain,
            vertical=vertical_name,
            source_channel="web_search",
            notes=snippet,
        )
