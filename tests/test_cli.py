import pytest
import os
from unittest.mock import patch
from run import parse_args, resolve_states, check_api_keys


def test_parse_args_defaults():
    args = parse_args([])
    assert args.states is None
    assert args.nationwide is False
    assert args.dry_run is False


def test_parse_args_states():
    args = parse_args(["--states", "south_central,southeast"])
    assert args.states == "south_central,southeast"


def test_parse_args_nationwide():
    args = parse_args(["--nationwide"])
    assert args.nationwide is True


def test_parse_args_dry_run():
    args = parse_args(["--dry-run"])
    assert args.dry_run is True


def test_parse_args_resume():
    args = parse_args(["--resume"])
    assert args.resume is True


def test_parse_args_skip_enrichment():
    args = parse_args(["--skip-enrichment"])
    assert args.skip_enrichment is True


def test_parse_args_skip_scoring():
    args = parse_args(["--skip-scoring"])
    assert args.skip_scoring is True


def test_parse_args_verticals():
    args = parse_args(["--verticals", "food,pharma"])
    assert args.verticals == "food,pharma"


def test_parse_args_channels():
    args = parse_args(["--channels", "web_search,apollo"])
    assert args.channels == "web_search,apollo"


def test_parse_args_verify_emails():
    args = parse_args(["--verify-emails"])
    assert args.verify_emails is True


def test_parse_args_tier():
    args = parse_args(["--verify-emails", "--tier", "HOT"])
    assert args.tier == "HOT"


def test_parse_args_all_tiers():
    args = parse_args(["--verify-emails", "--all"])
    assert args.all_tiers is True


def test_parse_args_set_status():
    args = parse_args(["--set-status", "Acme Corp", "CONTACTED"])
    assert args.set_status == ["Acme Corp", "CONTACTED"]


def test_parse_args_pipeline():
    args = parse_args(["--pipeline"])
    assert args.pipeline is True


def test_parse_args_list_status():
    args = parse_args(["--list-status", "NEW"])
    assert args.list_status == "NEW"


def test_parse_args_search():
    args = parse_args(["--search", "food TX"])
    assert args.search == "food TX"


def test_parse_args_db_stats():
    args = parse_args(["--db-stats"])
    assert args.db_stats is True


def test_parse_args_export_db():
    args = parse_args(["--export-db", "output.csv"])
    assert args.export_db == "output.csv"


def test_parse_args_reset_db():
    args = parse_args(["--reset-db", "--confirm"])
    assert args.reset_db is True
    assert args.confirm is True


def test_parse_args_note():
    args = parse_args(["--set-status", "Acme", "CONTACTED", "--note", "Called them"])
    assert args.note == "Called them"


def test_resolve_states_named_list():
    config = {"state_lists": {"south_central": {"default": True, "states": ["TX", "LA", "AR", "OK"]}}}
    states = resolve_states(config, states_arg="south_central", nationwide=False)
    assert states == ["TX", "LA", "AR", "OK"]


def test_resolve_states_nationwide():
    config = {"state_lists": {}}
    states = resolve_states(config, states_arg=None, nationwide=True)
    assert len(states) == 50


def test_resolve_states_nonexistent_errors():
    config = {"state_lists": {"south_central": {"states": ["TX"]}}}
    with pytest.raises(SystemExit):
        resolve_states(config, states_arg="nonexistent", nationwide=False)


def test_resolve_states_default():
    config = {"state_lists": {"south_central": {"default": True, "states": ["TX", "LA"]}}}
    states = resolve_states(config, states_arg=None, nationwide=False)
    assert states == ["TX", "LA"]


def test_resolve_states_no_default_errors():
    config = {"state_lists": {"south_central": {"states": ["TX"]}}}
    with pytest.raises(SystemExit):
        resolve_states(config, states_arg=None, nationwide=False)


def test_resolve_states_multiple_lists():
    config = {"state_lists": {
        "south_central": {"states": ["TX", "LA"]},
        "southeast": {"states": ["FL", "GA"]},
    }}
    states = resolve_states(config, states_arg="south_central,southeast", nationwide=False)
    assert set(states) == {"TX", "LA", "FL", "GA"}


def test_check_api_keys_all_missing():
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("SERPAPI_KEY", None)
        os.environ.pop("APOLLO_API_KEY", None)
        os.environ.pop("HUNTER_API_KEY", None)
        with pytest.raises(SystemExit):
            check_api_keys()


def test_check_api_keys_partial(capsys):
    with patch.dict(os.environ, {"SERPAPI_KEY": "test"}, clear=True):
        keys = check_api_keys()
    assert keys["serpapi"] == "test"
    assert keys["apollo"] is None
    captured = capsys.readouterr()
    assert "APOLLO_API_KEY" in captured.out


def test_check_api_keys_all_present():
    with patch.dict(os.environ, {
        "SERPAPI_KEY": "s", "APOLLO_API_KEY": "a", "HUNTER_API_KEY": "h"
    }, clear=True):
        keys = check_api_keys()
    assert keys["serpapi"] == "s"
    assert keys["apollo"] == "a"
    assert keys["hunter"] == "h"
