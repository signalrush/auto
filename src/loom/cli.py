"""CLI entry point for loom-run."""

import asyncio
import importlib.util
import sys
import os


def main():
    if len(sys.argv) < 2:
        print("Usage: loom-run <program.py> [--port PORT]", file=sys.stderr)
        sys.exit(1)

    program_path = sys.argv[1]
    port = "54321"

    # Parse --port
    for i, arg in enumerate(sys.argv[2:], start=2):
        if arg == "--port" and i + 1 < len(sys.argv):
            port = sys.argv[i + 1]

    if not os.path.isfile(program_path):
        print(f"Error: {program_path} not found", file=sys.stderr)
        sys.exit(1)

    # Load the program module
    spec = importlib.util.spec_from_file_location("__loom_program__", program_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, "main"):
        print(f"Error: {program_path} must define `async def main(step)`", file=sys.stderr)
        sys.exit(1)

    server_url = os.environ.get("LOOM_SERVER_URL", f"http://localhost:{port}")

    from loom.step import run_program
    asyncio.run(run_program(module.main, server_url=server_url))


if __name__ == "__main__":
    main()
