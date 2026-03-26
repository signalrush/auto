"""Run folder management for auto programs.

Each program run gets its own folder under ~/.auto/ (global, not project-local):
  ~/.auto/run-YYYYMMDD-HHMMSS-PID/
    self.json
    logs/
  ~/.auto/latest -> run-YYYYMMDD-HHMMSS-PID/
"""

import json
import os
import tempfile
import time
from pathlib import Path

_seq_counter = 0


def create_run_folder(auto_dir: Path) -> Path:
    """Create a timestamped run folder with logs/ subdir and latest symlink.

    Args:
        auto_dir: The ~/.auto/ directory.

    Returns:
        Path to the created run folder.
    """
    auto_dir.mkdir(parents=True, exist_ok=True)

    global _seq_counter
    ts = time.strftime("%Y%m%d-%H%M%S")
    pid = os.getpid()
    run_name = f"run-{ts}-{pid}"
    run_dir = auto_dir / run_name
    # Append sequence number if name already taken (same second, same PID)
    if run_dir.exists():
        _seq_counter += 1
        run_name = f"run-{ts}-{pid}-{_seq_counter}"
        run_dir = auto_dir / run_name
    run_dir.mkdir()
    (run_dir / "logs").mkdir()

    # Atomic symlink update
    latest = auto_dir / "latest"
    tmp_link = auto_dir / f".latest-{pid}.tmp"
    try:
        os.symlink(run_name, tmp_link)
        os.rename(tmp_link, latest)
    except OSError:
        try:
            os.unlink(latest)
        except FileNotFoundError:
            pass
        os.symlink(run_name, latest)

    return run_dir


def write_state(path: Path, data: dict) -> None:
    """Write state file atomically with updated_at timestamp."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    fd, temp_path = tempfile.mkstemp(
        dir=path.parent, prefix=".state-", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f)
            f.flush()
            os.fsync(f.fileno())
        os.rename(temp_path, path)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def read_state(path: Path) -> dict | None:
    """Read state file. Returns None if missing or invalid."""
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
