"""Cancellation stops jobs and removes only the selected incomplete outputs."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite://")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException

from backend.db.database import Base
from backend.db.models import PipelineJob, SampleStage, Stage, User
from backend.schemas.common import PipelineStatus
from backend.services import job_cancellation
from backend.services.job_service import set_job_finished
from backend.tasks import pipeline_tasks
from backend.routes import quality_analysis, quality_analysis_post_trim


class JobCancellationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "users"
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)
        self.db.add(User(id=5, username="cancel-test", hashed_password="test"))
        self.db.add_all(Stage(id=number, name=f"stage-{number}") for number in (1, 2, 3, 4))
        self.db.commit()
        settings_patch = patch.object(job_cancellation, "settings",
                                      SimpleNamespace(users_root=str(self.root)))
        event_patch = patch("backend.services.job_service.settings",
                            SimpleNamespace(users_root=str(self.root)))
        revoke_patch = patch.object(job_cancellation.celery_app.control, "revoke")
        for active_patch in (settings_patch, event_patch, revoke_patch):
            active_patch.start()
            self.addCleanup(active_patch.stop)

    def test_cancel_trim_removes_pair_but_not_another_sample(self):
        job = PipelineJob(id="job-a", user_id=5, stage="trimming", status="PENDING",
                          payload={"sample": "A", "params": {}})
        self.db.add(job)
        folder = self.root / "5" / "trimmed"
        folder.mkdir(parents=True)
        for name in ("A_1_trimmed.fastq.gz", "A_2_trimmed.fastq.gz", "B_1_trimmed.fastq.gz"):
            (folder / name).write_bytes(b"partial")
            self.db.add(SampleStage(user_id=5, stage_id=3, sra_code=name[0], name=name,
                                    status="PENDING"))
        self.db.commit()

        self.assertTrue(job_cancellation.cancel_jobs_for_output(
            self.db, 5, "trimming", "A_1_trimmed.fastq.gz"))
        self.assertEqual("CANCELED", job.status)
        self.assertFalse((folder / "A_1_trimmed.fastq.gz").exists())
        self.assertFalse((folder / "A_2_trimmed.fastq.gz").exists())
        self.assertTrue((folder / "B_1_trimmed.fastq.gz").exists())
        self.assertEqual(1, self.db.query(SampleStage).filter_by(user_id=5, stage_id=3).count())
        self.assertIn("cancelamento concluído", (self.root / "5" / "logs" / "jobs" /
                  "job-a.progress.log").read_text(encoding="utf-8"))

        set_job_finished(self.db, "job-a", PipelineStatus.COMPLETED)
        self.assertEqual("CANCELED", job.status)

    def test_quality_waits_for_completed_input_rows(self):
        raw = self.root / "5" / "samples" / "A"
        raw.mkdir(parents=True)
        (raw / "A_1.fastq.gz").write_bytes(b"reads")
        self.db.add(SampleStage(user_id=5, stage_id=1, sra_code="A",
                                name="A_1.fastq.gz", status="RUNNING"))
        self.db.commit()
        with patch.object(quality_analysis, "settings", SimpleNamespace(users_root=str(self.root))):
            with self.assertRaises(HTTPException) as error:
                quality_analysis.start_quality_analysis(
                    quality_analysis.QualityAnalysisRequest(samples=["A_1.fastq.gz"]),
                    self.db, self.db.get(User, 5))
        self.assertEqual(409, error.exception.status_code)
        self.assertEqual(0, self.db.query(PipelineJob).count())

    def test_post_trim_quality_waits_for_completed_trim(self):
        trimmed = self.root / "5" / "trimmed"
        trimmed.mkdir(parents=True)
        (trimmed / "A_1_trimmed.fastq.gz").write_bytes(b"reads")
        self.db.add(SampleStage(user_id=5, stage_id=3, sra_code="A",
                                name="A_1_trimmed.fastq.gz", status="RUNNING"))
        self.db.commit()
        with patch.object(quality_analysis_post_trim, "settings",
                          SimpleNamespace(users_root=str(self.root))):
            with self.assertRaises(HTTPException) as error:
                quality_analysis_post_trim.start_quality_analysis_post_trim(
                    quality_analysis_post_trim.QualityAnalysisPostTrimRequest(
                        samples=["A_1_trimmed.fastq.gz"]), self.db, self.db.get(User, 5))
        self.assertEqual(409, error.exception.status_code)
        self.assertEqual(0, self.db.query(PipelineJob).count())

    @unittest.skipUnless(os.name == "posix", "Process groups require POSIX")
    def test_worker_terminates_its_subprocess_after_cancel(self):
        class CanceledSession:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def query(self, *_args):
                return self

            def filter(self, *_args):
                return self

            def first(self):
                return SimpleNamespace(status="CANCELED")

        with patch.object(pipeline_tasks, "SessionLocal", return_value=CanceledSession()), \
             patch.object(pipeline_tasks, "settings", SimpleNamespace(users_root=str(self.root))), \
             patch.dict(pipeline_tasks._PROGRESS_CONTEXT,
                        {"job_id": "stop-test", "user_id": 5, "stage": "trimming"}):
            with self.assertRaises(pipeline_tasks.JobCanceled):
                pipeline_tasks._run(["bash", "-c", "sleep 30"])
        self.assertFalse((self.root / "5" / "logs" / "jobs" / "stop-test.progress.pid").exists())


if __name__ == "__main__":
    unittest.main()
