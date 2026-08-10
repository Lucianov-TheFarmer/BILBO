import unittest

import app.backend.pipeline_rag.literature as literature_entities


class LiteratureEntitiesTest(unittest.TestCase):
    def test_unique_mentions_normalizes_and_deduplicates(self) -> None:
        mentions = literature_entities.unique_mentions([" PIF3 ", "pif3", "(Arabidopsis thaliana)", ""])

        self.assertEqual(["PIF3", "Arabidopsis thaliana"], mentions)

    def test_span_patterns_use_expected_labels(self) -> None:
        patterns = literature_entities.make_span_patterns(
            species_terms=["Arabidopsis thaliana"],
            protein_family_terms=["potassium channel"],
            go_terms=["xyloglucan biosynthetic process"],
        )

        self.assertEqual(
            [
                {"label": "SPECIES", "pattern": "Arabidopsis thaliana"},
                {"label": "PROTEIN_FAMILY", "pattern": "potassium channel"},
                {"label": "GO_TERM", "pattern": "xyloglucan biosynthetic process"},
            ],
            patterns,
        )


if __name__ == "__main__":
    unittest.main()
