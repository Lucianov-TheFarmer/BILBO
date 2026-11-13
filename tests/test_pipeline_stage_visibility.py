"""Scheduled trimming outputs remain visible before files finish writing."""

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from backend.db.database import Base  # noqa: E402
from backend.db.models import PipelineRun, PipelineStep, SampleStage, Stage, User  # noqa: E402
from backend.routes.samples import get_samples_by_stage  # noqa: E402


class PipelineStageVisibilityTest(unittest.TestCase):
    def test_running_pair_is_listed_without_completed_files(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine)()
        user = User(id=7, username="stage-test", hashed_password="test")
        db.add_all([user, Stage(id=3, name="trimming"),
                    PipelineRun(id="run", user_id=7, status="RUNNING",
                                config={"samples": [{"name": "A1", "paired": True}]}),
                    PipelineStep(id="step", run_id="run", sample="A1",
                                 stage="trimming", status="RUNNING")])
        db.commit()
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "7" / "trimmed" / "A1_1_trimmed.fastq.gz"
            output.parent.mkdir(parents=True)
            output.write_bytes(b"x" * 1024)
            with patch("backend.routes.samples.settings", SimpleNamespace(users_root=root)):
                rows = get_samples_by_stage(3, db=db, current_user=user)
            self.assertEqual({"A1_1_trimmed.fastq.gz", "A1_2_trimmed.fastq.gz"},
                             {row["name"] for row in rows})
            self.assertEqual({"RUNNING"}, {row["status"] for row in rows})
            self.assertIsNotNone(next(row["size"] for row in rows if row["name"].startswith("A1_1")))

            db.add(SampleStage(user_id=7, stage_id=3, name="A1_1_trimmed.fastq.gz",
                               sra_code="A1", status="COMPLETED", size="1 MB"))
            db.commit()
            with patch("backend.routes.samples.settings", SimpleNamespace(users_root=root)):
                rows = get_samples_by_stage(3, db=db, current_user=user)
            self.assertEqual(2, len(rows))
            self.assertEqual("COMPLETED", next(row["status"] for row in rows
                                               if row["name"] == "A1_1_trimmed.fastq.gz"))
        db.close()
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
