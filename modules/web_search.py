"""
Web Search scraper module — with inline SQEP signal detection.

Searches for prospects using per-state keyword queries. SQEP/compliance
signal detection is applied to ALL results as a post-processing step
(no longer a separate module with its own searches).

Company names are extracted via heuristic title parsing with domain-based
fallback. Noise domains are filtered using centralized suffix matching.
"""

import re
from models import ProspectRecord, normalize_domain
from modules.base import BaseModule
from utils.domain_filter import is_blocked_domain, extract_company_from_title


# ---------------------------------------------------------------------------
# SQEP signal detection (merged from former sqep.py)
# ---------------------------------------------------------------------------

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

            # Strategy: keywords × states (keywords already trimmed to 2 in config)
            for keyword in keywords:
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

        return records

    def _make_record(self, item: dict, vertical_name: str) -> ProspectRecord | None:
        """Parse a search result dict into a ProspectRecord, or None if filtered."""
        url = item.get("link", "")
        title = item.get("title", "")
        snippet = item.get("snippet", "")

        domain = normalize_domain(url)

        # Reject noise domains using centralized suffix matcher
        if not domain or is_blocked_domain(domain):
            return None

        # Extract company name with smart fallback
        company_name = extract_company_from_title(title, domain)

        # Detect SQEP/compliance signals inline
        signals = _detect_signals(title, snippet)

        return ProspectRecord(
            company_name=company_name,
            website=domain,
            vertical=vertical_name,
            source_channel="web_search",
            compliance_signals=", ".join(signals) if signals else "",
            notes=snippet,
        )
