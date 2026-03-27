"""End-to-end tests for the v2 Auto API.

Tests the full flow without a live Claude session by simulating
the stop hook's response writing.
"""
import asyncio
import json
import os
import time
from pathlib import Path
from threading import Thread

from auto.core import Auto
from auto.step import run_program_v2
from auto.run_folder import read_state


def _simulate_hook_response(state_path: Path, step_number: int,
                            response: str, delay: float = 0.2):
    """Simulate the stop hook writing a response after a delay."""
    def _write():
        time.sleep(delay)
        with open(state_path) as f:
            state = json.load(f)
        state["status"] = "responded"
        state["response"] = response
        with open(state_path, "w") as f:
            json.dump(state, f)
    Thread(target=_write, daemon=True).start()


class TestRemindE2E:
    def test_remind_full_cycle(self, tmp_path):
        auto = Auto(project_root=tmp_path, auto_dir=tmp_path / ".auto")

        async def run():
            _simulate_hook_response(auto._self_state_path, 1, "the answer is 42")
            result = await auto.remind("what is the answer?")
            assert result == "the answer is 42"

        asyncio.run(run())

    def test_remind_with_schema_e2e(self, tmp_path):
        auto = Auto(project_root=tmp_path, auto_dir=tmp_path / ".auto")

        async def run():
            _simulate_hook_response(auto._self_state_path, 1, '{"score": 0.95}')
            result = await auto.remind("rate it", schema={"score": "float"})
            assert result["score"] == 0.95

        asyncio.run(run())

    def test_two_reminds_sequential(self, tmp_path):
        auto = Auto(project_root=tmp_path, auto_dir=tmp_path / ".auto")

        async def run():
            _simulate_hook_response(auto._self_state_path, 1, "first")
            r1 = await auto.remind("step 1")
            assert r1 == "first"

            _simulate_hook_response(auto._self_state_path, 2, "second")
            r2 = await auto.remind("step 2")
            assert r2 == "second"

        asyncio.run(run())

    def test_remind_timeout(self, tmp_path):
        auto = Auto(project_root=tmp_path, auto_dir=tmp_path / ".auto")

        async def run():
            try:
                await auto.remind("do something", timeout=0.5)
                assert False, "Should have raised TimeoutError"
            except (TimeoutError, asyncio.TimeoutError):
                pass

        asyncio.run(run())

    def test_remind_works_after_sleep(self, tmp_path):
        """Regression: program that sleeps between reminds should still work.

        The hook blocks in Phase 2 during the sleep. When the program writes
        "pending" after sleeping, the hook should pick it up.
        """
        auto = Auto(project_root=tmp_path, auto_dir=tmp_path / ".auto")

        async def run():
            # Simulate: sleep, then remind
            await asyncio.sleep(0.3)

            # Simulate hook responding (with a delay to mimic real hook)
            _simulate_hook_response(auto._self_state_path, 1, "hello 1")
            r1 = await auto.remind("say hello 1")
            assert r1 == "hello 1"

            # Sleep again, then another remind
            await asyncio.sleep(0.3)

            _simulate_hook_response(auto._self_state_path, 2, "hello 2")
            r2 = await auto.remind("say hello 2")
            assert r2 == "hello 2"

        asyncio.run(run())

        # Verify state file reflects correct step count
        state = read_state(auto._self_state_path)
        assert state["step_number"] == 2


class TestRunProgramV2Lifecycle:
    """Regression tests for run_program_v2 lifecycle bugs."""

    def test_writes_done_on_completion(self, tmp_path):
        """Regression: run_program_v2 must write status='done' after program
        finishes, otherwise the hook blocks forever in Phase 2 polling.
        """
        auto_dir = tmp_path / ".auto"

        async def program(auto):
            # Simulate hook response
            _simulate_hook_response(auto._self_state_path, 1, "ok")
            await auto.remind("do something")

        # Run with AUTO_RUN_DIR unset so run_program_v2 creates its own
        old_env = os.environ.pop("AUTO_RUN_DIR", None)
        try:
            os.environ["AUTO_RUN_DIR"] = ""
            # We need to create the run folder ourselves since we're
            # calling run_program_v2 directly (not through CLI)
            from auto.run_folder import create_run_folder
            run_dir = create_run_folder(auto_dir)
            os.environ["AUTO_RUN_DIR"] = str(run_dir)

            asyncio.run(run_program_v2(program))

            # The critical check: status must be "done"
            state = read_state(run_dir / "self.json")
            assert state is not None, "self.json should exist after program completes"
            assert state["status"] == "done", (
                f"Expected status='done' but got status='{state['status']}'. "
                f"Without 'done', the hook blocks forever in Phase 2."
            )
        finally:
            if old_env is not None:
                os.environ["AUTO_RUN_DIR"] = old_env
            elif "AUTO_RUN_DIR" in os.environ:
                del os.environ["AUTO_RUN_DIR"]

    def test_cli_and_program_share_same_run_folder(self, tmp_path):
        """Regression: CLI creates run folder and passes it to the child process
        via AUTO_RUN_DIR. The program must NOT create a second run folder.

        Previously, both CLI and run_program_v2 called create_run_folder(),
        creating two different folders. The hook read from one, the program
        wrote to the other, and they never communicated.
        """
        from auto.run_folder import create_run_folder

        auto_dir = tmp_path / ".auto"
        cli_run_dir = create_run_folder(auto_dir)

        # Simulate what the CLI does: set AUTO_RUN_DIR
        old_env = os.environ.get("AUTO_RUN_DIR")
        os.environ["AUTO_RUN_DIR"] = str(cli_run_dir)

        try:
            async def program(auto):
                # The auto object should use the CLI's run folder
                assert auto.run_dir == cli_run_dir, (
                    f"Program run_dir ({auto.run_dir}) != CLI run_dir ({cli_run_dir}). "
                    f"This means state and logs are in different folders."
                )
                # Write a file to verify it lands in the right place
                _simulate_hook_response(auto._self_state_path, 1, "ok")
                await auto.remind("test")

            asyncio.run(run_program_v2(program))

            # State should be in CLI's run folder, not a new one
            state = read_state(cli_run_dir / "self.json")
            assert state is not None
            assert state["status"] == "done"

            # No extra run folders should have been created
            run_dirs = [d for d in auto_dir.iterdir()
                       if d.is_dir() and d.name.startswith("run-")]
            assert len(run_dirs) == 1, (
                f"Expected 1 run folder but found {len(run_dirs)}: "
                f"{[d.name for d in run_dirs]}. "
                f"CLI and program are creating separate folders."
            )
        finally:
            if old_env is not None:
                os.environ["AUTO_RUN_DIR"] = old_env
            else:
                del os.environ["AUTO_RUN_DIR"]
