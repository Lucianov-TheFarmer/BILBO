"""Active manual jobs reappear when the user opens a new session."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from frontend.procedures.jobs import recover_active_jobs  # noqa: E402


class _Response:
    status_code = 200

    def __init__(self, value):
        self.value = value

    def raise_for_status(self):
        pass

    def json(self):
        return self.value


class _Client:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def get(self, url, **_kwargs):
        if url.endswith("/pipeline/runs"):
            return _Response([{"status": "RUNNING", "steps": [{"job_id": "pipeline-job"}]}])
        if url.endswith("status=PENDING"):
            return _Response([])
        if url.endswith("status=RUNNING"):
            return _Response([
                {"job_id": "alignment-job", "stage": "alignment"},
                {"job_id": "pipeline-job", "stage": "alignment"},
            ])
        if url.endswith("/jobs/alignment-job"):
            return _Response({"payload": {"sample": "B02-F_S6"}})
        raise AssertionError(url)


class JobRecoveryTest(unittest.IsolatedAsyncioTestCase):
    async def test_running_manual_alignment_is_restored_but_pipeline_job_is_not(self):
        started = []
        page = SimpleNamespace(session={"lang": "pt"},
                               run_task=lambda *args: started.append(args))

        async def refresh():
            pass

        with patch("frontend.procedures.jobs.httpx.AsyncClient", return_value=_Client()):
            await recover_active_jobs(page, "token", refresh)
        self.assertEqual(1, len(started))
        self.assertEqual("alignment-job", started[0][1])
        self.assertIn("B02-F_S6", started[0][2])


if __name__ == "__main__":
    unittest.main()
