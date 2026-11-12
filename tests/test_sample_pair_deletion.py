"""Deleting either read removes its logical sample exactly once."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite://")
sys.path.insert(0, os.environ.get("BILBO_APP_ROOT", str(Path(__file__).resolve().parents[1] / "app")))

from backend.db.database import Base  # noqa: E402
from backend.db.models import SampleStage, Stage, User  # noqa: E402
from backend.routes.samples import delete_sample  # noqa: E402


class SamplePairDeletionTest(unittest.TestCase):
    def test_one_selected_read_removes_both_records_and_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = create_engine("sqlite://")
            Base.metadata.create_all(engine)
            with Session(engine) as db, patch("backend.routes.samples.settings", SimpleNamespace(users_root=tmp)):
                user = User(id=3, username="researcher", hashed_password="unused")
                db.add_all([user, Stage(id=1, name="samples")])
                for mate in (1, 2):
                    db.add(SampleStage(
                        stage_id=1, user_id=3, sra_code="PUS_S54",
                        name=f"PUS_S54_{mate}.fastq.gz", size="1 GB", status="COMPLETED",
                    ))
                db.add(SampleStage(
                    stage_id=1, user_id=3, sra_code="other",
                    name="other_1.fastq.gz", size="1 GB", status="COMPLETED",
                ))
                db.commit()
                sample_dir = Path(tmp) / "3" / "samples" / "PUS_S54"
                sample_dir.mkdir(parents=True)
                for mate in (1, 2):
                    (sample_dir / f"PUS_S54_{mate}.fastq.gz").write_bytes(b"fastq")

                result = delete_sample("PUS_S54_1.fastq.gz", db=db, current_user=user)

                self.assertEqual(result["sra_code"], "PUS_S54")
                self.assertEqual(set(result["deleted_names"]), {"PUS_S54_1.fastq.gz", "PUS_S54_2.fastq.gz"})
                self.assertEqual(db.query(SampleStage).filter_by(sra_code="PUS_S54").count(), 0)
                self.assertEqual(db.query(SampleStage).filter_by(sra_code="other").count(), 1)
                self.assertFalse(sample_dir.exists())


if __name__ == "__main__":
    unittest.main()
