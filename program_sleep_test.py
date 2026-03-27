"""Test program: sleep 10s between reminds, 4 iterations."""
import asyncio

async def main(auto):
    for i in range(4):
        print(f"Sleeping 10s before remind {i+1}/4...")
        await asyncio.sleep(10)
        answer = await auto.remind(f"Say hello #{i+1}. Reply with just 'hello {i+1}'.")
        print(f"Got: {answer}")
    print("Done!")
