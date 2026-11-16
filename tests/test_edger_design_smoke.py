"""Run edgeR on tiny synthetic counts with group and block metadata."""

import random
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


class EdgeRDesignSmokeTest(unittest.TestCase):
    def test_block_model_produces_group_contrast(self):
        rscript = shutil.which("Rscript")
        if not rscript:
            self.skipTest("Rscript is not installed")
        script = Path(__file__).resolve().parents[1] / "app" / "backend" / "scripts" / "DEG.R"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            preprocess = root / "preprocess"
            output = root / "DEG"
            preprocess.mkdir()
            output.mkdir()
            random.seed(23)
            lines = ["files\tgroup\tdescription"]
            metadata = ["sample\tbloco"]
            for block in (2, 3, 4):
                for group, prefix in (("Controle", "C"), ("Seca", "D")):
                    sample = f"{prefix}{block}"
                    counts = root / f"{sample}.txt"
                    counts.write_text("\n".join(
                        f"gene_{index}\t{max(1, random.randint(20, 100) + (15 if prefix == 'D' and index < 15 else 0))}"
                        for index in range(100)) + "\n", encoding="utf-8")
                    lines.append(f"{counts}\t{group}\t{sample}")
                    metadata.append(f"{sample}\t{block}")
            (preprocess / "Targets.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
            (preprocess / "design_variables.tsv").write_text("\n".join(metadata) + "\n", encoding="utf-8")
            (preprocess / "design_terms.tsv").write_text("name\tkind\nbloco\tcategorical\n", encoding="utf-8")
            (preprocess / "selected_contrasts.txt").write_text("1\n", encoding="utf-8")
            (preprocess / "contrasts_db.txt").write_text(
                "id\tname\n1\tSeca(D2;D3;D4)*Controle(C2;C3;C4)\n", encoding="utf-8")
            result = subprocess.run([rscript, str(script), str(preprocess), str(output)],
                                    capture_output=True, text=True, timeout=120)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr +
                             (preprocess / "DEG_R.log").read_text(encoding="utf-8", errors="replace"))
            self.assertTrue((output / "DEG.xlsx").is_file())
            self.assertTrue((output / "DEG_full.xlsx").is_file())
            self.assertIn("Design formula: ~0+group+bloco",
                          (preprocess / "DEG_R.log").read_text(encoding="utf-8", errors="replace"))


if __name__ == "__main__":
    unittest.main()
