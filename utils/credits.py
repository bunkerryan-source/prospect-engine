"""
Credit estimation and usage reporting for external API services.

Provides pre-run estimates (SerpAPI, Apollo, Hunter) and post-run summaries.
"""

from __future__ import annotations

from typing import Optional


# ---------------------------------------------------------------------------
# Estimation
# ---------------------------------------------------------------------------

def estimate_credits(
    config: dict,
    active_verticals: list[str],
    active_states: list[str],
    active_channels: list[str],
) -> dict[str, dict]:
    """
    Estimate API credit usage before a run.

    Returns a dict keyed by provider with ``estimated`` and ``limit`` values::

        {
            "serpapi": {"estimated": N, "limit": M},
            "apollo":  {"estimated": N, "limit": M},
            "hunter":  {"estimated": N, "limit": M},
        }
    """
    verticals_cfg: dict = config.get("verticals", {})
    serpapi_limit: int = config.get("search_api", {}).get("plan_limit", 0)
    apollo_cfg: dict = config.get("apollo", {})
    hunter_cfg: dict = config.get("hunter", {})

    # ---- SerpAPI estimates ------------------------------------------------
    serpapi_estimated = 0

    if "web_search" in active_channels:
        # One search per (vertical × state × ~3 keyword groups) +
        # one search per sqep_product_signal per active vertical
        web_search_credits = len(active_verticals) * len(active_states) * 3
        sqep_signals_credits = sum(
            len(verticals_cfg.get(v, {}).get("sqep_product_signals", []))
            for v in active_verticals
        )
        serpapi_estimated += web_search_credits + sqep_signals_credits

    if "sqep" in active_channels:
        sqep_search_terms: list = config.get("sqep_search_terms", [])
        sqep_credits = len(sqep_search_terms)
        sqep_signals_by_state = sum(
            len(verticals_cfg.get(v, {}).get("sqep_product_signals", []))
            for v in active_verticals
        ) * len(active_states)
        serpapi_estimated += sqep_credits + sqep_signals_by_state

    if "import_search" in active_channels:
        import_keywords: dict = config.get("import_keywords", {})
        import_credits = sum(
            len(import_keywords.get(v, [])) for v in active_verticals
        ) * 2
        serpapi_estimated += import_credits

    # ---- Apollo estimates -------------------------------------------------
    apollo_estimated = 0
    apollo_limit: int = apollo_cfg.get("plan_limit", 0)

    if "apollo" in active_channels:
        max_pages: int = apollo_cfg.get("max_pages_per_search", 0)
        # Base: verticals × 3 search types × max_pages
        apollo_estimated = len(active_verticals) * 3 * max_pages
        # Upper-bound people records (per_page per page)
        per_page: int = apollo_cfg.get("per_page", 25)
        apollo_estimated += len(active_verticals) * 3 * max_pages * per_page

    # ---- Hunter estimates -------------------------------------------------
    hunter_limit: int = hunter_cfg.get("search_credit_limit", 0)
    hunter_estimated: int = hunter_cfg.get("max_searches_per_run", 0)

    return {
        "serpapi": {"estimated": serpapi_estimated, "limit": serpapi_limit},
        "apollo": {"estimated": apollo_estimated, "limit": apollo_limit},
        "hunter": {"estimated": hunter_estimated, "limit": hunter_limit},
    }


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def format_credit_warning(estimates: dict[str, dict]) -> str:
    """
    Return a human-readable warning string for providers whose estimated
    usage exceeds their plan limit.
    """
    lines: list[str] = []
    any_over = False

    for provider, data in estimates.items():
        estimated: int = data.get("estimated", 0)
        limit: int = data.get("limit", 0)
        over = limit > 0 and estimated > limit
        if over:
            any_over = True
        flag = " [WARNING: over limit]" if over else ""
        lines.append(f"  {provider}: {estimated}/{limit}{flag}")

    header = "WARNING: Credit estimate exceeds plan limits!" if any_over else "Credit estimates:"
    return header + "\n" + "\n".join(lines)


def format_credit_summary(actuals: dict[str, int], limits: dict[str, int]) -> str:
    """
    Return a one-line summary of credits actually used.

    Example output::

        Credits used — SerpAPI: 115/1000, Apollo: 283/30000,
        Hunter searches: 75/1000, Hunter verifications: 0/1000
    """
    serpapi = actuals.get("serpapi", 0)
    serpapi_limit = limits.get("serpapi", 0)

    apollo = actuals.get("apollo", 0)
    apollo_limit = limits.get("apollo", 0)

    hunter_search = actuals.get("hunter_search", 0)
    hunter_search_limit = limits.get("hunter_search", 0)

    hunter_verify = actuals.get("hunter_verify", 0)
    hunter_verify_limit = limits.get("hunter_verify", 0)

    return (
        f"Credits used — "
        f"SerpAPI: {serpapi}/{serpapi_limit}, "
        f"Apollo: {apollo}/{apollo_limit}, "
        f"Hunter searches: {hunter_search}/{hunter_search_limit}, "
        f"Hunter verifications: {hunter_verify}/{hunter_verify_limit}"
    )
