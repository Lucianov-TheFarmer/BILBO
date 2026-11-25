"""Growing analysis outputs provide activity without estimating completion."""

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite://")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from backend.routes import jobs


class OutputProgressTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.users = Path(self.temp.name) / "users"
        real_path = Path
        self.path_patch = patch.object(
            jobs, "Path", side_effect=lambda value: self.users if value == "/users" else real_path(value))
        self.path_patch.start()
        self.addCleanup(self.path_patch.stop)

    def job(self, stage="trimming", sample="A", started_at=None):
        return SimpleNamespace(
            status="RUNNING", stage=stage, user_id=1,
            payload={"sample": sample, "sra_code": sample},
            started_at=started_at or datetime.now(timezone.utc) - timedelta(minutes=1),
        )

    def test_paired_trimmed_outputs_are_summed(self):
        folder = self.users / "1" / "trimmed"
        folder.mkdir(parents=True)
        (folder / "A_1_trimmed.fastq.gz").write_bytes(b"x" * 128)
        (folder / "A_2_trimmed.fastq.gz").write_bytes(b"x" * 64)
        result = jobs._active_output_progress(self.job())
        self.assertEqual(192, result["output_bytes"])
        self.assertEqual(2, result["output_file_count"])

    def test_preexisting_output_is_ignored_with_naive_utc_start(self):
        folder = self.users / "1" / "trimmed"
        folder.mkdir(parents=True)
        path = folder / "A_1_trimmed.fastq.gz"
        path.write_bytes(b"old")
        old = datetime.now(timezone.utc) - timedelta(hours=1)
        os.utime(path, (old.timestamp(), old.timestamp()))
        start = (datetime.now(timezone.utc) - timedelta(minutes=1)).replace(tzinfo=None)
        self.assertIsNone(jobs._active_output_progress(self.job(started_at=start)))

    def test_download_and_alignment_outputs_are_visible(self):
        for stage, directory, filename in (
            ("samples_download", "samples/A", "A_1.fastq"),
            ("alignment", "alignment/A", "AAligned.out.bam"),
        ):
            with self.subTest(stage=stage):
                folder = self.users / "1" / directory
                folder.mkdir(parents=True, exist_ok=True)
                (folder / filename).write_bytes(b"x" * 32)
                self.assertEqual(32, jobs._active_output_progress(self.job(stage))["output_bytes"])


if __name__ == "__main__":
    unittest.main()
