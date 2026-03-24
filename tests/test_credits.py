import pytest
from utils.credits import estimate_credits, format_credit_warning, format_credit_summary

def test_estimate_basic():
    config = {
        "verticals": {"food": {"keywords": ["a", "b", "c"], "sqep_product_signals": ["snack", "food"]}},
        "sqep_search_terms": ["term1", "term2"],
        "import_keywords": {"food": ["a", "b"]},
        "search_api": {"plan_limit": 1000},
        "apollo": {"per_page": 25, "max_pages_per_search": 4, "plan_limit": 30000},
        "hunter": {"max_searches_per_run": 100, "search_credit_limit": 1000}
    }
    estimates = estimate_credits(config,
                                 active_verticals=["food"],
                                 active_states=["TX", "LA"],
                                 active_channels=["web_search", "sqep", "import_search", "apollo"])
    assert estimates["serpapi"]["estimated"] > 0
    assert estimates["apollo"]["estimated"] > 0
    assert estimates["hunter"]["estimated"] > 0

def test_estimate_skipped_channels():
    config = {
        "verticals": {"food": {"keywords": ["a", "b", "c"], "sqep_product_signals": ["snack"]}},
        "sqep_search_terms": ["term1"],
        "import_keywords": {"food": ["a"]},
        "search_api": {"plan_limit": 1000},
        "apollo": {"per_page": 25, "max_pages_per_search": 4, "plan_limit": 30000},
        "hunter": {"max_searches_per_run": 100, "search_credit_limit": 1000}
    }
    estimates = estimate_credits(config,
                                 active_verticals=["food"],
                                 active_states=["TX"],
                                 active_channels=["web_search"])
    assert estimates["serpapi"]["estimated"] > 0
    assert estimates["apollo"]["estimated"] == 0

def test_format_warning_over_limit():
    estimates = {
        "serpapi": {"estimated": 1200, "limit": 1000},
        "apollo": {"estimated": 100, "limit": 30000},
        "hunter": {"estimated": 50, "limit": 1000}
    }
    warning = format_credit_warning(estimates)
    assert "1200" in warning or "WARNING" in warning.upper()

def test_format_summary():
    actuals = {"serpapi": 115, "apollo": 283, "hunter_search": 75, "hunter_verify": 0}
    limits = {"serpapi": 1000, "apollo": 30000, "hunter_search": 1000, "hunter_verify": 1000}
    summary = format_credit_summary(actuals, limits)
    assert "115" in summary
    assert "283" in summary
