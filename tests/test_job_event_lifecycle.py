"""A job's successful or failed state must retain a readable event timeline."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from backend.db.database import Base  # noqa: E402
from backend.db.models import User  # noqa: E402
from backend.schemas.common import PipelineStatus  # noqa: E402
from backend.services import job_service  # noqa: E402


class JobEventLifecycleTest(unittest.TestCase):
    def test_failed_job_keeps_start_duration_and_reason(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        session = sessionmaker(bind=engine)()
        self.addCleanup(engine.dispose)
        self.addCleanup(session.close)
        session.add(User(id=7, username="test-user", hashed_password="unused"))
        session.commit()
        with tempfile.TemporaryDirectory() as users_root:
            with patch.object(job_service, "settings", SimpleNamespace(users_root=users_root)):
                job = job_service.create_job(session, "quality_analysis", 7, {"samples": ["S1_1.fastq.gz"]})
                job_service.set_job_running(session, job.id)
                job_service.set_job_finished(session, job.id, PipelineStatus.FAILED,
                                             error_message="FastQC exited with code 7: malformed FASTQ")
                events = (Path(users_root) / "7" / "logs" / "jobs" /
                          f"{job.id}.progress.log").read_text(encoding="utf-8")
        self.assertIn("na fila", events)
        self.assertIn("iniciado", events)
        self.assertIn("FAILED após", events)
        self.assertIn("malformed FASTQ", events)


if __name__ == "__main__":
    unittest.main()
