"""Check model estimability and prerequisite-based sample scheduling."""

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
from backend.db.models import PipelineJob, PipelineRun, PipelineStep, SampleStage, Stage, User  # noqa: E402
from backend.services.analysis_design import validate_design  # noqa: E402
from backend.tasks.orchestrator import _advance_run  # noqa: E402
from backend.routes.pipeline_runs import PipelinePlan, SamplePlan, create_run, start_run  # noqa: E402


class PipelineConfigurationTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.db.add(User(id=7, username="pipeline-test", hashed_password="test"))
        self.db.add_all([Stage(id=i, name=f"stage-{i}") for i in range(1, 9)])
        self.db.add(SampleStage(id=80, user_id=7, stage_id=8, status="Contrast",
            name="Seca(D2;D3;D4)*Controle(C2;C3;C4)"))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_block_adjustment_has_two_residual_degrees_of_freedom(self):
        config = {"contrast_ids": [80], "variables": [{
            "name": "bloco", "kind": "categorical",
            "values": {f"{group}{block}": str(block)
                       for group in ("D", "C") for block in (2, 3, 4)},
        }]}
        result = validate_design(self.db, 7, config)
        self.assertEqual("~0+group+bloco", result["formula"])
        self.assertEqual(4, result["rank"])
        self.assertEqual(2, result["residual_df"])
        self.assertEqual("Seca", result["samples"]["D2"])

    def test_confounding_is_rejected(self):
        config = {"contrast_ids": [80], "variables": [{
            "name": "lote", "kind": "categorical",
            "values": {f"{group}{block}": group for group in ("D", "C")
                       for block in (2, 3, 4)},
        }]}
        with self.assertRaisesRegex(ValueError, "not full rank"):
            validate_design(self.db, 7, config)

    def test_draft_can_start_before_samples_finish(self):
        self.db.add(SampleStage(user_id=7, stage_id=7, sra_code="reference-1",
                                name="Reference", status="PENDING"))
        self.db.commit()
        design = {"contrast_ids": [80], "variables": [{
            "name": "bloco", "kind": "categorical",
            "values": {f"{group}{block}": str(block)
                       for group in ("D", "C") for block in (2, 3, 4)},
        }]}
        plan = PipelinePlan(name="Test", samples=[SamplePlan(name=f"{group}{block}", source="drive")
                                                  for group in ("D", "C") for block in (2, 3, 4)],
                            stages={"trimming": True, "alignment": True,
                                    "quantification": True, "deg": True},
                            genome="reference-1", design=design)
        draft = create_run(plan, self.db, self.db.get(User, 7))
        self.assertEqual("DRAFT", draft["status"])
        self.assertEqual(25, len(draft["steps"]))
        started = start_run(draft["id"], self.db, self.db.get(User, 7))
        self.assertEqual("RUNNING", started["status"])
        self.assertEqual("~0+group+bloco", started["config"]["design_snapshot"]["formula"])

    def test_alignment_waits_for_trimmed_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw_dir = root / "7" / "samples" / "D2"
            raw_dir.mkdir(parents=True)
            for mate in (1, 2):
                name = f"D2_{mate}.fastq.gz"
                (raw_dir / name).write_bytes(b"reads")
                self.db.add(SampleStage(user_id=7, stage_id=1, sra_code="D2",
                                        name=name, status="COMPLETED"))
            run = PipelineRun(id="test-run", user_id=7, status="RUNNING", config={
                "samples": [{"name": "D2", "source": "existing", "paired": True}],
                "stages": {"trimming": True, "alignment": True},
                "trimming": {"threads": 2}, "alignment": {"threads": 4},
                "genome": "test-reference",
            })
            self.db.add(run)
            for stage in ("input", "trimming", "alignment"):
                self.db.add(PipelineStep(id=f"step-{stage}", run_id=run.id,
                                         sample="D2", stage=stage, status="WAITING"))
            self.db.commit()
            dispatched = []

            def fake_dispatch(db, _run, step, _paired):
                job = PipelineJob(id=f"job-{step.stage}", user_id=7,
                                  stage=step.stage, status="PENDING", payload={})
                db.add(job)
                db.commit()
                dispatched.append(step.stage)
                return job

            with patch("backend.tasks.orchestrator.settings", SimpleNamespace(users_root=str(root))), \
                 patch("backend.tasks.orchestrator._dispatch", side_effect=fake_dispatch), \
                 patch("backend.tasks.orchestrator._cpu_available", return_value=True), \
                 patch("backend.tasks.orchestrator._reference_ready", return_value=True):
                _advance_run(self.db, run)
                self.assertEqual(["trimming"], dispatched)
                self.assertEqual("SKIPPED", next(s.status for s in run.steps if s.stage == "input"))
                self.assertEqual("WAITING", next(s.status for s in run.steps if s.stage == "alignment"))
                trimmed_dir = root / "7" / "trimmed"
                trimmed_dir.mkdir()
                for mate in (1, 2):
                    name = f"D2_{mate}_trimmed.fastq.gz"
                    (trimmed_dir / name).write_bytes(b"trimmed")
                    self.db.add(SampleStage(user_id=7, stage_id=3, sra_code="D2",
                                            name=name, status="COMPLETED"))
                self.db.query(PipelineJob).filter(PipelineJob.id == "job-trimming").one().status = "COMPLETED"
                self.db.commit()
                _advance_run(self.db, run)
                self.assertEqual(["trimming", "alignment"], dispatched)


if __name__ == "__main__":
    unittest.main()
