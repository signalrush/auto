# auto

A single primitive for self-controlling agents: `step()`.

You write a Python program. Each `step()` is a turn in the model's own session — context accumulates, the model remembers everything. Python controls the flow. The model does the work.

## Install

```bash
npx skills add signalrush/auto
```

Works with Claude Code, Codex, Cursor, OpenCode, Windsurf, and 40+ other agents.

### Manual setup

```bash
pip install auto-agent
```

Requires Python 3.10+ and [OpenCode](https://github.com/opencode-ai/opencode) (`opencode serve`).

## Quick Start

Write a program:

```python
# program.py

async def main(step):
    result = await step("What files are in the current directory?")
    print(result)
```

Run it:

```bash
auto-run program.py
```

## How it works

```
opencode serve --port 54321
       │
       ├── TUI (opencode attach) — you watch
       │
       └── auto-run program.py — feeds steps into the same session
```

Each `step()` is a turn in the model's own session. The model remembers all previous steps. Python handles loops, branching, and state.

## Structured Output

Use `schema` when Python needs to make decisions:

```python
async def main(step):
    result = await step(
        "Run train.py and report the validation loss",
        schema={"val_loss": "float"}
    )
    if result["val_loss"] < 0.5:
        await step("Good enough. Stop experimenting.")
    else:
        await step("Try a higher learning rate.")
```

## Example: Autoresearch

```python
async def main(step):
    baseline = await step("Run train.py, report val_loss", schema={"val_loss": "float"})
    best = baseline["val_loss"]

    for i in range(20):
        result = await step(
            f"Experiment {i+1}: beat val_loss={best}. Edit, commit, run, report.",
            schema={"val_loss": "float", "description": "str"}
        )
        if result["val_loss"] < best:
            best = result["val_loss"]
        else:
            await step("Revert: git reset --hard HEAD~1")

        if (i + 1) % 5 == 0:
            await step("Reflect: what's working? Adjust strategy.")
```

See [`examples/autoresearch.py`](examples/autoresearch.py) for the full version.

## Monitor & Steer

```bash
auto-run status    # process status + state
auto-run log       # tail live output
auto-run stop      # kill it
```

Steer by killing, editing `program.py`, and restarting. State persists in `auto-state.json`.

## Key Insight

`step()` is NOT a sub-agent. It's the model continuing to work in its own session. The Python program is just control flow around the model's own actions. Every agent architecture pattern (ReAct, experiment loops, task trees) is a special case of `step()` + Python.

## Docs

- [Quickstart](docs/quickstart.md)
- [API Reference](docs/api.md)
- [Design](docs/design.md)

## License

MIT
