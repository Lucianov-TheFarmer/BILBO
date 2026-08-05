import unittest

import pandas as pd

from app.backend.scripts import prioritize_genes


class PrioritizeGenesTest(unittest.TestCase):
    def test_representative_is_most_central_gene(self) -> None:
        cluster = pd.DataFrame(
            {
                "gene_id": ["a", "b", "c"],
                "log2FoldChange": [1.0, 1.0, 1.0],
                "cluster_silhouette": [0.5, 0.6, 0.4],
            }
        )
        similarity = pd.DataFrame(
            [
                [1.0, 0.9, 0.5],
                [0.9, 1.0, 0.8],
                [0.5, 0.8, 1.0],
            ],
            index=["a", "b", "c"],
            columns=["a", "b", "c"],
        )

        representative = prioritize_genes.representative_for_cluster(cluster, similarity)

        self.assertEqual("b", representative["gene_id"])

    def test_candidates_are_selected_by_multiple_ontologies(self) -> None:
        candidates = pd.DataFrame(
            {
                "gene_id": ["single", "triple", "double"],
                "selected_for_search": [False, True, True],
                "selection_reason": ["single", "multiple", "multiple"],
                "n_ontologies": [1, 3, 2],
                "min_cluster_quality": [1.0, 0.8, 0.9],
                "centrality_score": [1.0, 0.8, 0.9],
                "abs_log2FoldChange": [3.0, 1.0, 2.0],
                "padj": [0.001, 0.01, 0.005],
            }
        ).sort_values(
            [
                "selected_for_search",
                "n_ontologies",
                "min_cluster_quality",
                "centrality_score",
                "abs_log2FoldChange",
                "padj",
                "gene_id",
            ],
            ascending=[False, False, False, False, False, True, True],
        )

        ranked = prioritize_genes.add_rank(candidates.reset_index(drop=True))

        self.assertEqual(["triple", "double", "single"], ranked["gene_id"].tolist())
        self.assertEqual([True, True, False], ranked["selected_for_search"].tolist())
        self.assertEqual(
            ["rank", "selected_for_search", "selection_reason"],
            ranked.columns[:3].tolist(),
        )

    def test_search_query_uses_comma_separated_gene_and_go_terms(self) -> None:
        query = prioritize_genes.search_query(
            "Probable xyloglucan 6-xylosyltransferase 5",
            [
                "root hair elongation",
                "xyloglucan biosynthetic process",
                "xyloglucan metabolic process",
                "extra term",
            ],
        )

        self.assertEqual(
            (
                "Probable xyloglucan 6-xylosyltransferase 5, "
                "root hair elongation, xyloglucan biosynthetic process, "
                "xyloglucan metabolic process"
            ),
            query,
        )


if __name__ == "__main__":
    unittest.main()
