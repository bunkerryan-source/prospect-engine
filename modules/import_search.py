"""
Task 9: Import/export data search module.

Searches ImportYeti and general web for importers/manufacturers using
per-vertical import keywords. Produces ProspectRecords with import_products set.
"""

import re
from models import ProspectRecord, normalize_domain
from modules.base import BaseModule

_TITLE_SEPARATORS = re.compile(r"\s*[|\-\u2014]\s*")

_IMPORTYETI_SUFFIX = re.compile(r"\s*-\s*ImportYeti\s*$", re.IGNORECASE)


def _extract_company_name(title: str, is_importyeti: bool = False) -> str:
    """Extract company name from title, stripping ImportYeti suffix when applicable."""
    if is_importyeti:
        name = _IMPORTYETI_SUFFIX.sub("", title).strip()
        return name if name else title.strip()
    parts = _TITLE_SEPARATORS.split(title)
    return parts[0].strip() if parts else title.strip()


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
                # Strategy 1: ImportYeti site search
                query = f'site:importyeti.com "{keyword}"'
                self.log(f"Searching (ImportYeti): {query}")
                results = self.search_client.search(query)
                for item in results:
                    record = self._make_record(item, keyword)
                    if record:
                        key = record.website
                        if key not in seen_domains:
                            seen_domains.add(key)
                            records.append(record)

                # Strategy 2: general importer search per state
                for state in self.states:
                    query = f'"{keyword}" importer {state} manufacturer'
                    self.log(f"Searching: {query}")
                    results = self.search_client.search(query)
                    for item in results:
                        record = self._make_record(item, keyword)
                        if record:
                            key = record.website
                            if key not in seen_domains:
                                seen_domains.add(key)
                                records.append(record)

        return records

    def _make_record(self, item: dict, keyword: str) -> ProspectRecord | None:
        """Parse a search result into a ProspectRecord."""
        url = item.get("link", "")
        title = item.get("title", "")
        snippet = item.get("snippet", "")

        domain = normalize_domain(url)
        if not domain:
            return None

        is_importyeti = "importyeti.com" in domain
        company_name = _extract_company_name(title, is_importyeti=is_importyeti) or domain

        return ProspectRecord(
            company_name=company_name,
            website=domain,
            source_channel="import",
            import_products=keyword,
            notes=snippet,
        )
