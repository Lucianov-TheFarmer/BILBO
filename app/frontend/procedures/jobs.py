import asyncio
import httpx


async def wait_for_job(token: str, job_id: str, *, interval: float = 2.0, timeout: float = 7200.0):
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    elapsed = 0.0
    async with httpx.AsyncClient(timeout=60.0) as client:
        while elapsed <= timeout:
            response = await client.get(f"http://localhost:8000/jobs/{job_id}", headers=headers)
            response.raise_for_status()
            payload = response.json()
            status = payload.get("status")
            if status in {"COMPLETED", "FAILED", "CANCELED"}:
                return payload
            await asyncio.sleep(interval)
            elapsed += interval
    raise TimeoutError(f"Job {job_id} did not finish within {timeout} seconds")
