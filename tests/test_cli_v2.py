# tests/test_cli_v2.py
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import auto.cli as cli_mod


def _mock_popen(pid=12345):
    mock = MagicMock()
    mock.pid = pid
    return mock


class TestRunFolderIntegration:
    def test_start_creates_run_folder(self, tmp_path, monkeypatch):
        """auto-run program.py creates ~/.auto/run-{ts}-{pid}/."""
        monkeypatch.chdir(tmp_path)
        prog = tmp_path / "prog.py"
        prog.write_text("async def main(auto): pass\n")
        (tmp_path / ".claude").mkdir()

        monkeypatch.setattr(cli_mod, "AUTO_DIR", str(tmp_path / ".auto"))
        monkeypatch.setattr(cli_mod, "PID_FILE", str(tmp_path / ".auto" / "auto.pid"))

        with patch.object(subprocess, "Popen", return_value=_mock_popen(111)):
            with patch.object(cli_mod, "_setup_hook"):
                cli_mod._start_program(str(prog))

        auto_dir = tmp_path / ".auto"
        assert auto_dir.exists()
        latest = auto_dir / "latest"
        assert latest.is_symlink()


class TestStatusMultiAgent:
    def test_status_shows_agent_states(self, tmp_path, capsys, monkeypatch):
        """auto-run status reads all .json files in latest/."""
        run_dir = tmp_path / ".auto" / "run-20260326-150000-99999"
        run_dir.mkdir(parents=True)
        (run_dir / "logs").mkdir()

        for name, status, step, instr in [
            ("self", "pending", 3, "check CI"),
            ("coder", "running", 1, "fix bug"),
        ]:
            (run_dir / f"{name}.json").write_text(json.dumps({
                "name": name,
                "status": status,
                "step_number": step,
                "last_instruction": instr,
                "updated_at": "2026-03-26T15:00:00Z",
            }))

        latest = tmp_path / ".auto" / "latest"
        os.symlink("run-20260326-150000-99999", latest)

        monkeypatch.setattr(cli_mod, "AUTO_DIR", str(tmp_path / ".auto"))
        monkeypatch.setattr(cli_mod, "PID_FILE", str(tmp_path / ".auto" / "auto.pid"))

        cli_mod._show_status()
        output = capsys.readouterr().out
        assert "self" in output
        assert "coder" in output


class TestLogWithAgentName:
    def test_tail_log_defaults_to_self(self, tmp_path, monkeypatch):
        run_dir = tmp_path / ".auto" / "run-test"
        (run_dir / "logs").mkdir(parents=True)
        (run_dir / "logs" / "self.log").write_text("hello\n")
        os.symlink("run-test", tmp_path / ".auto" / "latest")

        monkeypatch.setattr(cli_mod, "AUTO_DIR", str(tmp_path / ".auto"))
        log_path = Path(cli_mod.AUTO_DIR) / "latest" / "logs" / "self.log"
        assert log_path.exists()

    def test_tail_log_agent_name(self, tmp_path, monkeypatch):
        run_dir = tmp_path / ".auto" / "run-test"
        (run_dir / "logs").mkdir(parents=True)
        (run_dir / "logs" / "coder.log").write_text("agent log\n")
        os.symlink("run-test", tmp_path / ".auto" / "latest")

        monkeypatch.setattr(cli_mod, "AUTO_DIR", str(tmp_path / ".auto"))
        log_path = Path(cli_mod.AUTO_DIR) / "latest" / "logs" / "coder.log"
        assert log_path.exists()
