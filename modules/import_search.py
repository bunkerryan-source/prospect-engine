"""
Import/export data search module.

Searches ImportYeti and general web for importers/manufacturers using
per-vertical import keywords. Uses centralized domain filtering.

TRIMMED: Only 1 keyword per vertical, and general importer search runs
WITHOUT per-state iteration (just 1 general search per keyword).
ImportYeti site: search stays as-is.
"""

import re
from models import ProspectRecord, normalize_domain
from modules.base import BaseModule
from utils.domain_filter import is_blocked_domain, is_importyeti, extract_company_from_title

_IMPORTYETI_SUFFIX = re.compile(r"\s*-\s*ImportYeti\s*$", re.IGNORECASE)


def _extract_importyeti_name(title: str) -> str:
    """Extract company name from an ImportYeti result title."""
    name = _IMPORTYETI_SUFFIX.sub("", title).strip()
    return name if name else ""


class ImportSearchModule(BaseModule):

    def __init__(self, config: dict, states: list[str], search_client):
        super().__init__(config, states)
        self.search_client = search_client

    @property
    def channel_name(self) -> str:
        return "import"

    def run(self, active_verticals: list[str] | None = None) -> list[ProspectRecord]:
        verticals = self.get_active_verticals(active_verticals)
        records: list[ProspectRecord] = []
        seen_domains: set[str] = set()

        import_keywords_cfg: dict = self.config.get("import_keywords", {})

        for vertical_name in verticals:
            keywords: list[str] = import_keywords_cfg.get(vertical_name, [])

            for keyword in keywords:
                # Strategy 1: ImportYeti site search (1 query per keyword)
                query = f'site:importyeti.com "{keyword}"'
                self.log(f"Searching (ImportYeti): {query}")
                results = self.search_client.search(query)
                for item in results:
                    record = self._make_importyeti_record(item, keyword)
                    if record:
                        key = record.website or record.company_name.lower()
                        if key not in seen_domains:
                            seen_domains.add(key)
                            records.append(record)

                # Strategy 2: ONE general importer search (no per-state loop)
                query = f'"{keyword}" manufacturer importer USA'
                self.log(f"Searching: {query}")
                results = self.search_client.search(query)
                for item in results:
                    record = self._make_general_record(item, keyword)
                    if record:
                        key = record.website
                        if key not in seen_domains:
                            seen_domains.add(key)
                            records.append(record)

        return records

    def _make_importyeti_record(self, item: dict, keyword: str) -> ProspectRecord | None:
        """Parse an ImportYeti search result. Extract company name from title."""
        title = item.get("title", "")
        snippet = item.get("snippet", "")

        company_name = _extract_importyeti_name(title)
        if not company_name:
            return None

        # ImportYeti pages don't give us the company's real domain,
        # so we leave website blank — dedup will use fuzzy name matching,
        # and Apollo/Hunter can fill in the domain later.
        return ProspectRecord(
            company_name=company_name,
            source_channel="import",
            import_products=keyword,
            notes=snippet,
        )

    def _make_general_record(self, item: dict, keyword: str) -> ProspectRecord | None:
        """Parse a general web search result for importers."""
        url = item.get("link", "")
        title = item.get("title", "")
        snippet = item.get("snippet", "")

        domain = normalize_domain(url)
        if not domain or is_blocked_domain(domain):
            return None

        company_name = extract_company_from_title(title, domain)

        return ProspectRecord(
            company_name=company_name,
            website=domain,
            source_channel="import",
            import_products=keyword,
            notes=snippet,
        )
