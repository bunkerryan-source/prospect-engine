"""
ProspectRecord data model with normalization and deduplication logic.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Optional
from urllib.parse import urlparse

from thefuzz import fuzz


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

def normalize_domain(url: str) -> str:
    """Strip protocol, www, path, and lowercase a URL to a bare domain."""
    if not url:
        return ""
    u = url.strip()
    # Add scheme if missing so urlparse can handle it
    if not re.match(r'^https?://', u, re.IGNORECASE):
        u = "http://" + u
    parsed = urlparse(u)
    host = parsed.hostname or ""
    # Strip leading www.
    if host.startswith("www."):
        host = host[4:]
    return host.lower()


# Legal entity suffixes — always stripped (e.g. "Inc", "LLC", "Ltd", "Corp", "Co", "Company")
_LEGAL_SUFFIXES = ["inc", "llc", "ltd", "corp", "company", "co"]

# Organizational descriptor suffixes — stripped after legal suffixes
# (e.g. "International", "Holdings", "Enterprises")
# Note: "Corporation", "Group", "Company" are intentionally NOT stripped as
# they are considered meaningful parts of a proper company name.
_DESCRIPTOR_SUFFIXES = ["international", "holdings", "enterprises"]

_LEGAL_PATTERN = re.compile(
    r"[\s,]+(?:" + "|".join(_LEGAL_SUFFIXES) + r")\.?$",
    re.IGNORECASE,
)

_DESCRIPTOR_PATTERN = re.compile(
    r"[\s,]+(?:" + "|".join(_DESCRIPTOR_SUFFIXES) + r")\.?$",
    re.IGNORECASE,
)


def normalize_company_name(name: str) -> str:
    """Lowercase, strip common corporate suffixes, collapse whitespace.

    Two-phase stripping:
    1. Iteratively strip legal entity markers (Inc, LLC, Ltd, Corp, Co).
    2. Iteratively strip organizational descriptors (International, Holdings, Enterprises).
    """
    n = name.lower().strip()
    n = re.sub(r"\s+", " ", n)

    # Phase 1: strip legal suffixes
    prev = None
    while prev != n:
        prev = n
        n = _LEGAL_PATTERN.sub("", n).strip().rstrip(",").strip()

    # Phase 2: strip descriptor suffixes
    prev = None
    while prev != n:
        prev = n
        n = _DESCRIPTOR_PATTERN.sub("", n).strip().rstrip(",").strip()

    return re.sub(r"\s+", " ", n).strip()


# ---------------------------------------------------------------------------
# ProspectRecord dataclass
# ---------------------------------------------------------------------------

@dataclass
class ProspectRecord:
    # Required
    company_name: str

    # Address
    address: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""
    phone: str = ""
    website: str = ""

    # Classification
    vertical: str = ""
    source_channel: str = ""

    # Financials / size
    estimated_employees: Optional[int] = None
    estimated_revenue: Optional[int] = None

    # Product / compliance
    product_keywords: str = ""
    compliance_signals: str = ""

    # Contact
    contact_name: str = ""
    contact_title: str = ""
    contact_email: str = ""
    contact_source: str = ""
    email_verified: str = ""
    email_confidence: Optional[int] = None

    # Import data
    registration_id: str = ""
    import_products: str = ""

    # Misc
    notes: str = ""
    score: int = 0
    score_breakdown: str = ""
    tier: str = ""
    scraped_date: str = field(default_factory=lambda: date.today().isoformat())

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


# ---------------------------------------------------------------------------
# Merge helpers
# ---------------------------------------------------------------------------

# Multi-value fields that should be set-unioned on merge
_MULTI_VALUE_FIELDS = ("source_channel", "vertical", "product_keywords", "compliance_signals")

# Contact fields controlled by source priority
_CONTACT_FIELDS = ("contact_name", "contact_title", "contact_email",
                   "contact_source", "email_verified", "email_confidence")

_CONTACT_PRIORITY = {"apollo": 2, "hunter": 1}


def _merge_set_field(a: str, b: str) -> str:
    """Merge two comma-separated value strings into a sorted, deduplicated string."""
    parts_a = {v.strip() for v in a.split(",") if v.strip()}
    parts_b = {v.strip() for v in b.split(",") if v.strip()}
    merged = parts_a | parts_b
    return ", ".join(sorted(merged))


def merge_records(existing: ProspectRecord, new: ProspectRecord) -> ProspectRecord:
    """Merge *new* into *existing*, returning a new ProspectRecord."""
    merged = dataclasses.replace(existing)

    # Set-union multi-value fields
    for f in _MULTI_VALUE_FIELDS:
        setattr(merged, f, _merge_set_field(getattr(existing, f), getattr(new, f)))

    # Fill blank single-value fields from new
    single_value_fields = [
        f.name for f in dataclasses.fields(existing)
        if f.name not in _MULTI_VALUE_FIELDS
        and f.name not in _CONTACT_FIELDS
        and f.name != "company_name"
        and f.name != "scraped_date"
    ]
    for fname in single_value_fields:
        current = getattr(merged, fname)
        incoming = getattr(new, fname)
        # Treat empty string and None as "blank"
        is_blank = current == "" or current is None or current == 0
        if is_blank and incoming not in ("", None, 0):
            setattr(merged, fname, incoming)

    # Contact priority: apollo > hunter > anything else
    existing_priority = _CONTACT_PRIORITY.get(existing.contact_source, 0)
    new_priority = _CONTACT_PRIORITY.get(new.contact_source, 0)

    if new_priority > existing_priority:
        for cf in _CONTACT_FIELDS:
            setattr(merged, cf, getattr(new, cf))
    elif new_priority == existing_priority and existing_priority == 0:
        # Neither is a known source — fill blanks from new
        for cf in _CONTACT_FIELDS:
            current = getattr(merged, cf)
            incoming = getattr(new, cf)
            if (current == "" or current is None) and incoming not in ("", None):
                setattr(merged, cf, incoming)

    return merged


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

_FUZZY_THRESHOLD = 85


def deduplicate(records: list[ProspectRecord]) -> list[ProspectRecord]:
    """
    Deduplicate a list of ProspectRecords.

    Matching strategy (in order):
    1. Exact normalized domain match (when both records have a non-empty website).
    2. Fuzzy company name match using token_sort_ratio >= 85.

    Matched records are merged; unmatched records are appended.
    """
    result: list[ProspectRecord] = []
    # domain -> index in result
    domain_index: dict[str, int] = {}
    # normalized name -> index in result
    name_index: dict[str, int] = {}

    for record in records:
        norm_domain = normalize_domain(record.website) if record.website else ""
        norm_name = normalize_company_name(record.company_name)

        matched_idx: Optional[int] = None

        # 1. Domain match
        if norm_domain and norm_domain in domain_index:
            matched_idx = domain_index[norm_domain]

        # 2. Fuzzy name match (only if no domain match yet)
        if matched_idx is None:
            for existing_name, idx in name_index.items():
                score = fuzz.token_sort_ratio(norm_name, existing_name)
                if score >= _FUZZY_THRESHOLD:
                    matched_idx = idx
                    break

        if matched_idx is not None:
            # Merge into existing
            result[matched_idx] = merge_records(result[matched_idx], record)
            # Update domain index if new record adds a domain
            if norm_domain and norm_domain not in domain_index:
                domain_index[norm_domain] = matched_idx
        else:
            # New unique record
            idx = len(result)
            result.append(record)
            if norm_domain:
                domain_index[norm_domain] = idx
            name_index[norm_name] = idx

    return result
