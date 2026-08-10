import unittest

import numpy as np
import pandas as pd

from app.backend.scripts import clustering


class ClusteringTest(unittest.TestCase):
    def test_clean_go_annotations_excludes_invalid_terms(self) -> None:
        genes = pd.DataFrame(
            {
                "gene_id": ["valid", "mixed", "invalid", "empty"],
                "Uniprot MF": [
                    "activity [GO:0000001]",
                    "old [GO:9999999]; activity [GO:0000002]",
                    "old [GO:9999999]",
                    "",
                ],
            }
        )

        genes["Uniprot MF"] = clustering.clean_go_annotations(genes["Uniprot MF"], {"GO:9999999"})
        result = clustering.valid_go_gene_ids(genes, "Uniprot MF")

        self.assertEqual({"valid", "mixed"}, result)
        self.assertNotIn("GO:9999999", " ".join(genes["Uniprot MF"]))

    def test_complete_linkage_keeps_only_coherent_groups_of_three(self) -> None:
        genes = pd.DataFrame({"gene_id": ["a", "b", "c", "d", "e"]})
        similarity = np.array(
            [
                [1.0, 0.8, 0.7, 0.1, 0.1],
                [0.8, 1.0, 0.6, 0.1, 0.1],
                [0.7, 0.6, 1.0, 0.1, 0.1],
                [0.1, 0.1, 0.1, 1.0, 0.9],
                [0.1, 0.1, 0.1, 0.9, 1.0],
            ]
        )

        result = clustering.cluster_genes(genes, 1 - similarity, min_similarity=0.6)

        self.assertEqual([1, 1, 1, -1, -1], result["cluster"].tolist())
        self.assertEqual([3.0, 3.0, 3.0], result.loc[:2, "cluster_size"].tolist())
        self.assertEqual("unknown", result.loc[0, "cluster_quality"])

    def test_complete_linkage_rejects_pair_below_similarity_threshold(self) -> None:
        genes = pd.DataFrame({"gene_id": ["a", "b", "c"]})
        similarity = np.array(
            [
                [1.0, 0.8, 0.5],
                [0.8, 1.0, 0.8],
                [0.5, 0.8, 1.0],
            ]
        )

        result = clustering.cluster_genes(genes, 1 - similarity, min_similarity=0.6)

        self.assertEqual([-1, -1, -1], result["cluster"].tolist())

    def test_negative_silhouette_gene_is_pruned(self) -> None:
        labels = np.array([0, 0, 0, 0, 1, 1, 1])
        distance = np.array(
            [
                [0.0, 0.1, 0.1, 0.5, 0.9, 0.9, 0.9],
                [0.1, 0.0, 0.1, 0.5, 0.9, 0.9, 0.9],
                [0.1, 0.1, 0.0, 0.5, 0.9, 0.9, 0.9],
                [0.5, 0.5, 0.5, 0.0, 0.1, 0.1, 0.1],
                [0.9, 0.9, 0.9, 0.1, 0.0, 0.1, 0.1],
                [0.9, 0.9, 0.9, 0.1, 0.1, 0.0, 0.1],
                [0.9, 0.9, 0.9, 0.1, 0.1, 0.1, 0.0],
            ]
        )

        result = clustering.prune_negative_silhouettes(distance, labels)

        self.assertEqual([0, 0, 0, -1, 1, 1, 1], result.tolist())


if __name__ == "__main__":
    unittest.main()
