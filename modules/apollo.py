"""
Task 10: Apollo company and contact search module.

Uses the Apollo.io API to search for companies by keyword and then
fetch contacts (people) for each matching company.
"""

import re
import time
import logging

import requests

from models import ProspectRecord, normalize_domain
from modules.base import BaseModule

logger = logging.getLogger(__name__)

# Title keyword groups for contact priority selection
_PRIORITY_1_TITLES = [
    "logistics", "supply chain", "transportation", "shipping",
    "distribution", "freight",
]
_PRIORITY_2_TITLES = [
    "operations", "coo", "vp operations", "general manager", "plant manager",
]

# Person titles to request from Apollo people search
_PEOPLE_SEARCH_TITLES = [
    "logistics", "supply chain", "transportation", "shipping",
    "distribution", "operations", "procurement", "warehouse",
    "plant manager", "COO", "General Manager",
]


class ApolloModule(BaseModule):
    """Searches Apollo.io for companies and contacts matching active verticals."""

    def __init__(self, config: dict, states: list[str], api_key: str):
        super().__init__(config, states)
        self.api_key = api_key
        self.company_search_credits = 0
        self.people_search_credits = 0

    @property
    def channel_name(self) -> str:
        return "apollo"

    def run(self, active_verticals: list[str] | None = None) -> list[ProspectRecord]:
        verticals = self.get_active_verticals(active_verticals)
        icp = self.config.get("icp", {})
        apollo_cfg = self.config.get("apollo", {})
        max_pages = apollo_cfg.get("max_pages_per_search", 1)

        employee_min = icp.get("employee_min", "")
        employee_max = icp.get("employee_max", "")
        revenue_min = icp.get("revenue_min")
        revenue_max = icp.get("revenue_max")

        employee_range = f"{employee_min},{employee_max}" if employee_min or employee_max else None

        records: list[ProspectRecord] = []

        for vertical_name, vertical_cfg in verticals.items():
            keywords: list[str] = vertical_cfg.get("keywords", [])[:3]

            for keyword in keywords:
                for page in range(1, max_pages + 1):
                    companies = self._search_companies(
                        keyword=keyword,
                        employee_range=employee_range,
                        page=page,
                    )
                    if companies is None:
                        break

                    for company in companies:
                        # ICP revenue filtering
                        revenue_str = company.get("annual_revenue_printed")
                        estimated_revenue = self._parse_revenue(revenue_str)

                        if estimated_revenue is not None:
                            if revenue_min is not None and estimated_revenue < revenue_min:
                                continue
                            if revenue_max is not None and estimated_revenue > revenue_max:
                                continue

                        # Extract company fields
                        company_id = company.get("id", "")
                        name = company.get("name", "") or ""
                        city = company.get("city", "") or ""
                        state = company.get("state", "") or ""
                        phone = company.get("phone", "") or ""
                        primary_domain = company.get("primary_domain", "") or ""
                        website = normalize_domain(primary_domain) if primary_domain else ""
                        emp_count = company.get("estimated_num_employees")
                        industry = company.get("industry", "") or ""
                        kw_list = company.get("keywords") or []
                        product_keywords = ", ".join(kw_list) if isinstance(kw_list, list) else str(kw_list)

                        # Fetch contacts
                        contact_name = ""
                        contact_title = ""
                        contact_email = ""
                        contact_source = ""

                        if company_id:
                            time.sleep(0.5)
                            people = self._search_people(company_id)
                            if people:
                                selected = self._select_contact(people)
                                if selected:
                                    first = selected.get("first_name", "") or ""
                                    last = selected.get("last_name", "") or ""
                                    contact_name = f"{first} {last}".strip()
                                    contact_title = selected.get("title", "") or ""
                                    contact_email = selected.get("email", "") or ""
                                    contact_source = "apollo"

                        record = ProspectRecord(
                            company_name=name or website,
                            city=city,
                            state=state,
                            phone=phone,
                            website=website,
                            vertical=vertical_name,
                            source_channel="apollo",
                            estimated_employees=emp_count,
                            estimated_revenue=estimated_revenue,
                            product_keywords=product_keywords,
                            contact_name=contact_name,
                            contact_title=contact_title,
                            contact_email=contact_email,
                            contact_source=contact_source,
                        )
                        records.append(record)

                    time.sleep(0.5)

        self.log(
            f"Credit usage — company searches: {self.company_search_credits}, "
            f"people searches: {self.people_search_credits}"
        )
        return records

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _search_companies(self, keyword: str, employee_range: str | None, page: int) -> list | None:
        """POST to Apollo mixed_companies/search. Returns list of org dicts or None on error."""
        payload: dict = {
            "api_key": self.api_key,
            "q_organization_keyword_tags": [keyword],
            "organization_locations": self.states,
            "per_page": 25,
            "page": page,
        }
        if employee_range:
            payload["organization_num_employees_ranges"] = [employee_range]

        try:
            response = requests.post(
                "https://api.apollo.io/api/v1/mixed_companies/search",
                json=payload,
            )
            response.raise_for_status()
            self.company_search_credits += 1
            data = response.json()
            return data.get("organizations", [])
        except Exception as exc:
            logger.error("Apollo company search failed for keyword '%s' page %d: %s", keyword, page, exc)
            return None

    def _search_people(self, company_apollo_id: str) -> list | None:
        """POST to Apollo mixed_people/search. Returns list of people dicts or None on error."""
        payload = {
            "api_key": self.api_key,
            "q_organization_id": company_apollo_id,
            "person_titles": _PEOPLE_SEARCH_TITLES,
            "per_page": 3,
            "page": 1,
        }
        try:
            response = requests.post(
                "https://api.apollo.io/api/v1/mixed_people/search",
                json=payload,
            )
            response.raise_for_status()
            self.people_search_credits += 1
            data = response.json()
            return data.get("people", [])
        except Exception as exc:
            logger.error("Apollo people search failed for company id '%s': %s", company_apollo_id, exc)
            return None

    @staticmethod
    def _parse_revenue(s: str | None) -> int | None:
        """Parse an Apollo revenue string like '$10M-$50M' into the lower-bound integer."""
        if not s:
            return None
        match = re.search(r'\$([0-9]+(?:\.[0-9]+)?)\s*([KMB])', s, re.IGNORECASE)
        if not match:
            return None
        amount = float(match.group(1))
        suffix = match.group(2).upper()
        multipliers = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}
        return int(amount * multipliers[suffix])

    @staticmethod
    def _select_contact(people: list) -> dict | None:
        """
        Select the best contact from a list of people dicts.

        Priority 1: title contains logistics/supply-chain keywords.
        Priority 2: title contains operations keywords.
        Priority 3: return None.
        """
        p1_keywords = _PRIORITY_1_TITLES
        p2_keywords = _PRIORITY_2_TITLES

        priority1: list[dict] = []
        priority2: list[dict] = []

        for person in people:
            title = (person.get("title") or "").lower()
            if any(kw in title for kw in p1_keywords):
                priority1.append(person)
            elif any(kw in title for kw in p2_keywords):
                priority2.append(person)

        if priority1:
            return priority1[0]
        if priority2:
            return priority2[0]
        return None
