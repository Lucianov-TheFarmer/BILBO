"""Exercise FastQC success, failure, and long-running completion without FastQC."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASH = shutil.which("bash")


def shell_path(path: Path) -> str:
    if os.name != "nt":
        return str(path)
    return subprocess.check_output(
        [BASH, "-c", 'cygpath -u "$1"', "_", str(path)], text=True,
    ).strip()


@unittest.skipUnless(BASH, "Bash is required")
class QualityScriptDiagnosticsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        fastqc = self.bin / "fastqc"
        fastqc.write_text(
            "#!/usr/bin/env bash\n"
            "set -e\n"
            "while [ \"$#\" -gt 0 ]; do\n"
            "  case \"$1\" in -o) out=\"$2\"; shift 2 ;; *) input=\"$1\"; shift ;; esac\n"
            "done\n"
            "case \"$FASTQC_TEST_MODE\" in\n"
            "  slow) echo 'Approx 85% complete for test'; sleep 2; "
            "stem=\"$(basename \"$input\")\"; stem=\"${stem%.gz}\"; "
            "stem=\"${stem%.fastq}\"; "
            "printf 'report' > \"$out/${stem}_fastqc.html\"; "
            "printf 'report' > \"$out/${stem}_fastqc.zip\" ;;\n"
            "  error) echo 'Malformed FASTQ record' >&2; exit 7 ;;\n"
            "  success) stem=\"$(basename \"$input\")\"; stem=\"${stem%.gz}\"; "
            "stem=\"${stem%.fastq}\"; "
            "printf 'report' > \"$out/${stem}_fastqc.html\"; "
            "printf 'report' > \"$out/${stem}_fastqc.zip\" ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        fastqc.chmod(0o755)

    def run_quality(self, mode: str, post_trim: bool = False):
        sample = "S1_1_trimmed.fastq.gz" if post_trim else "S1_1.fastq.gz"
        source = self.root / "users" / "1" / ("trimmed" if post_trim else "samples/S1")
        source.mkdir(parents=True, exist_ok=True)
        (source / sample).write_bytes(b"test")
        env = os.environ.copy()
        env.update({
            "BILBO_TEST_BIN": shell_path(self.bin),
            "BILBO_USERS_ROOT": shell_path(self.root / "users"),
            "FASTQC_TEST_MODE": mode,
        })
        script = ROOT / "app" / "backend" / "scripts" / (
            "quality_analysis_post_trim.sh" if post_trim else "quality_analysis.sh")
        run = subprocess.run([BASH, "-c", 'PATH="$BILBO_TEST_BIN:$PATH" exec bash "$1" "$2" 1',
                              "_", shell_path(script), sample],
                             env=env, capture_output=True, text=True, timeout=15)
        log_dir = self.root / "users" / "1" / ("QC_PostTrim" if post_trim else "QC") / "S1"
        log_name = "S1_1_trimmed_quality_analysis_post_trim.log" if post_trim else f"{sample}_quality_analysis.log"
        return run, (log_dir / log_name).read_text(encoding="utf-8")

    def test_initial_quality_can_continue_after_silent_85_percent(self):
        run, log = self.run_quality("slow")
        self.assertEqual(0, run.returncode)
        self.assertIn("Approx 85%", log)
        self.assertIn("completed successfully", log)

    def test_initial_quality_keeps_fastqc_error(self):
        run, log = self.run_quality("error")
        self.assertEqual(7, run.returncode)
        self.assertIn("Malformed FASTQ record", log)
        self.assertIn("exit code 7", log)

    def test_success_requires_both_reports(self):
        run, log = self.run_quality("success")
        self.assertEqual(0, run.returncode)
        self.assertIn("completed successfully", log)

    def test_post_trim_can_continue_after_silent_85_percent(self):
        run, log = self.run_quality("slow", post_trim=True)
        self.assertEqual(0, run.returncode)
        self.assertIn("Approx 85%", log)
        self.assertIn("completed successfully", log)


if __name__ == "__main__":
    unittest.main()
