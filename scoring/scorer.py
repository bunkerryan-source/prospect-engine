"""
Lead Scoring Engine — pure computation, no I/O.

Scores each ProspectRecord across four dimensions:
  1. Signal Density   — number of distinct source channels
  2. Compliance Pressure — Walmart/SQEP/OTIF compliance signals
  3. Geography        — state match against target states
  4. Enrichment Quality — contact data quality

A vertical multiplier is then applied (max across all verticals on the record).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Optional

from models import ProspectRecord

# ---------------------------------------------------------------------------
# Logistics title keywords (case-insensitive)
# ---------------------------------------------------------------------------

_LOGISTICS_KEYWORDS = [
    "logistics",
    "supply chain",
    "transportation",
    "shipping",
    "distribution",
    "freight",
    "warehouse",
    "procurement",
    "fulfillment",
    "operations",
    "coo",
    "plant manager",
    "general manager",
]


def _is_logistics_title(title: str) -> bool:
    title_lower = title.lower()
    return any(kw in title_lower for kw in _LOGISTICS_KEYWORDS)


# ---------------------------------------------------------------------------
# Dimension helpers
# ---------------------------------------------------------------------------

def _signal_density(prospect: ProspectRecord, weights: dict) -> int:
    """Score based on the number of distinct source channels."""
    if not prospect.source_channel:
        return 0
    sources = [s.strip() for s in prospect.source_channel.split(",") if s.strip()]
    count = len(set(sources))
    if count >= 4:
        return weights.get("4_plus_sources", 35)
    elif count == 3:
        return weights.get("3_sources", 25)
    elif count == 2:
        return weights.get("2_sources", 15)
    elif count == 1:
        return weights.get("1_source", 5)
    return 0


def _compliance_pressure(prospect: ProspectRecord, weights: dict) -> int:
    """Score based on compliance signals present."""
    if not prospect.compliance_signals:
        return 0
    signals = {s.strip().lower() for s in prospect.compliance_signals.split(",") if s.strip()}
    score = 0
    for key in ("walmart_supplier", "sqep_mentioned", "otif_mentioned", "compliance_pain"):
        if key in signals:
            score += weights.get(key, 10)
    return score


def _geography(prospect: ProspectRecord, target_states: list[str], weights: dict) -> int:
    """Score based on whether the prospect's state is in the target list."""
    if prospect.state and prospect.state in target_states:
        return weights.get("in_target_state", 15)
    return weights.get("other", 0)


def _enrichment_quality(prospect: ProspectRecord, weights: dict) -> int:
    """Score based on quality of contact information."""
    has_email = bool(prospect.contact_email and prospect.contact_email.strip())
    has_title = bool(prospect.contact_title and prospect.contact_title.strip())
    has_name = bool(prospect.contact_name and prospect.contact_name.strip())
    hunter_pattern = "Hunter email pattern" in (prospect.notes or "")

    if has_email and has_title and _is_logistics_title(prospect.contact_title):
        return weights.get("verified_email_logistics_title", 15)
    elif has_email:
        return weights.get("email_non_logistics_title", 10)
    elif hunter_pattern:
        return weights.get("email_pattern_found", 5)
    elif has_name and not has_email:
        return weights.get("contact_name_no_email", 3)
    return weights.get("website_only", 0)


def _get_multiplier(prospect: ProspectRecord, multipliers: dict) -> float:
    """Return the maximum vertical multiplier across all verticals on the record."""
    unknown_mult = multipliers.get("unknown", 0.8)
    if not prospect.vertical or not prospect.vertical.strip():
        return unknown_mult
    verticals = [v.strip().lower() for v in prospect.vertical.split(",") if v.strip()]
    if not verticals:
        return unknown_mult
    return max(multipliers.get(v, unknown_mult) for v in verticals)


def _get_tier(score: int, tiers: dict) -> str:
    """Map a numeric score to a tier label."""
    hot_threshold = tiers.get("hot", 70)
    warm_threshold = tiers.get("warm", 45)
    nurture_threshold = tiers.get("nurture", 25)

    if score >= hot_threshold:
        return "HOT"
    elif score >= warm_threshold:
        return "WARM"
    elif score >= nurture_threshold:
        return "NURTURE"
    return "PARK"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_prospect(
    prospect: ProspectRecord,
    config: dict,
    target_states: list[str],
) -> ProspectRecord:
    """
    Compute a score for a single ProspectRecord.

    Returns a new ProspectRecord (via dataclasses.replace) with score,
    score_breakdown, and tier populated.
    """
    scoring_cfg = config["scoring"]

    signal = _signal_density(prospect, scoring_cfg["signal_density"])
    compliance = _compliance_pressure(prospect, scoring_cfg["compliance"])
    geography = _geography(prospect, target_states, scoring_cfg["geography"])
    enrichment = _enrichment_quality(prospect, scoring_cfg["enrichment"])

    subtotal = signal + compliance + geography + enrichment
    multiplier = _get_multiplier(prospect, scoring_cfg["vertical_multipliers"])
    raw_score = subtotal * multiplier
    final_score = round(raw_score)

    tier = _get_tier(final_score, scoring_cfg["tiers"])

    # Determine the vertical label used for the breakdown string
    if prospect.vertical and prospect.vertical.strip():
        verticals = [v.strip().lower() for v in prospect.vertical.split(",") if v.strip()]
        best_vertical = max(verticals, key=lambda v: scoring_cfg["vertical_multipliers"].get(v, scoring_cfg["vertical_multipliers"].get("unknown", 0.8)))
    else:
        best_vertical = "unknown"

    breakdown = (
        f"Signal:{signal} + Compliance:{compliance} + Geo:{geography} + Enrich:{enrichment} "
        f"= {subtotal} x {multiplier}({best_vertical}) = {final_score} -> {tier}"
    )

    return dataclasses.replace(
        prospect,
        score=final_score,
        score_breakdown=breakdown,
        tier=tier,
    )


def score_prospects(
    prospects: list[ProspectRecord],
    config: dict,
    target_states: list[str],
) -> list[ProspectRecord]:
    """Score a list of ProspectRecords, returning a new list of scored records."""
    return [score_prospect(p, config, target_states) for p in prospects]
