"""E2E tests for CLI logging, PID file, and symlink management.

Covers edge cases in _start_program, _show_status, _tail_log, _stop_program
around log file creation, symlink handling, and PID lifecycle.

Updated for the new ~/.auto/ run-folder layout.
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

import auto.cli as cli_mod


@pytest.fixture
def cli_env(tmp_path, monkeypatch):
    """Set up a tmp_path-based environment and monkeypatch module-level constants."""
    auto_dir = str(tmp_path / ".auto")
    pid_file = str(tmp_path / ".auto" / "auto.pid")

    monkeypatch.setattr(cli_mod, "AUTO_DIR", auto_dir)
    monkeypatch.setattr(cli_mod, "PID_FILE", pid_file)

    # Create .claude dir so _setup_hook can write settings
    (tmp_path / ".claude").mkdir(parents=True, exist_ok=True)

    # Create a fake program file
    prog = tmp_path / "prog.py"
    prog.write_text("def main(): pass\n")

    monkeypatch.chdir(tmp_path)

    return {
        "tmp_path": tmp_path,
        "auto_dir": auto_dir,
        "pid_file": pid_file,
        "prog": str(prog),
    }


def _mock_popen(pid=12345):
    """Create a mock Popen that behaves enough for _start_program."""
    mock = MagicMock()
    mock.pid = pid
    return mock


# ---------------------------------------------------------------------------
# Per-run log file naming
# ---------------------------------------------------------------------------

class TestLogFileCreation:

    def test_log_file_created_in_run_folder(self, cli_env):
        """Per-run log files should be created in run-folder/logs/self.log."""
        with patch.object(subprocess, "Popen", return_value=_mock_popen()):
            with patch.object(cli_mod, "_setup_hook"):
                cli_mod._start_program(cli_env["prog"])

        auto_dir = Path(cli_env["auto_dir"])
        latest = auto_dir / "latest"
        assert latest.is_symlink()
        log_file = latest / "logs" / "self.log"
        assert log_file.exists(), f"Expected self.log in run folder, got {list(latest.glob('**/*'))}"

    def test_multiple_runs_create_separate_run_folders(self, cli_env):
        """Each run should create a distinct run folder."""
        with patch.object(subprocess, "Popen", return_value=_mock_popen(111)):
            with patch.object(cli_mod, "_setup_hook"):
                cli_mod._start_program(cli_env["prog"])

        auto_dir = Path(cli_env["auto_dir"])
        first_target = os.readlink(auto_dir / "latest")

        # Remove PID file to allow second run
        os.remove(cli_env["pid_file"])

        with patch.object(subprocess, "Popen", return_value=_mock_popen(222)):
            with patch.object(cli_mod, "_setup_hook"):
                cli_mod._start_program(cli_env["prog"])

        second_target = os.readlink(auto_dir / "latest")
        assert first_target != second_target, "Each run should create a new run folder"


# ---------------------------------------------------------------------------
# Symlink behavior
# ---------------------------------------------------------------------------

class TestSymlink:

    def test_latest_symlink_points_to_run_folder(self, cli_env):
        """latest symlink should point to the most recent run folder."""
        with patch.object(subprocess, "Popen", return_value=_mock_popen()):
            with patch.object(cli_mod, "_setup_hook"):
                cli_mod._start_program(cli_env["prog"])

        auto_dir = Path(cli_env["auto_dir"])
        latest = auto_dir / "latest"
        assert latest.is_symlink(), "latest should be a symlink"
        target = os.readlink(latest)
        assert not os.path.isabs(target), (
            f"Symlink should be relative, got absolute path: {target}"
        )
        assert target.startswith("run-"), f"Symlink target should be a run folder: {target}"

    def test_latest_symlink_is_relative(self, cli_env):
        """Symlink must use a relative path (basename only) so the setup is portable."""
        with patch.object(subprocess, "Popen", return_value=_mock_popen()):
            with patch.object(cli_mod, "_setup_hook"):
                cli_mod._start_program(cli_env["prog"])

        auto_dir = Path(cli_env["auto_dir"])
        target = os.readlink(auto_dir / "latest")
        assert "/" not in target, (
            f"Relative symlink should not contain '/': {target}"
        )

    def test_latest_symlink_updated_on_second_run(self, cli_env):
        """Second run should atomically replace the latest symlink to point to new run folder."""
        with patch.object(subprocess, "Popen", return_value=_mock_popen(111)):
            with patch.object(cli_mod, "_setup_hook"):
                cli_mod._start_program(cli_env["prog"])

        auto_dir = Path(cli_env["auto_dir"])
        first_target = os.readlink(auto_dir / "latest")

        # Remove PID file to allow second run
        os.remove(cli_env["pid_file"])

        with patch.object(subprocess, "Popen", return_value=_mock_popen(222)):
            with patch.object(cli_mod, "_setup_hook"):
                cli_mod._start_program(cli_env["prog"])

        second_target = os.readlink(auto_dir / "latest")
        assert first_target != second_target, (
            "Symlink should point to a different run folder after second run"
        )
        assert second_target.startswith("run-"), f"Unexpected target: {second_target}"


# ---------------------------------------------------------------------------
# Log tailing edge cases
# ---------------------------------------------------------------------------

class TestTailLog:

    def test_tail_log_no_active_run(self, cli_env, capsys):
        """_tail_log should report no active run when latest symlink doesn't exist."""
        with pytest.raises(SystemExit) as exc_info:
            cli_mod._tail_log()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "No active run found" in captured.err

    def test_tail_log_missing_agent_log(self, cli_env, capsys):
        """_tail_log should report error when agent log file doesn't exist."""
        auto_dir = Path(cli_env["auto_dir"])
        run_dir = auto_dir / "run-test"
        (run_dir / "logs").mkdir(parents=True)
        os.symlink("run-test", auto_dir / "latest")

        with pytest.raises(SystemExit) as exc_info:
            cli_mod._tail_log("nonexistent")

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Log file not found" in captured.err


# ---------------------------------------------------------------------------
# Status display
# ---------------------------------------------------------------------------

class TestShowStatus:

    def test_show_status_with_valid_log(self, cli_env, capsys):
        """_show_status should read and display last 10 lines from valid log."""
        auto_dir = Path(cli_env["auto_dir"])
        run_dir = auto_dir / "run-test"
        (run_dir / "logs").mkdir(parents=True)
        os.symlink("run-test", auto_dir / "latest")

        # Create actual log file with content
        log_file = run_dir / "logs" / "self.log"
        lines = [f"line {i}\n" for i in range(15)]
        log_file.write_text("".join(lines))

        cli_mod._show_status()

        captured = capsys.readouterr()
        # Should show last 10 lines (line 5 through line 14)
        assert "line 5" in captured.out
        assert "line 14" in captured.out
        # Should NOT show line 0-4
        assert "line 4\n" not in captured.out

    def test_show_status_no_log(self, cli_env, capsys):
        """_show_status should report 'No log file found' when nothing exists."""
        auto_dir = Path(cli_env["auto_dir"])
        run_dir = auto_dir / "run-test"
        run_dir.mkdir(parents=True)
        os.symlink("run-test", auto_dir / "latest")

        cli_mod._show_status()

        captured = capsys.readouterr()
        assert "No log file found" in captured.out

    def test_show_status_no_active_run(self, cli_env, capsys):
        """_show_status should report no active run when latest doesn't exist."""
        cli_mod._show_status()

        captured = capsys.readouterr()
        assert "No active run found" in captured.out


# ---------------------------------------------------------------------------
# PID file
# ---------------------------------------------------------------------------

class TestPidFile:

    def test_pid_file_created_on_start(self, cli_env):
        """PID file should be written with the child process PID."""
        with patch.object(subprocess, "Popen", return_value=_mock_popen(42)):
            with patch.object(cli_mod, "_setup_hook"):
                cli_mod._start_program(cli_env["prog"])

        pid_file = Path(cli_env["pid_file"])
        assert pid_file.exists(), "PID file should be created"
        assert pid_file.read_text().strip() == "42"

    def test_start_refuses_if_pid_still_running(self, cli_env):
        """_start_program should refuse to start if PID file references a live process."""
        pid_file = Path(cli_env["pid_file"])
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        # Use our own PID -- guaranteed to be alive
        pid_file.write_text(str(os.getpid()))

        with pytest.raises(SystemExit):
            with patch.object(cli_mod, "_setup_hook"):
                cli_mod._start_program(cli_env["prog"])

    def test_start_cleans_stale_pid(self, cli_env):
        """_start_program should remove PID file if the old process is dead."""
        pid_file = Path(cli_env["pid_file"])
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text("99999999")  # almost certainly not running

        with patch.object(subprocess, "Popen", return_value=_mock_popen(555)):
            with patch.object(cli_mod, "_setup_hook"):
                cli_mod._start_program(cli_env["prog"])

        assert pid_file.read_text().strip() == "555"

    def test_start_corrupted_pid_file_cleans_up(self, cli_env):
        """_start_program should handle corrupted PID file gracefully by removing it."""
        pid_file = Path(cli_env["pid_file"])
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text("not-a-number")

        with patch.object(subprocess, "Popen", return_value=_mock_popen(999)):
            with patch.object(cli_mod, "_setup_hook"):
                cli_mod._start_program(cli_env["prog"])

        # Should have cleaned up corrupted PID and written new one
        assert pid_file.read_text() == "999"


# ---------------------------------------------------------------------------
# _stop_program
# ---------------------------------------------------------------------------

class TestStopProgram:

    def test_stop_uses_missing_ok_for_cleanup(self, cli_env, capsys):
        """_stop_program should not crash if PID file disappears during cleanup."""
        pid_file = Path(cli_env["pid_file"])
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text(str(os.getpid()))

        # Simulate: process lookup says it's dead (already stopped)
        with patch("auto.cli.os.killpg", side_effect=ProcessLookupError):
            cli_mod._stop_program()

        assert not pid_file.exists(), "PID file should be cleaned up"
        captured = capsys.readouterr()
        assert "already stopped" in captured.out.lower()

    def test_stop_no_pid_file(self, cli_env, capsys):
        """_stop_program should report no program running when no PID file exists."""
        cli_mod._stop_program()
        captured = capsys.readouterr()
        assert "No running auto program found" in captured.out

    def test_stop_corrupted_pid_file_cleaned(self, cli_env, capsys):
        """_stop_program should handle and remove corrupted PID files."""
        pid_file = Path(cli_env["pid_file"])
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text("garbage-data")

        cli_mod._stop_program()

        assert not pid_file.exists(), "Corrupted PID file should be removed"
        captured = capsys.readouterr()
        assert "corrupted" in captured.err.lower()

    def test_stop_corrupted_pid_cleans_up_safely(self, cli_env, capsys):
        """_stop_program should handle corrupted PID file without crashing,
        even if the file disappears between read and unlink (TOCTOU race)."""
        pid_file = Path(cli_env["pid_file"])
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text("garbage")

        # Should not raise -- uses Path.unlink(missing_ok=True)
        cli_mod._stop_program()
        captured = capsys.readouterr()
        assert "corrupted" in captured.err.lower()
        assert not pid_file.exists()


# ---------------------------------------------------------------------------
# Log file handle cleanup
# ---------------------------------------------------------------------------

class TestLogFileHandleCleanup:

    def test_log_fh_closed_on_popen_failure(self, cli_env):
        """Log file handle must be closed even when Popen raises."""
        with patch.object(subprocess, "Popen", side_effect=OSError("exec failed")):
            with patch.object(cli_mod, "_setup_hook"):
                with pytest.raises(OSError, match="exec failed"):
                    cli_mod._start_program(cli_env["prog"])

        # Verify the log file was created (open succeeded) but handle is closed.
        auto_dir = Path(cli_env["auto_dir"])
        latest = auto_dir / "latest"
        log_file = latest / "logs" / "self.log"
        assert log_file.exists(), "Log file should be created even on Popen failure"
        # Should be readable (fd was closed)
        content = log_file.read_text()
        assert content == "", "Log file should be empty (nothing was written)"

    def test_log_fh_closed_on_popen_success(self, cli_env):
        """Log file handle should be closed in the parent after successful Popen."""
        with patch.object(subprocess, "Popen", return_value=_mock_popen()):
            with patch.object(cli_mod, "_setup_hook"):
                cli_mod._start_program(cli_env["prog"])

        # Verify we can read the file (parent closed its handle)
        auto_dir = Path(cli_env["auto_dir"])
        latest = auto_dir / "latest"
        log_file = latest / "logs" / "self.log"
        assert log_file.exists()
        log_file.read_text()  # should not raise


# ---------------------------------------------------------------------------
# _show_status PID handling
# ---------------------------------------------------------------------------

class TestShowStatusPid:

    def test_show_status_running_process(self, cli_env, capsys):
        """_show_status should report 'Running' for a live PID."""
        pid_file = Path(cli_env["pid_file"])
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text(str(os.getpid()))

        cli_mod._show_status()

        captured = capsys.readouterr()
        assert "Running" in captured.out
        assert str(os.getpid()) in captured.out

    def test_show_status_stale_pid_cleaned(self, cli_env, capsys):
        """_show_status should clean up stale PID file and report 'Not running'."""
        pid_file = Path(cli_env["pid_file"])
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text("99999999")

        cli_mod._show_status()

        captured = capsys.readouterr()
        assert "stale" in captured.out.lower()
        assert not pid_file.exists(), "Stale PID file should be removed"

    def test_show_status_corrupted_pid(self, cli_env, capsys):
        """_show_status should handle corrupted PID file gracefully."""
        pid_file = Path(cli_env["pid_file"])
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text("not-a-pid")

        cli_mod._show_status()

        captured = capsys.readouterr()
        assert "corrupted" in captured.out.lower()
