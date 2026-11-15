"""The stage view finds completed DEG output from pipeline runs."""

import asyncio
import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from openpyxl import Workbook

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite://")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from backend.db.database import Base  # noqa: E402
from backend.db.models import PipelineRun, PipelineStep, SampleStage, User  # noqa: E402
from backend.services import deg_workbooks  # noqa: E402
from backend.routes import deg as deg_routes  # noqa: E402
from backend.routes.deg import get_deg_sheets  # noqa: E402
from backend.routes.results import download_deg_bundle  # noqa: E402


class DEGWorkbookSelectionTest(unittest.TestCase):
    def test_deleting_one_run_does_not_remove_another_runs_contrast(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine)()
        user = User(id=3, username="test", hashed_password="test")
        db.add(user)
        for run_id in ("older", "newer"):
            db.add(PipelineRun(id=run_id, user_id=3, status="COMPLETED", config={}))
            db.add(PipelineStep(id=f"step-{run_id}", run_id=run_id, sample="__all__",
                                stage="deg", status="COMPLETED"))
        db.add(SampleStage(user_id=3, stage_id=9, name="Controle_vs_Seca", status="COMPLETED"))
        db.commit()
        with tempfile.TemporaryDirectory() as root:
            for run_id in ("older", "newer"):
                workbook = Path(root) / "users" / "3" / "pipelines" / run_id / "DEG" / "DEG.xlsx"
                workbook.parent.mkdir(parents=True)
                book = Workbook()
                book.active.title = "Controle_vs_Seca"
                book.save(workbook)

            async def payload():
                return {"sheets": ["Controle_vs_Seca"], "run_id": "older"}

            fake_module = Path(root) / "a" / "b" / "c" / "deg.py"
            with patch.object(deg_workbooks, "settings", SimpleNamespace(users_root=Path(root) / "users")), \
                 patch.object(deg_routes, "__file__", str(fake_module)):
                result = asyncio.run(deg_routes.delete_deg_sheets(
                    SimpleNamespace(json=payload), db=db, current_user=user))
            self.assertEqual(["Controle_vs_Seca"], result["deleted_sheets"])
            self.assertFalse((Path(root) / "users" / "3" / "pipelines" / "older" / "DEG" / "DEG.xlsx").exists())
            self.assertTrue((Path(root) / "users" / "3" / "pipelines" / "newer" / "DEG" / "DEG.xlsx").exists())
            self.assertEqual(1, db.query(SampleStage).filter_by(stage_id=9).count())
        db.close()
        engine.dispose()

    def test_previous_runs_remain_listed_after_a_new_analysis(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine)()
        db.add(User(id=3, username="test", hashed_password="test"))
        for index, sheet in enumerate(("Controle_vs_Seca", "Controle_vs_Seca",
                                       "Controle_vs_Seca_sem_blocos")):
            run_id = f"run{index}"
            db.add(PipelineRun(id=run_id, user_id=3, status="COMPLETED",
                               config={"name": run_id}))
            db.add(PipelineStep(id=f"step{index}", run_id=run_id, sample="__all__",
                                stage="deg", status="COMPLETED"))
        db.commit()
        with tempfile.TemporaryDirectory() as root:
            for index, sheet in enumerate(("Controle_vs_Seca", "Controle_vs_Seca",
                                           "Controle_vs_Seca_sem_blocos")):
                workbook = Path(root) / "3" / "pipelines" / f"run{index}" / "DEG" / "DEG.xlsx"
                workbook.parent.mkdir(parents=True)
                book = Workbook()
                book.active.title = sheet
                book.save(workbook)
            with patch.object(deg_workbooks, "settings", SimpleNamespace(users_root=root)):
                retained = deg_workbooks.available_deg_workbooks(db, 3)
                old_workbook, old_run = deg_workbooks.selected_deg_workbook(db, 3, "run0")
                response = asyncio.run(get_deg_sheets(
                    SimpleNamespace(query_params={"all_runs": "true"}),
                    db=db, current_user=db.get(User, 3)))
                bundle = download_deg_bundle(json.dumps([
                    {"sheet": "Controle_vs_Seca", "run_id": "run0"},
                    {"sheet": "Controle_vs_Seca_sem_blocos", "run_id": "run2"},
                ]), db=db, current_user=db.get(User, 3))

                async def bundle_bytes():
                    return b"".join([part async for part in bundle.body_iterator])

                with zipfile.ZipFile(io.BytesIO(asyncio.run(bundle_bytes()))) as archive:
                    self.assertEqual(2, len(archive.namelist()))
            self.assertEqual(3, len(retained))
            self.assertEqual(3, len(response["results"]))
            self.assertEqual(2, len({item["sheet"] for item in response["results"]}))
            self.assertEqual({"run0", "run1", "run2"}, {run.id for _, run in retained})
            self.assertEqual("run0", old_run.id)
            self.assertEqual("run0", old_workbook.parent.parent.name)
        db.close()
        engine.dispose()

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
