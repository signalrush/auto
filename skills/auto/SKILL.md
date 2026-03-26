---
name: auto
description: Run yourself in a loop with branching logic via a Python program. Use for long-running tasks like optimization, research, iterative improvement, or any multi-step workflow where you need to repeat, branch, or track progress across 10+ turns. Triggers on "auto", "run a loop", "autoresearch", "keep improving", or when a program.py with def main(step) exists.
---

# Auto — Run yourself in a loop

A Python program drives your turns. Each `step()` becomes YOUR next turn — you execute it with full tool access. The program controls the loop, branching, and state.

## CRITICAL: How to launch

```bash
auto-run program.py
```

Then say **"go"** as your next message. That's it. The stop hook injects each step automatically after that.

**DO NOT:**
- Use `nohup`, `&`, or redirect output — `auto-run` handles backgrounding
- Run `auto-run log` (it blocks) — use `auto-run status` instead
- Stop the program because you see "Send any message to begin" — just say "go"
- Worry about CLAUDE_CODE_SESSION_ID — it works without it

## Writing a program

```python
# program.py
async def main(step):
    # Each step() is one of YOUR turns — you do the work
    baseline = await step(
        "Run train.py and report val_loss",
        schema={"val_loss": "float"}
    )
    best = baseline["val_loss"]

    for i in range(20):
        result = await step(
            f"Experiment {i+1}: try to beat val_loss={best}. "
            "Edit train.py, commit, run, report.",
            schema={"val_loss": "float", "description": "str"}
        )

        if result["val_loss"] < best:
            best = result["val_loss"]
            await step(f"Good, improved to {best}. Keep it.")
        else:
            await step("Didn't improve. Revert: git reset --hard HEAD~1")

        if (i + 1) % 5 == 0:
            await step("Reflect: what's working? What to try next?")
```

No imports needed beyond the `step` function passed to `main`.

## step() API

```python
result = await step(instruction)              # returns str
result = await step(instruction, schema={})   # returns dict
```

- **instruction** (`str`): What to do. You execute this as a full turn.
- **schema** (`dict`, optional): Forces structured JSON output. Keys are field names, values are type descriptions.

If JSON parsing fails, it retries up to 2 times automatically.

## Monitor and control

```bash
auto-run status    # process state + recent logs (non-blocking)
auto-run stop      # kill the program
```

## State tracking (optional)

```python
from auto import state

async def main(step):
    state.set("status", "running")
    for i in range(100):
        result = await step(f"experiment {i}", schema={"score": "float"})
        state.update({"step": i, "score": result["score"]})
    state.set("status", "done")
```

Progress visible via `auto-run status` or `cat auto-state.json`.

## Patterns

### Optimization loop
```python
async def main(step):
    best = 999
    for i in range(20):
        r = await step(f"Try to beat {best}", schema={"loss": "float"})
        if r["loss"] < best:
            best = r["loss"]
        else:
            await step("Revert")
```

### Error recovery
```python
async def main(step):
    for i in range(20):
        try:
            r = await step(f"Experiment {i}", schema={"loss": "float"})
        except Exception as e:
            await step(f"Failed: {e}. Try a simpler approach.")
```

### Periodic reflection
```python
async def main(step):
    for i in range(100):
        await step(f"Experiment {i}")
        if (i + 1) % 10 == 0:
            await step("Reflect on last 10 experiments. Adjust strategy.")
```

## Key insight

Each `step()` is YOUR full turn — you use all your tools (Bash, Read, Edit, etc.) to execute the instruction. The Python program decides what comes next based on your results. You keep full conversation memory across all steps.
