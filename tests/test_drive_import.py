"""Drive import must identify read pairs without merging unrelated samples."""

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite://")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from backend.services.drive_service import parse_fastq_pair  # noqa: E402


class DrivePairNamesTest(unittest.TestCase):
    def test_paired_illumina_names(self):
        self.assertEqual(parse_fastq_pair("A01-F_S2_R1_001.fastq.gz"), ("A01-F_S2", 1))
        self.assertEqual(parse_fastq_pair("A01-F_S2_R2_001.fastq.gz"), ("A01-F_S2", 2))

    def test_lane_remains_in_sample_key(self):
        self.assertEqual(parse_fastq_pair("A01-F_S2_L001_R1_001.fastq.gz"), ("A01-F_S2_L001", 1))

    def test_simple_pair(self):
        self.assertEqual(parse_fastq_pair("sample_2.fq.gz"), ("sample", 2))

    def test_invalid_names(self):
        for name in ("../outside_R1_001.fastq.gz", "sample.fastq.gz", "sample_R1_001.fastq", "sample_R3_001.fastq.gz"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                parse_fastq_pair(name)


if __name__ == "__main__":
    unittest.main()
