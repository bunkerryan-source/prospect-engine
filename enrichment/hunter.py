"""
Hunter.io email enrichment and verification for ProspectRecord objects.
"""

from __future__ import annotations

import dataclasses
import logging
import time
from typing import Optional

import requests

from models import ProspectRecord

logger = logging.getLogger(__name__)

# Keywords used to identify relevant contacts
_TARGET_KEYWORDS = [
    "logistics",
    "supply chain",
    "transportation",
    "shipping",
    "distribution",
    "operations",
    "procurement",
    "warehouse",
    "plant manager",
    "fulfillment",
    "coo",
]

_HUNTER_BASE = "https://api.hunter.io/v2"


class HunterEnrichment:
    def __init__(self, config: dict, api_key: str) -> None:
        self.config = config
        self.api_key = api_key
        self.search_credits_used: int = 0
        self.verify_credits_used: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def enrich(self, prospects: list[ProspectRecord]) -> list[ProspectRecord]:
        """Enrich prospects using Hunter.io domain search.

        Only processes prospects that:
        - have a non-empty website
        - have no contact_email
        - were NOT sourced from apollo
        """
        hunter_cfg = self.config.get("hunter", {})
        max_searches = hunter_cfg.get("max_searches_per_run", 100)

        # Split into candidates and untouched
        candidates = []
        untouched = []
        for p in prospects:
            if p.website and not p.contact_email and p.contact_source != "apollo":
                candidates.append(p)
            else:
                untouched.append(p)

        enriched: list[ProspectRecord] = []
        searches_done = 0

        for prospect in candidates:
            if searches_done >= max_searches:
                # Quota exhausted — pass through unchanged
                enriched.append(prospect)
                continue

            domain = _extract_domain(prospect.website)
            updated = self._domain_search(prospect, domain)
            enriched.append(updated)
            searches_done += 1

            if searches_done < len(candidates) and searches_done < max_searches:
                time.sleep(2)

        total_enriched = sum(1 for p in enriched if p.contact_source == "hunter")
        logger.info(
            "Hunter enrichment complete: %d searched, %d contacts found",
            searches_done,
            total_enriched,
        )

        # Return full list: enriched candidates + untouched
        return enriched + untouched

    def verify_email(self, email: str) -> str:
        """Verify a single email address. Returns status string."""
        url = f"{_HUNTER_BASE}/email-verifier"
        params = {"email": email, "api_key": self.api_key}
        try:
            resp = _get_with_retry(url, params)
            resp.raise_for_status()
            self.verify_credits_used += 1
            return resp.json()["data"]["status"]
        except requests.HTTPError as exc:
            logger.error("Hunter verify HTTP error for %s: %s", email, exc)
            return "unknown"
        except Exception as exc:  # noqa: BLE001
            logger.error("Hunter verify error for %s: %s", email, exc)
            return "unknown"

    def verify_batch(
        self,
        emails_with_ids: list[tuple],
        limit: int,
    ) -> dict[int, str]:
        """Verify up to *limit* emails. Returns {prospect_id: status}."""
        results: dict[int, str] = {}
        for prospect_id, email in emails_with_ids[:limit]:
            status = self.verify_email(email)
            results[prospect_id] = status
            time.sleep(2)
        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _domain_search(self, prospect: ProspectRecord, domain: str) -> ProspectRecord:
        """Call Hunter domain-search API and apply contact selection."""
        url = f"{_HUNTER_BASE}/domain-search"
        params = {
            "domain": domain,
            "api_key": self.api_key,
            "type": "personal",
        }
        try:
            resp = _get_with_retry(url, params)
            resp.raise_for_status()
            self.search_credits_used += 1
            data = resp.json().get("data", {})
            return self._select_contact(prospect, data, domain)
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            if status_code in (401, 403):
                logger.error(
                    "Hunter auth error (%s) — aborting enrichment for %s",
                    status_code,
                    prospect.company_name,
                )
                raise  # re-raise to abort in enrich()
            logger.warning(
                "Hunter HTTP %s for %s — skipping",
                status_code,
                prospect.company_name,
            )
            return prospect
        except requests.Timeout:
            logger.warning("Hunter timeout for %s — skipping", prospect.company_name)
            return prospect
        except Exception as exc:  # noqa: BLE001
            logger.warning("Hunter error for %s: %s — skipping", prospect.company_name, exc)
            return prospect

    def _select_contact(
        self,
        prospect: ProspectRecord,
        data: dict,
        domain: str,
    ) -> ProspectRecord:
        """Apply contact selection logic and return updated (or unchanged) record."""
        emails: list[dict] = data.get("emails", [])
        pattern: Optional[str] = data.get("pattern")

        # Filter to relevant contacts
        matches = [e for e in emails if _is_target_contact(e)]

        if matches:
            best = max(matches, key=lambda e: e.get("confidence", 0))
            first = best.get("first_name", "")
            last = best.get("last_name", "")
            return dataclasses.replace(
                prospect,
                contact_name=f"{first} {last}".strip(),
                contact_title=best.get("position", ""),
                contact_email=best.get("value", ""),
                email_confidence=best.get("confidence"),
                contact_source="hunter",
            )

        if not emails and pattern:
            # No emails at all but pattern exists
            readable_pattern = pattern.replace("{first}", "{first}").replace("{last}", "{last}")
            note = f"Hunter email pattern: {readable_pattern}@{domain}"
            existing_notes = prospect.notes or ""
            combined = f"{existing_notes}\n{note}".strip() if existing_notes else note
            return dataclasses.replace(prospect, notes=combined)

        # Nothing useful
        logger.debug(
            "Hunter found no useful contact for %s (domain=%s)",
            prospect.company_name,
            domain,
        )
        return prospect


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

def _is_target_contact(email_entry: dict) -> bool:
    """Return True if position or department matches target keywords."""
    position = (email_entry.get("position") or "").lower()
    department = (email_entry.get("department") or "").lower()
    for kw in _TARGET_KEYWORDS:
        if kw in position or kw in department:
            return True
    return False


def _extract_domain(website: str) -> str:
    """Return bare domain from a website string (strip www/protocol)."""
    from urllib.parse import urlparse

    w = website.strip()
    if not w.startswith(("http://", "https://")):
        w = "http://" + w
    parsed = urlparse(w)
    host = parsed.hostname or w
    if host.startswith("www."):
        host = host[4:]
    return host.lower()


def _get_with_retry(url: str, params: dict) -> requests.Response:
    """GET with one retry on HTTP 429 (rate limit)."""
    resp = requests.get(url, params=params, timeout=30)
    if resp.status_code == 429:
        logger.warning("Hunter rate limit hit — waiting 60s before retry")
        time.sleep(60)
        resp = requests.get(url, params=params, timeout=30)
    return resp
