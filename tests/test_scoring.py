import pytest
from scoring.scorer import score_prospect, score_prospects
from models import ProspectRecord

def load_test_config():
    return {
        "scoring": {
            "signal_density": {"1_source": 5, "2_sources": 15, "3_sources": 25, "4_plus_sources": 35},
            "compliance": {"walmart_supplier": 10, "sqep_mentioned": 10, "otif_mentioned": 10, "compliance_pain": 10},
            "geography": {"in_target_state": 15, "other": 0},
            "enrichment": {
                "verified_email_logistics_title": 15, "email_non_logistics_title": 10,
                "email_pattern_found": 5, "contact_name_no_email": 3, "website_only": 0
            },
            "vertical_multipliers": {"food": 1.3, "fragrance": 1.2, "nutraceutical": 1.15,
                                      "pharma": 1.1, "flavor": 1.0, "unknown": 0.8},
            "tiers": {"hot": 70, "warm": 45, "nurture": 25}
        }
    }

def test_hot_prospect():
    config = load_test_config()
    p = ProspectRecord(
        company_name="Acme Food",
        source_channel="web_search,apollo,sqep",
        compliance_signals="walmart_supplier,sqep_mentioned",
        state="TX",
        vertical="food",
        contact_email="j@acme.com",
        contact_title="Director of Logistics",
        contact_source="apollo"
    )
    result = score_prospect(p, config, target_states=["TX", "LA"])
    # Signal:25(3src) + Compliance:20(2sig) + Geo:15(TX) + Enrich:15(email+logistics) = 75 * 1.3(food) = 97.5 -> 98
    assert result.score == 98
    assert result.tier == "HOT"
    assert "Signal:25" in result.score_breakdown

def test_warm_prospect():
    config = load_test_config()
    p = ProspectRecord(
        company_name="Beta Pharma",
        source_channel="web_search,apollo",
        state="TX",
        vertical="pharma",
        contact_email="info@beta.com",
        contact_title="CEO",
        contact_source="hunter"
    )
    result = score_prospect(p, config, target_states=["TX"])
    # Signal:15(2src) + Compliance:0 + Geo:15(TX) + Enrich:10(email+non-logistics) = 40 * 1.1(pharma) = 44 -> NURTURE
    assert result.tier == "NURTURE"

def test_park_prospect():
    config = load_test_config()
    p = ProspectRecord(company_name="Tiny Co", source_channel="web_search", state="NY")
    result = score_prospect(p, config, target_states=["TX"])
    # Signal:5(1src) + Compliance:0 + Geo:0(NY) + Enrich:0(no contact) = 5 * 0.8(unknown) = 4 -> PARK
    assert result.tier == "PARK"

def test_multi_vertical_uses_max_multiplier():
    config = load_test_config()
    p = ProspectRecord(company_name="Combo", source_channel="web_search",
                       vertical="food,pharma", state="TX")
    result = score_prospect(p, config, target_states=["TX"])
    # 5 + 0 + 15 + 0 = 20 * 1.3(food, max) = 26
    assert result.score == 26

def test_score_prospects_batch():
    config = load_test_config()
    prospects = [
        ProspectRecord(company_name="A", source_channel="web_search", state="TX"),
        ProspectRecord(company_name="B", source_channel="apollo,sqep", state="TX",
                       compliance_signals="walmart_supplier")
    ]
    results = score_prospects(prospects, config, target_states=["TX"])
    assert len(results) == 2
    assert all(r.score > 0 for r in results)
    assert all(r.tier != "" for r in results)
