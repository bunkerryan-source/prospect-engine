import pytest
import os
from utils.checkpoints import CheckpointManager
from models import ProspectRecord

def test_save_and_load(tmp_path):
    config = {"checkpoints": {"directory": str(tmp_path), "keep_on_success": False}}
    mgr = CheckpointManager(config)
    mgr.start_run()
    prospects = [ProspectRecord(company_name="Acme", website="acme.com").to_dict()]
    mgr.save("web_search", prospects, credits_used=50)
    completed = mgr.get_completed_modules()
    assert "web_search" in completed
    loaded = mgr.load("web_search")
    assert len(loaded) == 1
    assert loaded[0]["company_name"] == "Acme"

def test_canonical_numbering(tmp_path):
    config = {"checkpoints": {"directory": str(tmp_path), "keep_on_success": False}}
    mgr = CheckpointManager(config)
    mgr.start_run()
    mgr.save("apollo", [ProspectRecord(company_name="A").to_dict()], credits_used=10)
    files = os.listdir(mgr.run_dir)
    assert any("04_apollo" in f for f in files)

def test_cleanup(tmp_path):
    config = {"checkpoints": {"directory": str(tmp_path), "keep_on_success": False}}
    mgr = CheckpointManager(config)
    mgr.start_run()
    mgr.save("web_search", [], credits_used=0)
    mgr.cleanup(keep=False)
    assert not os.path.exists(mgr.run_dir)

def test_load_all_combines(tmp_path):
    config = {"checkpoints": {"directory": str(tmp_path), "keep_on_success": False}}
    mgr = CheckpointManager(config)
    mgr.start_run()
    mgr.save("web_search", [ProspectRecord(company_name="A").to_dict()], credits_used=10)
    mgr.save("sqep", [ProspectRecord(company_name="B").to_dict()], credits_used=5)
    all_prospects = mgr.load_all()
    assert len(all_prospects) == 2
