from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

FEATURES_FILE = Path("outputs/features/genes_filtered.csv")
FEATURES_DIR = Path("outputs/features")
CLUSTERS_DIR = Path("clusters")
INTERPRETATIONS_FILE = CLUSTERS_DIR / "interpretations.csv"
OUTPUT_FILE = Path("outputs/prioritized_genes.csv")

ONTOLOGIES = {
    "BP": "go_terms",  # BILBO_CANONICAL_GO_TERMS_CONTRACT,
    "MF": "go_terms",
    "CC": "go_terms",
}
DIRECTIONS = {
    "down": "downregulated",
    "up": "upregulated",
}


def representative_for_cluster(
    cluster: pd.DataFrame,
    similarity: pd.DataFrame,
) -> pd.Series:
    gene_ids = cluster["gene_id"].astype(str)
    matrix = similarity.loc[gene_ids, gene_ids].to_numpy(float)
    centrality = (matrix.sum(axis=1) - 1) / (len(cluster) - 1)

    ranked = cluster.assign(
        representative_centrality=centrality,
        abs_log2_fold_change=cluster["log2FoldChange"].abs(),
    ).sort_values(
        [
            "representative_centrality",
            "cluster_silhouette",
            "abs_log2_fold_change",
            "gene_id",
        ],
        ascending=[False, False, False, True],
    )
    return ranked.iloc[0]


def load_representatives(
    features_dir: Path = FEATURES_DIR,
    clusters_dir: Path = CLUSTERS_DIR,
) -> pd.DataFrame:
    representatives = []

    for ontology, go_column in ONTOLOGIES.items():
        similarity = pd.read_csv(
            features_dir / f"GO_Wang_{ontology}.csv",
            index_col=0,
        )
        for direction, filename_prefix in DIRECTIONS.items():
            clusters = pd.read_csv(clusters_dir / ontology / f"{filename_prefix}_clusters.csv")
            clusters = clusters.loc[clusters["cluster"].ne(-1)]

            for cluster_id, cluster in clusters.groupby("cluster"):
                representative = representative_for_cluster(cluster, similarity).copy()
                representative["ontology"] = ontology
                representative["direction_name"] = direction
                representative["represented_cluster"] = f"{ontology}:{direction}:{int(cluster_id)}"
                representative["go_terms"] = representative[go_column]
                representatives.append(representative)

    return pd.DataFrame(representatives)


def primary_name(name: str) -> str:
    return re.split(r"\s*[\(\[]", str(name), maxsplit=1)[0].strip()


def go_labels(annotations: pd.Series) -> list[str]:
    labels = []
    for annotation in annotations.fillna(""):
        for term in annotation.split(";"):
            label = re.sub(r"\s*\[GO:\d+\]\s*", "", term).strip()
            if label and label not in labels:
                labels.append(label)
    return labels


def search_query(name: str, labels: list[str]) -> str:
    return ", ".join([name, *labels[:3]])


def load_interpretations(
    interpretations_file: Path = INTERPRETATIONS_FILE,
) -> dict[str, str]:
    if not interpretations_file.exists():
        return {}
    interpretations = pd.read_csv(interpretations_file)
    if interpretations.empty:
        return {}
    return {
        f"{row.ontology}:{row.direction}:{int(row.cluster)}": row.interpretation for row in interpretations.itertuples()
    }


def build_candidates(
    representatives: pd.DataFrame,
    features_file: Path = FEATURES_FILE,
    interpretations_file: Path = INTERPRETATIONS_FILE,
) -> pd.DataFrame:
    genes = pd.read_csv(features_file).set_index("gene_id")
    interpretations = load_interpretations(interpretations_file)
    candidates = []

    for gene_id, represented in representatives.groupby("gene_id"):
        gene = genes.loc[gene_id]
        clusters = represented["represented_cluster"].tolist()
        labels = go_labels(represented["go_terms"])
        name = primary_name(gene["Uniprot gene names"])
        themes = [interpretations[cluster] for cluster in clusters if cluster in interpretations]

        candidates.append(
            {
                "gene_id": gene_id,
                "direction": gene["direction"],
                "primary_name": name,
                "Name GFF": gene["Name GFF"],
                "Uniprot gene names": gene["Uniprot gene names"],
                "log2FoldChange": gene["log2FoldChange"],
                "padj": gene["padj"],
                "centrality_score": represented["representative_centrality"].mean(),
                "min_cluster_quality": represented["mean_silhouette"].min(),
                "n_ontologies": represented["ontology"].nunique(),
                "represented_ontologies": "; ".join(sorted(represented["ontology"].unique())),
                "represented_clusters": "; ".join(clusters),
                "cluster_themes": " | ".join(themes),
                "search_query": search_query(name, labels),
            }
        )

    candidates = pd.DataFrame(candidates)
    candidates["selected_for_search"] = candidates["n_ontologies"].ge(2)
    candidates["selection_reason"] = np.where(
        candidates["selected_for_search"],
        "representative_in_multiple_ontologies",
        "representative_in_single_ontology",
    )
    candidates["abs_log2FoldChange"] = candidates["log2FoldChange"].abs()
    return candidates.sort_values(
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
    ).reset_index(drop=True)


def add_rank(candidates: pd.DataFrame) -> pd.DataFrame:
    candidates = candidates.copy()
    selected = candidates.pop("selected_for_search")
    reason = candidates.pop("selection_reason")
    candidates.insert(0, "rank", np.arange(1, len(candidates) + 1))
    candidates.insert(1, "selected_for_search", selected)
    candidates.insert(2, "selection_reason", reason)
    return candidates


def run_prioritization(
    features_file: Path,
    features_dir: Path,
    clusters_dir: Path,
    interpretations_file: Path,
    output_file: Path,
) -> pd.DataFrame:
    representatives = load_representatives(features_dir, clusters_dir)
    if representatives.empty:
        candidates = pd.DataFrame()
    else:
        candidates = add_rank(build_candidates(representatives, features_file, interpretations_file))

    output_file.parent.mkdir(parents=True, exist_ok=True)
    candidates.to_csv(output_file, index=False)

    print(
        f"{len(candidates)} representantes unicos; "
        f"{(candidates['selected_for_search'].sum() if not candidates.empty else 0)} selecionados por suporte "
        "em multiplas ontologias."
    )
    return candidates


def main() -> None:
    run_prioritization(
        FEATURES_FILE,
        FEATURES_DIR,
        CLUSTERS_DIR,
        INTERPRETATIONS_FILE,
        OUTPUT_FILE,
    )


if __name__ == "__main__":
    main()
