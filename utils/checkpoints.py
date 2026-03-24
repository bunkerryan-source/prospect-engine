"""
Checkpoint system for crash recovery.

Saves pipeline module outputs to disk so a run can be resumed
from the last completed module rather than restarting from scratch.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from typing import Optional

# Canonical order for module checkpoint filenames
_MODULE_ORDER: dict[str, str] = {
    "web_search": "01",
    "sqep": "02",
    "import_search": "03",
    "apollo": "04",
    "dedup": "05",
    "hunter": "06",
}


class CheckpointManager:
    """Manage per-run checkpoint files in a dedicated run directory."""

    def __init__(self, config: dict) -> None:
        checkpoint_cfg = config.get("checkpoints", {})
        self._directory: str = checkpoint_cfg.get("directory", "checkpoints")
        self._keep_on_success: bool = checkpoint_cfg.get("keep_on_success", True)
        self.run_dir: Optional[str] = None

    # ------------------------------------------------------------------
    # Run lifecycle
    # ------------------------------------------------------------------

    def start_run(self) -> None:
        """Create a timestamped directory for this run and store as run_dir."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.run_dir = os.path.join(self._directory, f"run_{timestamp}")
        os.makedirs(self.run_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Save / load
    # ------------------------------------------------------------------

    def save(self, module_name: str, prospects: list[dict], *, credits_used: int = 0) -> None:
        """Serialize *prospects* to ``{order}_{module}_complete.json`` in run_dir."""
        if self.run_dir is None:
            raise RuntimeError("start_run() must be called before save()")

        order = _MODULE_ORDER.get(module_name, "99")
        filename = f"{order}_{module_name}_complete.json"
        filepath = os.path.join(self.run_dir, filename)

        payload = {
            "module": module_name,
            "timestamp": datetime.now().isoformat(),
            "credits_used": credits_used,
            "prospect_count": len(prospects),
            "prospects": prospects,
        }

        with open(filepath, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, default=str)

    def get_completed_modules(self) -> set[str]:
        """Return the set of module names that have a checkpoint file in run_dir."""
        if self.run_dir is None or not os.path.exists(self.run_dir):
            return set()

        completed: set[str] = set()
        for fname in os.listdir(self.run_dir):
            if fname.endswith("_complete.json"):
                # filename pattern: {order}_{module}_complete.json
                # Strip leading order prefix and trailing _complete suffix
                without_ext = fname[:-len("_complete.json")]
                # Remove the leading "NN_" order prefix
                parts = without_ext.split("_", 1)
                if len(parts) == 2 and parts[0].isdigit():
                    completed.add(parts[1])
                else:
                    completed.add(without_ext)
        return completed

    def load(self, module_name: str) -> list[dict]:
        """Load and return the prospects list from a module's checkpoint file."""
        if self.run_dir is None:
            raise RuntimeError("start_run() must be called before load()")

        order = _MODULE_ORDER.get(module_name, "99")
        filename = f"{order}_{module_name}_complete.json"
        filepath = os.path.join(self.run_dir, filename)

        with open(filepath, "r", encoding="utf-8") as fh:
            payload = json.load(fh)

        return payload.get("prospects", [])

    def load_all(self) -> list[dict]:
        """Load all checkpoint files and combine their prospect lists."""
        if self.run_dir is None or not os.path.exists(self.run_dir):
            return []

        combined: list[dict] = []
        checkpoint_files = sorted(
            f for f in os.listdir(self.run_dir) if f.endswith("_complete.json")
        )

        for fname in checkpoint_files:
            filepath = os.path.join(self.run_dir, fname)
            with open(filepath, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
            combined.extend(payload.get("prospects", []))

        return combined

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup(self, keep: bool = False) -> None:
        """Delete run_dir unless *keep* is True."""
        if keep or self.run_dir is None:
            return
        if os.path.exists(self.run_dir):
            shutil.rmtree(self.run_dir)
