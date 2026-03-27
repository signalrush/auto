"""Test program: delegate tasks to a sub-agent, then remind self."""

async def main(auto):
    auto.agent("worker", cwd="/home/tianhao/auto")

    # Step 1: Remind self to set the stage
    plan = await auto.remind(
        "We're about to test multi-agent orchestration. Just say 'ready'.")
    print(f"Self said: {plan}")

    # Step 2: Delegate a task to the worker agent
    result = await auto.task(
        "What is the capital of France? Reply with just the city name.",
        to="worker")
    print(f"Worker said: {result}")

    # Step 3: Remind self with the worker's answer
    await auto.remind(
        f"The worker agent said the capital of France is: {result}. "
        f"Confirm if that's correct. Reply with just 'correct' or 'wrong'.")

    # Step 4: Delegate another task
    result2 = await auto.task(
        "Write a Python function that returns the sum of two numbers. "
        "Reply with just the code, no explanation.",
        to="worker")
    print(f"Worker wrote: {result2}")

    # Step 5: Remind self to review
    review = await auto.remind(
        f"Review this code from the worker:\n{result2}\n"
        f"Is it correct? Reply with just 'yes' or 'no'.")
    print(f"Review: {review}")

    print("All done!")
