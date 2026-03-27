"""Continuous bug-hunting loop: reviewer finds bugs, implementer fixes them."""

async def main(auto):
    auto.agent("reviewer", cwd="/home/tianhao/auto")
    auto.agent("implementer", cwd="/home/tianhao/auto")

    round_num = 0
    consecutive_clean = 0

    while True:
        round_num += 1

        # Reviewer: find bugs
        review = await auto.task(
            f"Round {round_num}: You are a code reviewer for the 'auto' project. "
            "This is a Python tool that orchestrates Claude Code sessions via a stop hook IPC mechanism. "
            "Key files: src/auto/core.py (Auto class with remind/task/agent), "
            "src/auto/step.py (run_program, run_program_v2, _extract_json), "
            "src/auto/hooks/stop-hook.sh (bash stop hook), "
            "src/auto/cli.py (CLI entry point), "
            "src/auto/agents.py (AgentHandle for claude -p), "
            "src/auto/run_folder.py (state file I/O). "
            "\n\n"
            "Read ALL of these files carefully. Look for: "
            "1. Race conditions in state file reads/writes "
            "2. Edge cases in JSON parsing or transcript extraction "
            "3. Missing error handling "
            "4. Field name mismatches between Python and bash "
            "5. Logic errors in the polling loops "
            "6. Anything that could cause hangs, crashes, or data loss "
            "\n\n"
            "Report ONLY real, concrete bugs with file paths and line numbers. "
            "Do NOT report style issues, missing docs, or hypothetical concerns. "
            "If you find no bugs, say 'NO_BUGS_FOUND'.",
            to="reviewer",
            schema={
                "bugs_found": "int",
                "bugs": "list of {file: str, line: int, severity: str, description: str, fix: str}",
                "clean": "bool"
            }
        )

        bugs_found = review.get("bugs_found", 0)
        is_clean = review.get("clean", False)

        if is_clean or bugs_found == 0:
            consecutive_clean += 1
            await auto.remind(
                f"Round {round_num}: Reviewer found no bugs. "
                f"Clean rounds so far: {consecutive_clean}. "
                f"Report this status briefly."
            )
            if consecutive_clean >= 3:
                await auto.remind(
                    f"Bug hunt complete after {round_num} rounds. "
                    f"3 consecutive clean reviews. Summarize what was fixed across all rounds."
                )
                break
            continue

        consecutive_clean = 0

        # Format bugs for the implementer
        bug_descriptions = []
        for i, bug in enumerate(review.get("bugs", []), 1):
            bug_descriptions.append(
                f"Bug {i} [{bug.get('severity', '?')}]: {bug.get('file', '?')}:{bug.get('line', '?')} — "
                f"{bug.get('description', '?')}\n  Suggested fix: {bug.get('fix', '?')}"
            )
        bug_report = "\n".join(bug_descriptions)

        # Implementer: fix bugs
        fix_result = await auto.task(
            f"Round {round_num}: Fix these bugs found by the reviewer. "
            "Read each file, understand the context, and make the fix. "
            "Run the existing tests after fixing to make sure nothing is broken: "
            "cd /home/tianhao/auto && python -m pytest tests/ -x -q\n\n"
            f"Bugs to fix:\n{bug_report}\n\n"
            "For each bug, either fix it or explain why it's not actually a bug. "
            "Do NOT make unnecessary changes beyond the bugs listed.",
            to="implementer",
            schema={
                "fixed": "int",
                "skipped": "int",
                "details": "list of {bug: str, action: str, reason: str}",
                "tests_pass": "bool"
            }
        )

        fixed = fix_result.get("fixed", 0)
        skipped = fix_result.get("skipped", 0)
        tests_pass = fix_result.get("tests_pass", False)

        # Report to main session
        await auto.remind(
            f"Round {round_num} complete. "
            f"Reviewer found {bugs_found} bugs. "
            f"Implementer fixed {fixed}, skipped {skipped}. "
            f"Tests pass: {tests_pass}. "
            f"Report this status briefly."
        )
