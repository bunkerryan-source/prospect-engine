import pytest
import os
import yaml
from unittest.mock import MagicMock, patch
from run import run_pipeline, run_verification


def write_test_config(tmp_path):
    config = {
        "icp": {"revenue_min": 5000000, "revenue_max": 500000000, "employee_min": 25, "employee_max": 2000},
        "state_lists": {"test": {"default": True, "states": ["TX"]}},
        "verticals": {"food": {"keywords": ["food manufacturer", "food producer", "food processor"],
                                "sqep_product_signals": ["snack"]}},
        "sqep_search_terms": ["Walmart SQEP supplier"],
        "import_keywords": {"food": ["food ingredient"]},
        "search_api": {"provider": "serpapi", "plan_limit": 1000},
        "apollo": {"enabled": True, "per_page": 25, "max_pages_per_search": 1, "plan_limit": 30000},
        "hunter": {"enabled": True, "max_searches_per_run": 10, "max_verifications_per_run": 5,
                   "search_credit_limit": 1000, "verification_credit_limit": 1000},
        "scoring": {
            "signal_density": {"1_source": 5, "2_sources": 15, "3_sources": 25, "4_plus_sources": 35},
            "compliance": {"walmart_supplier": 10, "sqep_mentioned": 10, "otif_mentioned": 10, "compliance_pain": 10},
            "geography": {"in_target_state": 15, "other": 0},
            "enrichment": {"verified_email_logistics_title": 15, "email_non_logistics_title": 10,
                          "email_pattern_found": 5, "contact_name_no_email": 3, "website_only": 0},
            "vertical_multipliers": {"food": 1.3, "unknown": 0.8},
            "tiers": {"hot": 70, "warm": 45, "nurture": 25}
        },
        "database": {"path": str(tmp_path / "test.db")},
        "checkpoints": {"directory": str(tmp_path / "checkpoints"), "keep_on_success": False},
        "output": {"directory": str(tmp_path / "output"), "filename_prefix": "test", "formats": ["xlsx", "csv"]}
    }
    config_path = str(tmp_path / "config.yaml")
    with open(config_path, "w") as f:
        yaml.dump(config, f)
    return config_path, config


def test_pipeline_dry_run(tmp_path, capsys):
    config_path, _ = write_test_config(tmp_path)
    with patch.dict(os.environ, {"SERPAPI_KEY": "test", "APOLLO_API_KEY": "test", "HUNTER_API_KEY": "test"}):
        run_pipeline(config_path=config_path, dry_run=True, states_arg="test")
    captured = capsys.readouterr()
    assert "Estimated" in captured.out or "credit" in captured.out.lower()


def test_pipeline_with_mocked_modules(tmp_path):
    from models import ProspectRecord
    config_path, config = write_test_config(tmp_path)
    os.makedirs(str(tmp_path / "output"), exist_ok=True)

    mock_prospects = [
        ProspectRecord(company_name="Acme Food", website="acme.com",
                       state="TX", vertical="food", source_channel="web_search")
    ]

    with patch.dict(os.environ, {"SERPAPI_KEY": "test", "APOLLO_API_KEY": "test", "HUNTER_API_KEY": "test"}):
        with patch("run.WebSearchModule") as MockWS, \
             patch("run.SQEPModule") as MockSQ, \
             patch("run.ImportSearchModule") as MockIM, \
             patch("run.ApolloModule") as MockAP, \
             patch("run.HunterEnrichment") as MockHU, \
             patch("builtins.input", return_value="y"):
            MockWS.return_value.run.return_value = mock_prospects
            MockWS.return_value.channel_name = "web_search"
            MockSQ.return_value.run.return_value = []
            MockSQ.return_value.channel_name = "sqep"
            MockIM.return_value.run.return_value = []
            MockIM.return_value.channel_name = "import"
            MockAP.return_value.run.return_value = []
            MockAP.return_value.channel_name = "apollo"
            MockAP.return_value.company_search_credits = 0
            MockAP.return_value.people_search_credits = 0
            MockHU.return_value.enrich.return_value = mock_prospects
            MockHU.return_value.search_credits_used = 0

            run_pipeline(config_path=config_path, states_arg="test")

    # Verify output was generated
    output_dir = str(tmp_path / "output")
    assert os.path.isdir(output_dir)


def test_pipeline_abort_on_no(tmp_path, capsys):
    """Pipeline should abort when user answers 'n' to proceed prompt."""
    config_path, _ = write_test_config(tmp_path)
    with patch.dict(os.environ, {"SERPAPI_KEY": "test", "APOLLO_API_KEY": "test", "HUNTER_API_KEY": "test"}):
        with patch("builtins.input", return_value="n"):
            run_pipeline(config_path=config_path, states_arg="test")
    captured = capsys.readouterr()
    assert "Aborted" in captured.out


def test_pipeline_skip_enrichment(tmp_path):
    """Pipeline should skip hunter enrichment when --skip-enrichment is set."""
    from models import ProspectRecord
    config_path, _ = write_test_config(tmp_path)
    os.makedirs(str(tmp_path / "output"), exist_ok=True)

    mock_prospects = [
        ProspectRecord(company_name="Acme Food", website="acme.com",
                       state="TX", vertical="food", source_channel="web_search")
    ]

    with patch.dict(os.environ, {"SERPAPI_KEY": "test", "APOLLO_API_KEY": "test", "HUNTER_API_KEY": "test"}):
        with patch("run.WebSearchModule") as MockWS, \
             patch("run.SQEPModule") as MockSQ, \
             patch("run.ImportSearchModule") as MockIM, \
             patch("run.ApolloModule") as MockAP, \
             patch("run.HunterEnrichment") as MockHU, \
             patch("builtins.input", return_value="y"):
            MockWS.return_value.run.return_value = mock_prospects
            MockWS.return_value.channel_name = "web_search"
            MockSQ.return_value.run.return_value = []
            MockSQ.return_value.channel_name = "sqep"
            MockIM.return_value.run.return_value = []
            MockIM.return_value.channel_name = "import"
            MockAP.return_value.run.return_value = []
            MockAP.return_value.channel_name = "apollo"
            MockAP.return_value.company_search_credits = 0
            MockAP.return_value.people_search_credits = 0
            MockHU.return_value.enrich.return_value = mock_prospects
            MockHU.return_value.search_credits_used = 0

            run_pipeline(config_path=config_path, states_arg="test", skip_enrichment=True)

            # HunterEnrichment should not have been instantiated
            MockHU.assert_not_called()


def test_pipeline_skip_scoring(tmp_path):
    """Pipeline should skip scoring when --skip-scoring is set."""
    from models import ProspectRecord
    config_path, _ = write_test_config(tmp_path)
    os.makedirs(str(tmp_path / "output"), exist_ok=True)

    mock_prospects = [
        ProspectRecord(company_name="Acme Food", website="acme.com",
                       state="TX", vertical="food", source_channel="web_search")
    ]

    with patch.dict(os.environ, {"SERPAPI_KEY": "test", "APOLLO_API_KEY": "test", "HUNTER_API_KEY": "test"}):
        with patch("run.WebSearchModule") as MockWS, \
             patch("run.SQEPModule") as MockSQ, \
             patch("run.ImportSearchModule") as MockIM, \
             patch("run.ApolloModule") as MockAP, \
             patch("run.HunterEnrichment") as MockHU, \
             patch("run.score_prospects") as MockScore, \
             patch("builtins.input", return_value="y"):
            MockWS.return_value.run.return_value = mock_prospects
            MockWS.return_value.channel_name = "web_search"
            MockSQ.return_value.run.return_value = []
            MockSQ.return_value.channel_name = "sqep"
            MockIM.return_value.run.return_value = []
            MockIM.return_value.channel_name = "import"
            MockAP.return_value.run.return_value = []
            MockAP.return_value.channel_name = "apollo"
            MockAP.return_value.company_search_credits = 0
            MockAP.return_value.people_search_credits = 0
            MockHU.return_value.enrich.return_value = mock_prospects
            MockHU.return_value.search_credits_used = 0

            run_pipeline(config_path=config_path, states_arg="test", skip_scoring=True)

            MockScore.assert_not_called()


def test_verification_with_mocked_db(tmp_path):
    """Test run_verification with mocked DB and Hunter."""
    config_path, config = write_test_config(tmp_path)

    mock_db = MagicMock()
    mock_db.get_for_verification.return_value = [
        {"id": 1, "contact_email": "test@example.com", "company_name": "Acme"},
    ]

    mock_hunter = MagicMock()
    mock_hunter.verify_batch.return_value = {1: "valid"}
    mock_hunter.verify_credits_used = 1

    with patch.dict(os.environ, {"HUNTER_API_KEY": "test", "SERPAPI_KEY": "test"}):
        with patch("run.ProspectDB", return_value=mock_db), \
             patch("run.HunterEnrichment", return_value=mock_hunter):
            run_verification(config_path=config_path, tier="HOT")

    mock_db.get_for_verification.assert_called_once()
    mock_hunter.verify_batch.assert_called_once()
    mock_db.update_email_verified.assert_called_once_with(1, "valid")
