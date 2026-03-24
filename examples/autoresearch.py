"""Autoresearch: autonomous experiment loop using loom.

Requires a running OpenCode server (`opencode serve`) and a train.py
in the working directory.
"""

import asyncio
from loom import StepRuntime


async def main():
    rt = StepRuntime(server_url="http://localhost:54321", cwd=".")

    # Baseline
    baseline = await rt.step(
        "Run `uv run train.py > run.log 2>&1`, then `grep '^val_bpb:' run.log`. Report the val_bpb.",
        schema={"val_bpb": "float"},
    )
    best = baseline["val_bpb"]

    count = 0
    while True:
        count += 1
        result = await rt.step(
            "Propose one experiment. Edit train.py, git commit, run it, report results.",
            context={"best_so_far": best, "experiment_number": count},
            schema={"val_bpb": "float", "description": "str", "status": "str"},
        )

        if result["val_bpb"] < best:
            best = result["val_bpb"]
            await rt.step(
                f"Log keep to results.tsv: {result['description']}, val_bpb={result['val_bpb']}"
            )
        else:
            await rt.step(
                f"Log discard to results.tsv: {result['description']}. Git reset to previous commit."
            )

        if count % 10 == 0:
            await rt.step(
                "Read results.tsv. Reflect on what directions are working. Adjust strategy for next experiments."
            )


if __name__ == "__main__":
    asyncio.run(main())
