"""CLI entry point for auto-run."""

import asyncio
import importlib.util
import subprocess
import sys
import os
import signal


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print("Usage: auto-run <command> [args...]")
        print()
        print("Commands:")
        print("    auto-run <program.py>   Start an auto program in background")
        print("    auto-run status         Show running state and recent logs")
        print("    auto-run log            Tail the auto.log file")
        print("    auto-run stop           Kill running program")
        print()
        print("Environment Variables:")
        print("    AUTO_SESSION_ID         Resume a specific session")
        print("    AUTO_MODEL              Model to use (e.g. claude-haiku-4-5)")
        print("    AUTO_PROVIDER           Provider (default: anthropic)")
        sys.exit(0)

    command = sys.argv[1]

    if command == "status":
        _show_status()
    elif command == "log":
        _tail_log()
    elif command == "stop":
        _stop_program()
    elif command.endswith(".py"):
        _start_program(command)
    else:
        print(f"Error: Unknown command '{command}'", file=sys.stderr)
        sys.exit(1)


PID_FILE = ".auto.pid"
LOG_FILE = "auto.log"


def _start_program(program_path):
    if not os.path.isfile(program_path):
        print(f"Error: {program_path} not found", file=sys.stderr)
        sys.exit(1)

    # Check if already running
    if os.path.isfile(PID_FILE):
        with open(PID_FILE) as f:
            old_pid = int(f.read().strip())
        try:
            os.kill(old_pid, 0)
            print(f"Error: Auto program already running (PID {old_pid})", file=sys.stderr)
            print("Use 'auto-run stop' first", file=sys.stderr)
            sys.exit(1)
        except ProcessLookupError:
            os.remove(PID_FILE)

    program_path = os.path.abspath(program_path)

    # Always run in background via subprocess
    # This prevents deadlock when called from an agent session
    proc = subprocess.Popen(
        [sys.executable, "-c", f"""
import asyncio, importlib.util, sys, os
sys.path.insert(0, os.getcwd())
spec = importlib.util.spec_from_file_location('program', {program_path!r})
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
from auto.step import run_program
asyncio.run(run_program(mod.main))
"""],
        stdout=open(LOG_FILE, "w"),
        stderr=subprocess.STDOUT,
        start_new_session=True,  # detach from parent
    )

    with open(PID_FILE, "w") as f:
        f.write(str(proc.pid))

    print(f"[auto] Started in background (PID {proc.pid})")
    print(f"[auto] Logs: {LOG_FILE}")
    print(f"[auto] Monitor: auto-run status")


def _show_status():
    print("=== Auto Status ===")

    if os.path.isfile(PID_FILE):
        with open(PID_FILE) as f:
            pid = int(f.read().strip())
        try:
            os.kill(pid, 0)
            print(f"Process: Running (PID {pid})")
        except ProcessLookupError:
            print("Process: Not running (stale PID file)")
            os.remove(PID_FILE)
            return
    else:
        print("Process: Not running")
        return

    # Show state
    print()
    print("=== State ===")
    if os.path.isfile("auto-state.json"):
        with open("auto-state.json") as f:
            print(f.read())
    else:
        print("No state file found")

    # Show recent logs
    print()
    print("=== Recent Log ===")
    if os.path.isfile(LOG_FILE):
        with open(LOG_FILE) as f:
            lines = f.readlines()
            for line in lines[-10:]:
                print(line, end="")
    else:
        print("No log file found")


def _tail_log():
    if not os.path.isfile(LOG_FILE):
        print(f"Error: {LOG_FILE} not found", file=sys.stderr)
        sys.exit(1)
    os.execvp("tail", ["tail", "-f", LOG_FILE])


def _stop_program():
    if not os.path.isfile(PID_FILE):
        print("No running auto program found")
        return

    with open(PID_FILE) as f:
        pid = int(f.read().strip())

    print(f"Stopping auto program (PID {pid})...")
    try:
        os.kill(pid, signal.SIGTERM)
        # Wait briefly
        import time
        for _ in range(10):
            time.sleep(1)
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
        else:
            os.kill(pid, signal.SIGKILL)
        print("Program stopped")
    except ProcessLookupError:
        print("Process already stopped")

    os.remove(PID_FILE)


if __name__ == "__main__":
    main()
