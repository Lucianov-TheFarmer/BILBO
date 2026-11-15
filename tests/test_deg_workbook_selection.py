"""The stage view finds completed DEG output from pipeline runs."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite://")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from backend.db.database import Base  # noqa: E402
from backend.db.models import PipelineRun, PipelineStep, User  # noqa: E402
from backend.services import deg_workbooks  # noqa: E402


class DEGWorkbookSelectionTest(unittest.TestCase):
    def test_pipeline_result_is_visible_when_manual_workbook_is_absent(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine)()
        db.add(User(id=3, username="test", hashed_password="test"))
        db.add(PipelineRun(id="run123", user_id=3, status="RUNNING", config={"name": "Test"}))
        db.add(PipelineStep(id="step123", run_id="run123", sample="__all__",
                            stage="deg", status="COMPLETED"))
        db.commit()
        with tempfile.TemporaryDirectory() as root:
            workbook = Path(root) / "3" / "pipelines" / "run123" / "DEG" / "DEG.xlsx"
            workbook.parent.mkdir(parents=True)
            workbook.write_bytes(b"result")
            with patch.object(deg_workbooks, "settings", SimpleNamespace(users_root=root)):
                selected, run = deg_workbooks.selected_deg_workbook(db, 3)
            self.assertEqual(workbook, selected)
            self.assertEqual("run123", run.id)
        db.close()
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
