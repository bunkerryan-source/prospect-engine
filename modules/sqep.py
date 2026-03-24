"""
Task 8: SQEP compliance signal scraper module.

Searches for Walmart suppliers exhibiting SQEP/OTIF/compliance pain signals.
Filters out known consultant/service-provider domains.
"""

import re
from models import ProspectRecord, normalize_domain
from modules.base import BaseModule

# Consultant domains to exclude (substring match against the bare domain)
_CONSULTANT_SUBSTRINGS = {
    "8thandwalton",
    "carbon6",
    "vendormint",
    "newnexusgroup",
    "ozarkconsulting",
    "coldstreamlogistics",
    "rjwgroup",
    "5gsales",
    "supplypike",
}

# Title separators (mirrors web_search helper)
_TITLE_SEPARATORS = re.compile(r"\s*[|\-\u2014]\s*")


def _extract_company_name(title: str) -> str:
    parts = _TITLE_SEPARATORS.split(title)
    return parts[0].strip() if parts else title.strip()


def _detect_signals(title: str, snippet: str) -> list[str]:
    """Return a list of signal keys found in the combined title+snippet text."""
    text = (title + " " + snippet).lower()
    signals: list[str] = []

    if "sqep" in text:
        signals.append("sqep_mentioned")

    if "otif" in text:
        signals.append("otif_mentioned")

    if "walmart" in text and ("supplier" in text or "vendor" in text):
        signals.append("walmart_supplier")

    if any(word in text for word in ("chargeback", "fine", "penalty", "deduction")):
        signals.append("compliance_pain")

    return signals


def _is_consultant(domain: str) -> bool:
    return any(sub in domain for sub in _CONSULTANT_SUBSTRINGS)


class SQEPModule(BaseModule):

    def __init__(self, config: dict, states: list[str], search_client):
        super().__init__(config, states)
        self.search_client = search_client

    @property
    def channel_name(self) -> str:
        return "sqep"

    def run(self, active_verticals: list[str] | None = None) -> list[ProspectRecord]:
        verticals = self.get_active_verticals(active_verticals)
        records: list[ProspectRecord] = []
        seen_domains: set[str] = set()

        sqep_terms: list[str] = self.config.get("sqep_search_terms", [])

        # Strategy 1: global SQEP search terms
        for term in sqep_terms:
            self.log(f"Searching (global): {term}")
            results = self.search_client.search(term)
            for item in results:
                record = self._make_record(item)
                if record:
                    key = record.website
                    if key not in seen_domains:
                        seen_domains.add(key)
                        records.append(record)

        # Strategy 2: per-vertical × per-signal × per-state
        for vertical_name, vertical_cfg in verticals.items():
            signals: list[str] = vertical_cfg.get("sqep_product_signals", [])
            for signal in signals:
                for state in self.states:
                    query = f'Walmart supplier "{signal}" {state}'
                    self.log(f"Searching: {query}")
                    results = self.search_client.search(query)
                    for item in results:
                        record = self._make_record(item)
                        if record:
                            key = record.website
                            if key not in seen_domains:
                                seen_domains.add(key)
                                records.append(record)

        return records

    def _make_record(self, item: dict) -> ProspectRecord | None:
        """Parse a search result into a ProspectRecord, or None if filtered/no signals."""
        url = item.get("link", "")
        title = item.get("title", "")
        snippet = item.get("snippet", "")

        domain = normalize_domain(url)
        if not domain:
            return None

        if _is_consultant(domain):
            return None

        detected = _detect_signals(title, snippet)
        if not detected:
            return None

        company_name = _extract_company_name(title) or domain

        return ProspectRecord(
            company_name=company_name,
            website=domain,
            source_channel="sqep",
            compliance_signals=", ".join(detected),
            notes=snippet,
        )
