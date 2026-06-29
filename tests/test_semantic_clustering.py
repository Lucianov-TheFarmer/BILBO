import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from app.backend.scripts import clustering


class SemanticClusteringTest(unittest.TestCase):
    def test_normalize_table_maps_deg_and_annotation_columns(self) -> None:
        frame = pd.DataFrame(
            {
                "Unnamed: 0": ["gene-a"],
                "logFC": ["1,5"],
                "PValue": ["0.001"],
                "FDR": ["0.01"],
                "Product GFF": ["kinase protein"],
                "BP (C3)": ["response to stimulus [GO:0050896]"],
                "MF (C3)": ["kinase activity [GO:0016301]"],
                "CC (C3)": ["nucleus [GO:0005634]"],
            }
        )

        normalized = clustering.normalize_table(frame)

        self.assertEqual(clustering.CANONICAL_COLUMNS, normalized.columns.tolist())
        self.assertEqual("gene-a", normalized.loc[0, "gene_id"])
        self.assertEqual(1.5, normalized.loc[0, "log2FoldChange"])
        self.assertEqual(0.01, normalized.loc[0, "padj"])
        self.assertEqual("kinase protein", normalized.loc[0, "Uniprot Function"])

    def test_read_input_table_reads_selected_xlsx_sheet(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            input_file = Path(temp_dir) / "DEG.xlsx"
            expected = pd.DataFrame(
                {
                    "Unnamed: 0": ["gene-a"],
                    "logFC": ["1,5"],
                    "PValue": ["0,001"],
                    "FDR": ["0,01"],
                    "Product GFF": ["enzyme, subunit"],
                    "BP (C3)": ["process [GO:0008150]"],
                    "MF (C3)": ["binding [GO:0003674]"],
                    "CC (C3)": ["nucleus [GO:0005634]"],
                }
            )
            other = expected.assign(**{"Unnamed: 0": ["other-gene"]})
            with pd.ExcelWriter(input_file, engine="openpyxl") as writer:
                other.to_excel(writer, sheet_name="Other", index=False)
                expected.to_excel(writer, sheet_name="Contrast_A", index=False)

            normalized = clustering.normalize_table(
                clustering.read_input_table(input_file, sheet_name="Contrast_A")
            )

        self.assertEqual(["gene-a"], normalized["gene_id"].tolist())
        self.assertEqual(1.5, normalized.loc[0, "log2FoldChange"])
        self.assertEqual("enzyme, subunit", normalized.loc[0, "Uniprot Function"])

    def test_clean_genes_filters_and_adds_direction(self) -> None:
        frame = pd.DataFrame(
            {
                "gene_id": ["up", "down", "not-deg", "generic"],
                "log2FoldChange": [2.0, -2.5, 0.5, 2.0],
                "pvalue": [0.001, 0.001, 0.001, 0.001],
                "padj": [0.01, 0.01, 0.01, 0.01],
                "Name GFF": ["Up", "Down", "Not", "Generic"],
                "Uniprot gene names": ["Up protein", "Down protein", "Not protein", "Generic protein"],
                "Uniprot Function": ["kinase activity", "transport activity", "binding", "hypothetical protein"],
                "Uniprot BP": [
                    "process [GO:0008150]",
                    "process [GO:0008150]",
                    "process [GO:0008150]",
                    "process [GO:0008150]",
                ],
                "Uniprot MF": [
                    "function [GO:0003674]",
                    "function [GO:0003674]",
                    "function [GO:0003674]",
                    "function [GO:0003674]",
                ],
                "Uniprot CC": ["", "", "", ""],
            }
        )

        cleaned = clustering.clean_genes(frame)

        self.assertEqual(["up", "down"], cleaned["gene_id"].tolist())
        self.assertEqual(["upregulated", "downregulated"], cleaned["direction"].tolist())

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

    def test_representatives_and_compatibility_json_use_semantic_medoids(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            features_dir = root / "features"
            clusters_dir = root / "clusters"
            bp_dir = clusters_dir / "BP"
            features_dir.mkdir()
            bp_dir.mkdir(parents=True)

            similarity = pd.DataFrame(
                [
                    [1.0, 0.9, 0.5],
                    [0.9, 1.0, 0.8],
                    [0.5, 0.8, 1.0],
                ],
                index=["a", "b", "c"],
                columns=["a", "b", "c"],
            )
            similarity.to_csv(features_dir / "GO_Wang_BP.csv")

            cluster_rows = pd.DataFrame(
                {
                    "cluster": [1, 1, 1],
                    "gene_id": ["a", "b", "c"],
                    "log2FoldChange": [2.0, 2.0, 2.0],
                    "Name GFF": ["Alpha", "Beta", "Gamma"],
                    "Uniprot gene names": ["Alpha protein", "Beta protein", "Gamma protein"],
                    "function": ["f", "f", "f"],
                    "go_terms": ["term [GO:0008150]"] * 3,
                    "cluster_silhouette": [0.5, 0.6, 0.4],
                    "cluster_size": [3, 3, 3],
                    "mean_silhouette": [0.5, 0.5, 0.5],
                    "min_silhouette": [0.4, 0.4, 0.4],
                    "min_pairwise_similarity": [0.5, 0.5, 0.5],
                    "cluster_quality": ["strong", "strong", "strong"],
                }
            )
            cluster_rows.to_csv(bp_dir / "upregulated_clusters.csv", index=False)

            representatives = clustering.load_representatives(clusters_dir, features_dir)
            compatibility = clustering.build_compatibility_clusters(representatives, clusters_dir)

        self.assertEqual(["b"], representatives["gene_id"].tolist())
        self.assertIn("BP:up:1", compatibility)
        self.assertEqual("Beta protein", compatibility["BP:up:1"]["representative"])
        self.assertEqual(["a", "b", "c"], compatibility["BP:up:1"]["gene_ids"])

    def test_cluster_pipeline_preserves_legacy_artifacts_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_file = root / "DEG.xlsx"
            out_dir = root / "out"
            sheet_name = "Contrast_A"
            input_data = pd.DataFrame(
                {
                    "gene_id": ["a", "b", "c"],
                    "logFC": [2.0, 2.1, 1.9],
                    "PValue": [0.001, 0.001, 0.001],
                    "FDR": [0.01, 0.01, 0.01],
                    "Name GFF": ["Alpha", "Beta", "Gamma"],
                    "Uniprot gene names": ["Alpha protein", "Beta protein", "Gamma protein"],
                    "Uniprot Function": ["kinase", "kinase", "kinase"],
                    "Uniprot BP": ["response [GO:0008150]"] * 3,
                    "Uniprot MF": ["binding [GO:0003674]"] * 3,
                    "Uniprot CC": ["nucleus [GO:0005634]"] * 3,
                }
            )
            input_data.to_excel(input_file, sheet_name=sheet_name, index=False)

            def fake_run_wang(features_file, features_dir, metrics_path):
                features = pd.read_csv(features_file)
                ids = features["gene_id"].astype(str).tolist()
                similarity = pd.DataFrame(
                    [
                        [1.0, 0.95, 0.90],
                        [0.95, 1.0, 0.92],
                        [0.90, 0.92, 1.0],
                    ],
                    index=ids,
                    columns=ids,
                )
                for ontology in clustering.ONTOLOGIES:
                    similarity.to_csv(features_dir / f"GO_Wang_{ontology}.csv")
                clustering.update_metrics(
                    metrics_path,
                    **{
                        "Number of valid GO-annotated genes": 3,
                        "GO term validation / update time": 0,
                        "Wang similarity matrix time": 0,
                    },
                )
                return {"stdout": "fake", "stderr": ""}

            original_run_wang = clustering.run_wang
            try:
                clustering.run_wang = fake_run_wang
                result = clustering.cluster_pipeline(
                    str(input_file),
                    sheet_name=sheet_name,
                    img_final_path=str(out_dir / "cluster.png"),
                    img_metrics_path=str(out_dir / "metrics.png"),
                    clusters_json_path=str(out_dir / "clusters.json"),
                )
            finally:
                clustering.run_wang = original_run_wang

            clusters = pd.read_json(out_dir / "clusters.json")

            self.assertTrue((out_dir / "cluster.png").exists())
            self.assertTrue((out_dir / "metrics.png").exists())
            self.assertTrue((out_dir / "clusters.json").exists())
            self.assertGreaterEqual(result["cluster_count"], 1)
            self.assertIn("BP:up:1", clusters.columns)

    def test_cluster_pipeline_writes_empty_artifacts_for_too_few_valid_genes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_file = root / "DEG.xlsx"
            out_dir = root / "out"
            sheet_name = "Contrast_A"
            input_data = pd.DataFrame(
                {
                    "gene_id": ["a", "b"],
                    "logFC": [2.0, -2.1],
                    "PValue": [0.001, 0.001],
                    "FDR": [0.01, 0.01],
                    "Name GFF": ["Alpha", "Beta"],
                    "Uniprot gene names": ["Alpha protein", "Beta protein"],
                    "Uniprot Function": ["kinase", "binding"],
                    "Uniprot BP": ["response [GO:0008150]"] * 2,
                    "Uniprot MF": ["binding [GO:0003674]"] * 2,
                    "Uniprot CC": ["nucleus [GO:0005634]"] * 2,
                }
            )
            input_data.to_excel(input_file, sheet_name=sheet_name, index=False)

            def fake_run_wang(features_file, features_dir, metrics_path):
                features = pd.read_csv(features_file)
                ids = features["gene_id"].astype(str).tolist()
                similarity = pd.DataFrame(np.eye(len(ids)), index=ids, columns=ids)
                for ontology in clustering.ONTOLOGIES:
                    similarity.to_csv(features_dir / f"GO_Wang_{ontology}.csv")
                clustering.update_metrics(
                    metrics_path,
                    **{
                        "Number of valid GO-annotated genes": len(ids),
                        "GO term validation / update time": 0,
                        "Wang similarity matrix time": 0,
                    },
                )
                return {"stdout": "fake", "stderr": ""}

            original_run_wang = clustering.run_wang
            try:
                clustering.run_wang = fake_run_wang
                result = clustering.cluster_pipeline(
                    str(input_file),
                    sheet_name=sheet_name,
                    img_final_path=str(out_dir / "cluster.png"),
                    img_metrics_path=str(out_dir / "metrics.png"),
                    clusters_json_path=str(out_dir / "clusters.json"),
                )
            finally:
                clustering.run_wang = original_run_wang

            self.assertTrue((out_dir / "cluster.png").exists())
            self.assertTrue((out_dir / "metrics.png").exists())
            self.assertEqual(0, result["cluster_count"])
            self.assertEqual({}, result["clusters"])


if __name__ == "__main__":
    unittest.main()
