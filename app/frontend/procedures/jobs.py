import asyncio
import inspect
from typing import Optional
import httpx


async def wait_for_job(
    token: str,
    job_id: str,
    *,
    interval: float = 2.0,
    timeout: Optional[float] = 7200.0,
    on_update=None,
):
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    elapsed = 0.0
    async with httpx.AsyncClient(timeout=60.0) as client:
        # BILBO_OPTIONAL_JOB_TIMEOUT
        while timeout is None or elapsed <= timeout:
            response = await client.get(f"http://localhost:8890/jobs/{job_id}", headers=headers)
            response.raise_for_status()
            payload = response.json()

            if on_update is not None:
                try:
                    maybe_result = on_update(payload)
                    if inspect.isawaitable(maybe_result):
                        await maybe_result
                except Exception:
                    pass

            status = payload.get("status")
            if status in {"COMPLETED", "FAILED", "CANCELED"}:
                return payload
            await asyncio.sleep(interval)
            elapsed += interval
    raise TimeoutError(f"Job {job_id} did not finish within {timeout} seconds")
