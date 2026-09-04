"""Non-gating enqueue p99 measurement: run against an already configured project."""

import argparse
import asyncio
import statistics
import time
import uuid

import httpx


async def run(base_url: str, project_id: str, token: str, requests: int) -> None:
    url = f"{base_url.rstrip('/')}/v1/projects/{project_id}/queues/load/jobs"
    headers = {"Authorization": f"Bearer {token}"}
    timings: list[float] = []
    async with httpx.AsyncClient(timeout=30) as client:
        for _ in range(requests):
            started = time.perf_counter()
            response = await client.post(
                url,
                headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
                json={"handler": "load.noop", "payload": {"value": 1}},
            )
            response.raise_for_status()
            timings.append((time.perf_counter() - started) * 1000)
    p99 = statistics.quantiles(timings, n=100, method="inclusive")[98]
    print(f"requests={requests} p99_ms={p99:.2f} target_ms=25.00")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--requests", type=int, default=500)
    args = parser.parse_args()
    asyncio.run(run(args.base_url, args.project_id, args.token, args.requests))


if __name__ == "__main__":
    main()
