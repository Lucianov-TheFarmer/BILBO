"""Queued jobs beyond worker capacity must not block ready alignment work."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from backend.db.database import Base  # noqa: E402
from backend.db.models import PipelineJob, User  # noqa: E402
from backend.tasks.orchestrator import _cpu_available  # noqa: E402


class PipelineCpuReservationTest(unittest.TestCase):
    def test_only_jobs_that_can_enter_worker_slots_reserve_cpus(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine)()
        db.add(User(id=7, username="cpu-test", hashed_password="test"))
        for index in range(4):
            db.add(PipelineJob(id=f"trim-{index}", user_id=7, stage="trimming",
                               status="RUNNING" if index < 2 else "PENDING",
                               payload={"params": {"threads": 64}}))
        db.commit()
        with patch("backend.tasks.orchestrator.os.cpu_count", return_value=256):
            self.assertTrue(_cpu_available(db, 64))
            for index in range(2):
                db.add(PipelineJob(id=f"align-{index}", user_id=7, stage="alignment",
                                   status="PENDING", payload={"threads": 64}))
            db.commit()
            self.assertFalse(_cpu_available(db, 64))
            db.query(PipelineJob).filter(PipelineJob.stage == "alignment").delete()
            db.add(PipelineJob(id="deg-1", user_id=7, stage="deg",
                               status="RUNNING", payload={"diamond_threads": 120}))
            db.commit()
            self.assertFalse(_cpu_available(db, 16))
        db.close()
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
