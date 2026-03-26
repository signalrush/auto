# tests/test_run_folder.py
import os
import json
import time
from pathlib import Path

from auto.run_folder import create_run_folder, read_state, write_state


class TestRunFolder:
    def test_create_run_folder_creates_structure(self, tmp_path):
        """Run folder has correct structure with logs/ subdir."""
        run_dir = create_run_folder(tmp_path / ".auto")
        assert run_dir.exists()
        assert (run_dir / "logs").is_dir()
        assert run_dir.name.startswith("run-")
        parts = run_dir.name.split("-")
        assert len(parts) >= 4  # run-YYYYMMDD-HHMMSS-PID

    def test_create_run_folder_creates_latest_symlink(self, tmp_path):
        """latest symlink points to the new run folder."""
        auto_dir = tmp_path / ".auto"
        run_dir = create_run_folder(auto_dir)
        latest = auto_dir / "latest"
        assert latest.is_symlink()
        assert latest.resolve() == run_dir.resolve()

    def test_create_run_folder_updates_latest_on_second_run(self, tmp_path):
        """Second run atomically replaces the latest symlink."""
        auto_dir = tmp_path / ".auto"
        run1 = create_run_folder(auto_dir)
        run2 = create_run_folder(auto_dir)
        latest = auto_dir / "latest"
        assert latest.resolve() == run2.resolve()
        assert run1.exists()  # old run still exists

    def test_write_state_creates_file(self, tmp_path):
        """write_state creates a JSON file atomically."""
        state_path = tmp_path / "self.json"
        data = {"status": "pending", "step_number": 1, "instruction": "do X"}
        write_state(state_path, data)
        assert state_path.exists()
        loaded = json.loads(state_path.read_text())
        assert loaded["status"] == "pending"
        assert "updated_at" in loaded

    def test_read_state_returns_none_on_missing(self, tmp_path):
        """read_state returns None if file doesn't exist."""
        result = read_state(tmp_path / "missing.json")
        assert result is None

    def test_read_state_returns_none_on_invalid_json(self, tmp_path):
        """read_state returns None on corrupt JSON."""
        bad = tmp_path / "bad.json"
        bad.write_text("not json{{{")
        assert read_state(bad) is None

    def test_write_state_is_atomic(self, tmp_path):
        """write_state uses temp file + rename."""
        state_path = tmp_path / "state.json"
        write_state(state_path, {"status": "pending"})
        # No leftover temp files
        temps = list(tmp_path.glob("*.tmp"))
        assert len(temps) == 0
