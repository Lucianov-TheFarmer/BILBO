"""Automatic DEG runs expose their own R progress log."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from backend.utils_paths import deg_r_progress_path  # noqa: E402


class DEGProgressPathTest(unittest.TestCase):
    def test_pipeline_uses_run_specific_log(self):
        root = Path("/users/3")
        self.assertEqual(root / "pipelines" / "run123" / "preprocess" / "DEG_R.log",
                         deg_r_progress_path(root, {"run_id": "run123"}))

    def test_manual_analysis_uses_original_log(self):
        root = Path("/users/3")
        self.assertEqual(root / "preprocess" / "DEG_R.log",
                         deg_r_progress_path(root, {}))


if __name__ == "__main__":
    unittest.main()
