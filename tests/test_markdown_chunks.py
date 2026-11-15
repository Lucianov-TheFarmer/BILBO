"""Long reports can be rendered a few Markdown sections at a time."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from frontend.procedures.markdown_chunks import split_markdown_report  # noqa: E402


class MarkdownChunksTest(unittest.TestCase):
    def test_preserves_report_and_avoids_large_render_blocks(self):
        report = "# Report\n\n" + "".join(
            "## Cluster {}\n\n{}\n\n".format(index, "text " * 200)
            for index in range(20)
        )
        chunks = split_markdown_report(report, target_chars=2500)
        self.assertEqual(report, "".join(chunks))
        self.assertGreater(len(chunks), 2)
        self.assertTrue(all(len(chunk) <= 2500 for chunk in chunks))

    def test_keeps_fenced_code_together(self):
        report = "# Report\n\n```text\n# not a heading\n\ncode\n```\n\n## Next\n\nDone.\n"
        chunks = split_markdown_report(report, target_chars=35)
        self.assertEqual(report, "".join(chunks))
        self.assertTrue(any("```text\n# not a heading\n\ncode\n```" in chunk for chunk in chunks))


if __name__ == "__main__":
    unittest.main()
