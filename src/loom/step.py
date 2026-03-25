"""Loom: the step() primitive.

The model writes a program with def main(step). loom-run executes it,
injecting step() which sends each instruction into the model's own session.

    async def main(step):
        result = await step("run train.py, report loss")
        await step(f"loss was {result}, try to improve it")

step(instruction) -> str
step(instruction, schema={...}) -> dict
"""

import json
import re
import os
import subprocess


def _extract_json(text):
    """Extract JSON object from model response, handling markdown fences and surrounding text."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1).strip())
        except json.JSONDecodeError:
            pass

    for start_char, end_char in [('{', '}'), ('[', ']')]:
        start = text.find(start_char)
        if start == -1:
            continue
        depth = 0
        for i in range(start, len(text)):
            if text[i] == start_char:
                depth += 1
            elif text[i] == end_char:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break

    raise ValueError(f"Could not extract valid JSON from response: {text[:200]}")


def _get_latest_session_id():
    """Get the most recent session ID from opencode CLI."""
    result = subprocess.run(
        ["opencode", "session", "list"],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to list sessions: {result.stderr}")

    # Parse the table output — session IDs start with "ses_"
    for line in result.stdout.strip().split("\n"):
        line = line.strip()
        if line.startswith("ses_"):
            return line.split()[0]

    raise RuntimeError("No existing sessions found. Start opencode first.")


async def run_program(program_fn, server_url=None, cwd=None, session_id=None,
                      model=None, provider_id=None, permission_mode="auto"):
    """Execute a loom program.

    The program_fn receives a step() function that sends instructions
    into a persistent session. Context accumulates across steps — the model
    remembers everything from previous steps.

    Uses the opencode-agent-sdk to attach to the existing session. All steps
    run in the SAME session visible in the TUI.

    Args:
        program_fn: An async function that takes step as its argument.
        server_url: Unused (kept for backwards compat). SDK uses subprocess mode.
        cwd: Working directory for the agent. Defaults to current dir.
        session_id: Session ID to use. If not set, checks LOOM_SESSION_ID env var.
                    If neither is set, uses the most recent session.
        model: Model to use (e.g. "claude-haiku-4-5"). Defaults to LOOM_MODEL env.
        provider_id: Provider ID (e.g. "anthropic"). Defaults to LOOM_PROVIDER env.
        permission_mode: Permission mode for tool use. Defaults to "auto".
    """
    from opencode_agent_sdk import SDKClient, AgentOptions

    session_id = session_id or os.environ.get("LOOM_SESSION_ID")
    if not session_id:
        session_id = _get_latest_session_id()

    model = model or os.environ.get("LOOM_MODEL", "")
    provider_id = provider_id or os.environ.get("LOOM_PROVIDER", "anthropic")
    cwd = cwd or os.getcwd()

    print(f"[loom] Attaching to session: {session_id}")

    options = AgentOptions(
        cwd=cwd,
        model=model,
        provider_id=provider_id,
        permission_mode=permission_mode,
        resume=session_id,
    )

    client = SDKClient(options=options)
    await client.connect()

    try:
        async def step(instruction, schema=None):
            """Send an instruction to the model and get the result.

            Args:
                instruction: What to do. Natural language.
                schema: If provided, returns structured JSON output.

            Returns:
                str (default) or dict (if schema provided).
            """
            prompt = instruction
            if schema is not None:
                schema_desc = json.dumps(schema, indent=2)
                prompt += (
                    f"\n\nRespond with ONLY a JSON object. The keys and their expected types are:\n"
                    f"{schema_desc}\n\n"
                    f"Replace the type descriptions with actual values. "
                    f"For example, if the schema is {{\"name\": \"str\", \"age\": \"int\"}}, "
                    f"you would return {{\"name\": \"Alice\", \"age\": 30}}.\n"
                    f"Return ONLY the JSON object, no other text."
                )

            await client.query(prompt)

            # Collect the full response
            result_text = ""
            async for msg in client.receive_response():
                if hasattr(msg, 'content'):
                    for block in msg.content:
                        if hasattr(block, 'text'):
                            result_text = block.text
                # ResultMessage signals end of turn
                if hasattr(msg, 'session_id') and hasattr(msg, 'is_error'):
                    break

            if schema is not None:
                return _extract_json(result_text)
            return result_text

        await program_fn(step)
    finally:
        await client.disconnect()
