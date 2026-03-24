"""
SQEP compliance signal scraper module.

Searches a small set of SQEP-specific queries to find companies mentioned
alongside Walmart compliance pain signals. Uses centralized domain filtering.

NOTE: This module now runs a SMALL number of targeted searches (just the
sqep_search_terms from config, NOT per-vertical × per-state). The bulk of
SQEP signal detection happens inline in web_search.py as post-processing.
"""

from models import ProspectRecord, normalize_domain
from modules.base import BaseModule
from utils.domain_filter import is_blocked_domain, extract_company_from_title


def _detect_signals(title: str, snippet: str) -> list[str]:
    """Return compliance signal keys found in combined title + snippet text."""
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


class SQEPModule(BaseModule):

    def __init__(self, config: dict, states: list[str], search_client):
        super().__init__(config, states)
        self.search_client = search_client

    @property
    def channel_name(self) -> str:
        return "sqep"

    def run(self, active_verticals: list[str] | None = None) -> list[ProspectRecord]:
        records: list[ProspectRecord] = []
        seen_domains: set[str] = set()

        sqep_terms: list[str] = self.config.get("sqep_search_terms", [])

        # ONLY run the global SQEP search terms (2 queries, not 85+)
        # Per-vertical × per-state SQEP searches have been REMOVED —
        # those signals are now detected inline by web_search.py
        for term in sqep_terms:
            self.log(f"Searching: {term}")
            results = self.search_client.search(term)
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
        if not domain or is_blocked_domain(domain):
            return None

        detected = _detect_signals(title, snippet)
        if not detected:
            return None

        company_name = extract_company_from_title(title, domain)

        return ProspectRecord(
            company_name=company_name,
            website=domain,
            source_channel="sqep",
            compliance_signals=", ".join(detected),
            notes=snippet,
        )
