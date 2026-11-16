"""Keep RAG evidence citations legible when indexed PDF metadata is noisy."""

import unittest

from app.backend.scripts.generate_rag_html import _rag_evidence_table


class RagReportMetadataTest(unittest.TestCase):
    def test_doi_link_and_clean_section(self) -> None:
        table = _rag_evidence_table([{
            "citation_id": "R1",
            "source": "10.1105_2Ftpc.18.00693.md",
            "section": "1 **INTRODUCTION**",
            "article_title": "**RESEARCH ARTICLE**",
        }])
        self.assertIn("https://doi.org/10.1105/tpc.18.00693", table)
        self.assertIn("<td>INTRODUCTION</td>", table)
        self.assertIn("Title unavailable in indexed article", table)
        self.assertNotIn("RESEARCH ARTICLE", table)

    def test_valid_title_is_readable_and_escaped(self) -> None:
        table = _rag_evidence_table([{
            "source": "10.1000_2Fexample.md",
            "section": "*Cell Wall Modifications*",
            "article_title": "A [paper](https://example.org) about <i>roots</i> & drought",
        }])
        self.assertIn("<td>Cell Wall Modifications</td>", table)
        self.assertIn("A paper about roots &amp; drought", table)
        self.assertNotIn("https://example.org", table)

    def test_spaced_pdf_header_is_not_presented_as_a_title(self) -> None:
        table = _rag_evidence_table([{
            "source": "10.1000_2Fexample.md",
            "article_title": "R E S EAR CH A R TIC L E Open Access",
        }])
        self.assertIn("Title unavailable in indexed article", table)


if __name__ == "__main__":
    unittest.main()
