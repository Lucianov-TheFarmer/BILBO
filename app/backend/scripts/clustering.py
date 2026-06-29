from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
from pathlib import Path
from time import perf_counter
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/tmp/bilbo-matplotlib")
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics import silhouette_samples


SCRIPT_DIR = Path(__file__).resolve().parent
WANG_SCRIPT = SCRIPT_DIR / "go_wang.R"

PADJ_MAX = 0.05
MIN_ABS_LOG2_FOLD_CHANGE = 1.0
MIN_GO_TERMS = 2
MIN_CLUSTER_SIZE = 3

GO_COLS = ["Uniprot BP", "Uniprot MF", "Uniprot CC"]
NAME_COLS = ["Name GFF", "Uniprot gene names"]
CANONICAL_COLUMNS = [
    "gene_id",
    "log2FoldChange",
    "pvalue",
    "padj",
    "Name GFF",
    "Uniprot gene names",
    "Uniprot Function",
    "Uniprot BP",
    "Uniprot MF",
    "Uniprot CC",
]
CLUSTER_COLUMNS = [
    "cluster",
    "gene_id",
    "log2FoldChange",
    "Name GFF",
    "Uniprot gene names",
    "function",
    "go_terms",
    "cluster_silhouette",
    "cluster_size",
    "mean_silhouette",
    "min_silhouette",
    "min_pairwise_similarity",
    "cluster_quality",
]
PRIORITIZED_COLUMNS = [
    "rank",
    "selected_for_search",
    "selection_reason",
    "gene_id",
    "direction",
    "primary_name",
    "Name GFF",
    "Uniprot gene names",
    "log2FoldChange",
    "padj",
    "centrality_score",
    "min_cluster_quality",
    "n_ontologies",
    "represented_ontologies",
    "represented_clusters",
    "cluster_themes",
    "search_query",
    "abs_log2FoldChange",
]
METRIC_COLUMNS = [
    "Dataset size",
    "Number of DEGs",
    "Number of valid GO-annotated genes",
    "GO term validation / update time",
    "Wang similarity matrix time",
    "Hierarchical clustering time",
    "Silhouette pruning time",
    "Semantic medoid selection time",
    "Total clustering time",
    "Representative genes submitted to RAG",
]

ONTOLOGIES = {
    "BP": ("Uniprot BP", 0.50),
    "MF": ("Uniprot MF", 0.60),
    "CC": ("Uniprot CC", 0.85),
}
DIRECTIONS = {
    "down": "downregulated",
    "up": "upregulated",
}

GENERIC_FUNCTION = (
    r"(function:\s*)?"
    r"(hypothetical|uncharacterized|unknown|predicted|putative|expressed)"
    r"( protein)?( of unknown function)?[.\s]*"
)
GENERIC_NAME = (
    r"hypothetical|uncharacterized|unknown|predicted|putative protein|"
    r"expressed protein|similar to .*protein|os\d+g\d+.*protein"
)


def _empty_metrics() -> dict[str, Any]:
    return {column: "" for column in METRIC_COLUMNS}


def _read_metrics(path: Path) -> dict[str, Any]:
    if not path.exists() or path.stat().st_size == 0:
        return _empty_metrics()
    metrics = pd.read_csv(path)
    if metrics.empty:
        return _empty_metrics()
    row = _empty_metrics()
    row.update(metrics.iloc[0].to_dict())
    return row


def _write_metrics(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{column: row.get(column, "") for column in METRIC_COLUMNS}]).to_csv(
        path,
        index=False,
    )


def reset_metrics(path: Path, **values: Any) -> None:
    row = _empty_metrics()
    row.update(values)
    _write_metrics(path, row)


def update_metrics(path: Path, **values: Any) -> None:
    row = _read_metrics(path)
    row.update(values)
    _write_metrics(path, row)


def add_duration(path: Path, column: str, seconds: float) -> None:
    row = _read_metrics(path)
    current = pd.to_numeric(pd.Series([row.get(column, 0)]), errors="coerce").iloc[0]
    row[column] = float(0 if pd.isna(current) else current) + float(seconds)
    _write_metrics(path, row)


def recompute_total_clustering_time(path: Path) -> None:
    row = _read_metrics(path)
    columns = [
        "GO term validation / update time",
        "Wang similarity matrix time",
        "Hierarchical clustering time",
        "Silhouette pruning time",
        "Semantic medoid selection time",
    ]
    values = pd.to_numeric(
        pd.Series([row.get(column, 0) for column in columns]),
        errors="coerce",
    )
    row["Total clustering time"] = float(values.fillna(0).sum())
    _write_metrics(path, row)


def usable_text(value: Any) -> str:
    text = str(value).strip()
    return "" if text.lower() in {"", "nan", "none"} else text


def first_existing(frame: pd.DataFrame, columns: list[str]) -> pd.Series:
    for column in columns:
        if column in frame.columns:
            return frame[column]
    return pd.Series([""] * len(frame), index=frame.index)


def parse_number(series: pd.Series) -> pd.Series:
    cleaned = (
        series.fillna("")
        .astype(str)
        .str.strip()
        .str.strip("'")
        .str.replace(",", ".", regex=False)
    )
    return pd.to_numeric(cleaned, errors="coerce")


def normalize_table(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()

    if "gene_id" not in normalized.columns:
        if "Unnamed: 0" in normalized.columns:
            normalized["gene_id"] = normalized["Unnamed: 0"]
        elif len(normalized.columns) > 0 and normalized.columns[0] not in {"logFC", "logCPM", "LR", "PValue", "FDR"}:
            normalized["gene_id"] = normalized.iloc[:, 0]

    aliases = {
        "log2FoldChange": ["logFC", "log2FoldChange", "log_fold_change"],
        "pvalue": ["PValue", "pvalue", "p.value", "P.Value"],
        "padj": ["FDR", "padj", "adj.P.Val", "qvalue"],
    }
    for target, source_columns in aliases.items():
        if target not in normalized.columns:
            for source in source_columns:
                if source in normalized.columns:
                    normalized[target] = normalized[source]
                    break

    if "Name GFF" not in normalized.columns:
        normalized["Name GFF"] = first_existing(
            normalized,
            ["protein_name", "Product GFF", "Note GFF", "gene_id"],
        )
    if "Uniprot gene names" not in normalized.columns:
        normalized["Uniprot gene names"] = first_existing(
            normalized,
            ["Prot. encontrada (C3)", "Prot. encontrada (C4)", "Product GFF", "protein_name", "Name GFF"],
        )
    if "Uniprot Function" not in normalized.columns:
        normalized["Uniprot Function"] = first_existing(
            normalized,
            ["Funcao (C3)", "Funcao (C4)", "Função (C3)", "Função (C4)", "Product GFF", "Note GFF"],
        )
    if "Uniprot BP" not in normalized.columns:
        normalized["Uniprot BP"] = first_existing(normalized, ["BP (C3)", "BP (C4)"])
    if "Uniprot MF" not in normalized.columns:
        normalized["Uniprot MF"] = first_existing(normalized, ["MF (C3)", "MF (C4)"])
    if "Uniprot CC" not in normalized.columns:
        normalized["Uniprot CC"] = first_existing(normalized, ["CC (C3)", "CC (C4)"])

    missing = [column for column in CANONICAL_COLUMNS if column not in normalized.columns]
    if missing:
        raise ValueError(f"Colunas obrigatorias ausentes apos normalizacao: {missing}")

    normalized["log2FoldChange"] = parse_number(normalized["log2FoldChange"])
    normalized["pvalue"] = parse_number(normalized["pvalue"])
    normalized["padj"] = parse_number(normalized["padj"])
    normalized["gene_id"] = normalized["gene_id"].fillna("").astype(str).str.strip()

    for column in CANONICAL_COLUMNS:
        if column not in {"log2FoldChange", "pvalue", "padj"}:
            normalized[column] = normalized[column].fillna("").astype(str).str.strip()

    return normalized.loc[:, CANONICAL_COLUMNS]


def require_columns(frame: pd.DataFrame) -> None:
    missing_columns = set(CANONICAL_COLUMNS) - set(frame.columns)
    if missing_columns:
        raise ValueError(f"Colunas obrigatorias ausentes: {sorted(missing_columns)}")


def clean_genes(genes: pd.DataFrame) -> pd.DataFrame:
    require_columns(genes)

    genes = genes.copy()
    genes["gene_id"] = genes["gene_id"].fillna("").astype(str).str.strip()
    non_empty_ids = genes.loc[genes["gene_id"].ne(""), "gene_id"]
    if non_empty_ids.duplicated().any():
        duplicated = non_empty_ids[non_empty_ids.duplicated()].unique().tolist()
        raise ValueError(f"gene_id deve ser unico; duplicados: {duplicated[:10]}")

    for column in ["log2FoldChange", "pvalue", "padj"]:
        genes[column] = pd.to_numeric(genes[column], errors="coerce")

    function = genes["Uniprot Function"].fillna("").astype(str).str.strip()
    names = genes[NAME_COLS].fillna("").astype(str).apply(lambda column: column.str.strip())
    go_count = (
        genes[GO_COLS]
        .fillna("")
        .astype(str)
        .apply(lambda column: column.str.count(r"GO:\d+"))
        .sum(axis=1)
    )

    differentially_expressed = (
        genes["padj"].le(PADJ_MAX)
        & genes["log2FoldChange"].abs().ge(MIN_ABS_LOG2_FOLD_CHANGE)
    )
    valid_function = function.ne("") & ~function.str.fullmatch(
        GENERIC_FUNCTION,
        case=False,
    )
    useful_name = (
        names.ne("")
        & ~names.apply(
            lambda column: column.str.contains(
                GENERIC_NAME,
                case=False,
                regex=True,
            )
        )
    ).any(axis=1)

    kept = (
        genes["gene_id"].ne("")
        & differentially_expressed
        & go_count.ge(MIN_GO_TERMS)
        & valid_function
    )
    selected_columns = [
        "gene_id",
        "log2FoldChange",
        "pvalue",
        "padj",
        *NAME_COLS,
        "Uniprot Function",
        *GO_COLS,
    ]
    filtered = genes.loc[kept, selected_columns].copy()
    filtered.insert(
        2,
        "direction",
        np.where(filtered["log2FoldChange"] > 0, "upregulated", "downregulated"),
    )
    filtered.insert(7, "useful_name", useful_name.loc[kept].to_numpy())
    return filtered.reset_index(drop=True)


def invalid_go_ids(ontology: str, invalid_go_file: Path) -> set[str]:
    if invalid_go_file.exists() and invalid_go_file.stat().st_size > 0:
        invalid = pd.read_csv(invalid_go_file)
        if {"ontology", "go_id"}.issubset(invalid.columns):
            return set(invalid.loc[invalid["ontology"].eq(ontology), "go_id"])
    return set()


def clean_go_annotations(series: pd.Series, invalid_ids: set[str]) -> pd.Series:
    return series.fillna("").apply(
        lambda annotation: "; ".join(
            term.strip()
            for term in str(annotation).split(";")
            if term.strip()
            and not any(go_id in invalid_ids for go_id in re.findall(r"GO:\d+", term))
        )
    )


def valid_go_gene_ids(genes: pd.DataFrame, go_column: str) -> set[str]:
    has_valid_go = genes[go_column].fillna("").astype(str).str.contains(r"GO:\d+", regex=True)
    return set(genes.loc[has_valid_go, "gene_id"].astype(str))


def read_similarity(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        similarity = pd.read_csv(path, index_col=0)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()
    similarity.index = similarity.index.astype(str)
    similarity.columns = similarity.columns.astype(str)
    return similarity


def distance_matrix(similarity: pd.DataFrame, gene_ids: pd.Series) -> np.ndarray:
    ids = gene_ids.astype(str)
    if len(ids) == 0:
        return np.zeros((0, 0))
    matrix = similarity.loc[ids, ids].to_numpy(float)
    matrix = np.clip((matrix + matrix.T) / 2, 0, 1)
    np.fill_diagonal(matrix, 1)
    return 1 - matrix


def empty_result(genes: pd.DataFrame) -> pd.DataFrame:
    return genes.assign(
        cluster=-1,
        cluster_silhouette=np.nan,
        cluster_size=np.nan,
        mean_silhouette=np.nan,
        min_silhouette=np.nan,
        min_pairwise_similarity=np.nan,
        cluster_quality="",
    )


def renumber(labels: np.ndarray) -> np.ndarray:
    cluster_ids = sorted(label for label in np.unique(labels) if label != -1)
    mapping = {label: index for index, label in enumerate(cluster_ids, start=1)}
    return np.array([mapping.get(label, -1) for label in labels], dtype=int)


def remove_small_clusters(labels: np.ndarray) -> None:
    counts = pd.Series(labels[labels != -1]).value_counts()
    labels[np.isin(labels, counts[counts < MIN_CLUSTER_SIZE].index)] = -1


def silhouette(distance: np.ndarray, labels: np.ndarray) -> np.ndarray:
    scores = np.full(len(labels), np.nan)
    clustered = labels != -1
    if len(np.unique(labels[clustered])) >= 2:
        scores[clustered] = silhouette_samples(
            distance[np.ix_(clustered, clustered)],
            labels[clustered],
            metric="precomputed",
        )
    return scores


def prune_negative_silhouettes(distance: np.ndarray, labels: np.ndarray) -> np.ndarray:
    labels = labels.copy()
    remove_small_clusters(labels)
    while True:
        scores = silhouette(distance, labels)
        negative = np.isfinite(scores) & (scores < 0)
        if not negative.any():
            return labels
        labels[negative] = -1
        remove_small_clusters(labels)


def add_cluster_metrics(
    result: pd.DataFrame,
    distance: np.ndarray,
    labels: np.ndarray,
    scores: np.ndarray,
) -> None:
    for cluster in sorted(set(labels) - {-1}):
        cluster_mask = labels == cluster
        cluster_distance = distance[np.ix_(cluster_mask, cluster_mask)]
        pairwise = 1 - cluster_distance[np.triu_indices(cluster_mask.sum(), 1)]
        cluster_scores = scores[cluster_mask]
        finite_scores = cluster_scores[np.isfinite(cluster_scores)]
        mean_score = finite_scores.mean() if len(finite_scores) else np.nan
        min_score = finite_scores.min() if len(finite_scores) else np.nan
        quality = (
            "unknown"
            if not len(finite_scores)
            else "strong"
            if mean_score >= 0.30
            else "borderline"
            if mean_score >= 0.10
            else "weak"
        )

        result.loc[cluster_mask, "cluster_size"] = cluster_mask.sum()
        result.loc[cluster_mask, "mean_silhouette"] = mean_score
        result.loc[cluster_mask, "min_silhouette"] = min_score
        result.loc[cluster_mask, "min_pairwise_similarity"] = pairwise.min()
        result.loc[cluster_mask, "cluster_quality"] = quality


def _fit_complete_linkage(distance: np.ndarray, min_similarity: float) -> np.ndarray:
    threshold = np.nextafter(1 - min_similarity, np.inf)
    try:
        return AgglomerativeClustering(
            n_clusters=None,
            metric="precomputed",
            linkage="complete",
            distance_threshold=threshold,
        ).fit_predict(distance)
    except TypeError:
        return AgglomerativeClustering(
            n_clusters=None,
            affinity="precomputed",
            linkage="complete",
            distance_threshold=threshold,
        ).fit_predict(distance)


def cluster_genes(
    genes: pd.DataFrame,
    distance: np.ndarray,
    min_similarity: float,
    metrics_path: Path | None = None,
) -> pd.DataFrame:
    result = empty_result(genes)
    if len(result) < MIN_CLUSTER_SIZE:
        return result

    start = perf_counter()
    labels = _fit_complete_linkage(distance, min_similarity)
    if metrics_path is not None:
        add_duration(metrics_path, "Hierarchical clustering time", perf_counter() - start)

    start = perf_counter()
    labels = renumber(prune_negative_silhouettes(distance, labels))
    if metrics_path is not None:
        add_duration(metrics_path, "Silhouette pruning time", perf_counter() - start)
    scores = silhouette(distance, labels)

    result["cluster"] = labels
    result["cluster_silhouette"] = scores
    add_cluster_metrics(result, distance, labels, scores)
    return result


def final_columns(result: pd.DataFrame, go_column: str) -> pd.DataFrame:
    result = result.assign(
        function=result["Uniprot Function"],
        go_terms=result[go_column],
        _cluster_sort=result["cluster"].replace(-1, np.inf),
    )
    result["cluster_size"] = result["cluster_size"].astype("Int64")
    return (
        result.sort_values(["_cluster_sort", "gene_id"])
        .loc[:, CLUSTER_COLUMNS]
        .reset_index(drop=True)
    )


def read_input_table(path: str | Path, sheet_name: str | None = None) -> pd.DataFrame:
    input_path = Path(path)
    if input_path.suffix.lower() in {".xlsx", ".xls"}:
        if sheet_name is None:
            return pd.read_excel(input_path)
        return pd.read_excel(input_path, sheet_name=sheet_name)
    return pd.read_csv(input_path)


def run_wang(features_file: Path, features_dir: Path, metrics_path: Path) -> dict[str, Any]:
    if not WANG_SCRIPT.exists():
        raise FileNotFoundError(f"Script R de similaridade GO nao encontrado: {WANG_SCRIPT}")
    process = subprocess.run(
        ["Rscript", str(WANG_SCRIPT), str(features_file), str(features_dir), str(metrics_path)],
        capture_output=True,
        text=True,
        timeout=172800,
        check=False,
    )
    if process.returncode != 0:
        raise RuntimeError(
            "Falha ao calcular similaridade GO Wang. "
            f"stdout={process.stdout[-2000:]} stderr={process.stderr[-4000:]}"
        )
    return {"stdout": process.stdout[-4000:], "stderr": process.stderr[-2000:]}


def run_semantic_clustering(
    features_file: Path,
    features_dir: Path,
    clusters_dir: Path,
    metrics_path: Path,
) -> None:
    genes = pd.read_csv(features_file)
    invalid_file = features_dir / "invalid_go_annotations.csv"

    for ontology, (go_column, min_similarity) in ONTOLOGIES.items():
        similarity = read_similarity(features_dir / f"GO_Wang_{ontology}.csv")
        cleaned_genes = genes.copy()
        cleaned_genes[go_column] = clean_go_annotations(
            cleaned_genes[go_column],
            invalid_go_ids(ontology, invalid_file),
        )
        valid_gene_ids = valid_go_gene_ids(cleaned_genes, go_column)
        valid_gene_ids &= set(similarity.index.astype(str))
        output_dir = clusters_dir / ontology
        output_dir.mkdir(parents=True, exist_ok=True)

        for direction_name, direction in DIRECTIONS.items():
            selected = cleaned_genes.loc[cleaned_genes["direction"].eq(direction)].copy()
            eligible = selected.loc[selected["gene_id"].astype(str).isin(valid_gene_ids)].copy()
            result = empty_result(selected)

            if len(eligible) >= MIN_CLUSTER_SIZE:
                distance = distance_matrix(similarity, eligible["gene_id"].astype(str))
                clustered = cluster_genes(
                    eligible,
                    distance,
                    min_similarity,
                    metrics_path=metrics_path,
                )
                result.loc[clustered.index, "cluster"] = clustered["cluster"]
                result.loc[clustered.index, "cluster_silhouette"] = clustered["cluster_silhouette"]
                metric_columns = [
                    "cluster_size",
                    "mean_silhouette",
                    "min_silhouette",
                    "min_pairwise_similarity",
                    "cluster_quality",
                ]
                result.loc[clustered.index, metric_columns] = clustered[metric_columns]

            output_file = output_dir / f"{direction_name}regulated_clusters.csv"
            final_columns(result, go_column).to_csv(output_file, index=False)

    recompute_total_clustering_time(metrics_path)


def representative_for_cluster(cluster: pd.DataFrame, similarity: pd.DataFrame) -> pd.Series:
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
    clusters_dir: Path,
    features_dir: Path,
    metrics_path: Path | None = None,
) -> pd.DataFrame:
    start = perf_counter()
    representatives: list[pd.Series] = []

    for ontology, _ontology_config in ONTOLOGIES.items():
        similarity = read_similarity(features_dir / f"GO_Wang_{ontology}.csv")
        if similarity.empty:
            continue
        for direction, filename_prefix in DIRECTIONS.items():
            clusters_file = clusters_dir / ontology / f"{filename_prefix}_clusters.csv"
            if not clusters_file.exists() or clusters_file.stat().st_size == 0:
                continue
            clusters = pd.read_csv(clusters_file)
            clusters = clusters.loc[pd.to_numeric(clusters["cluster"], errors="coerce").ne(-1)]

            for cluster_id, cluster in clusters.groupby("cluster"):
                representative = representative_for_cluster(cluster, similarity).copy()
                representative["ontology"] = ontology
                representative["direction_name"] = direction
                representative["represented_cluster"] = f"{ontology}:{direction}:{int(cluster_id)}"
                representatives.append(representative)

    if metrics_path is not None:
        add_duration(metrics_path, "Semantic medoid selection time", perf_counter() - start)
        recompute_total_clustering_time(metrics_path)

    return pd.DataFrame(representatives)


def primary_name(name: Any) -> str:
    text = usable_text(name)
    return re.split(r"\s*[\(\[]", text, maxsplit=1)[0].strip()


def go_labels(annotations: pd.Series) -> list[str]:
    labels: list[str] = []
    for annotation in annotations.fillna(""):
        for term in str(annotation).split(";"):
            label = re.sub(r"\s*\[GO:\d+\]\s*", "", term).strip()
            if label and label not in labels:
                labels.append(label)
    return labels


def search_query(name: str, labels: list[str]) -> str:
    return ", ".join([part for part in [name, *labels[:3]] if part])


def build_prioritized_genes(
    representatives: pd.DataFrame,
    features_file: Path,
    output_file: Path,
    metrics_path: Path,
) -> pd.DataFrame:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    if representatives.empty:
        candidates = pd.DataFrame(columns=PRIORITIZED_COLUMNS)
        candidates.to_csv(output_file, index=False)
        update_metrics(metrics_path, **{"Representative genes submitted to RAG": 0})
        return candidates

    genes = pd.read_csv(features_file).set_index("gene_id")
    candidates = []
    for gene_id, represented in representatives.groupby("gene_id"):
        gene = genes.loc[gene_id]
        clusters = represented["represented_cluster"].tolist()
        labels = go_labels(represented["go_terms"])
        name = primary_name(gene["Uniprot gene names"]) or usable_text(gene["Name GFF"]) or str(gene_id)
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
                "cluster_themes": "",
                "search_query": search_query(name, labels),
            }
        )

    candidates_df = pd.DataFrame(candidates)
    candidates_df["selected_for_search"] = candidates_df["n_ontologies"].ge(2)
    candidates_df["selection_reason"] = np.where(
        candidates_df["selected_for_search"],
        "representative_in_multiple_ontologies",
        "representative_in_single_ontology",
    )
    candidates_df["abs_log2FoldChange"] = candidates_df["log2FoldChange"].abs()
    candidates_df = candidates_df.sort_values(
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
    selected = candidates_df.pop("selected_for_search")
    reason = candidates_df.pop("selection_reason")
    candidates_df.insert(0, "rank", np.arange(1, len(candidates_df) + 1))
    candidates_df.insert(1, "selected_for_search", selected)
    candidates_df.insert(2, "selection_reason", reason)
    candidates_df = candidates_df.reindex(columns=PRIORITIZED_COLUMNS)
    candidates_df.to_csv(output_file, index=False)
    update_metrics(
        metrics_path,
        **{"Representative genes submitted to RAG": int(candidates_df["selected_for_search"].sum())},
    )
    return candidates_df


def gene_label(row: pd.Series | dict[str, Any]) -> str:
    get = row.get  # type: ignore[assignment]
    return (
        primary_name(get("Uniprot gene names", ""))
        or usable_text(get("Name GFF", ""))
        or usable_text(get("gene_id", ""))
    )


def build_compatibility_clusters(representatives: pd.DataFrame, clusters_dir: Path) -> dict[str, Any]:
    compatibility: dict[str, Any] = {}
    if representatives.empty:
        return compatibility

    for representative in representatives.to_dict("records"):
        cluster_key = str(representative["represented_cluster"])
        ontology, direction, cluster_id = cluster_key.split(":")
        clusters_file = clusters_dir / ontology / f"{direction}regulated_clusters.csv"
        clusters = pd.read_csv(clusters_file)
        member_rows = clusters.loc[pd.to_numeric(clusters["cluster"], errors="coerce").eq(int(cluster_id))]
        genes = [gene_label(row) for _, row in member_rows.iterrows()]
        gene_ids = member_rows["gene_id"].fillna("").astype(str).tolist()
        compatibility[cluster_key] = {
            "representative": gene_label(representative),
            "representative_gene_id": str(representative.get("gene_id", "")),
            "genes": genes,
            "gene_ids": gene_ids,
            "ontology": ontology,
            "direction": DIRECTIONS.get(direction, direction),
            "cluster": int(cluster_id),
            "cluster_size": int(len(member_rows)),
            "mean_silhouette": _json_float(representative.get("mean_silhouette")),
            "cluster_quality": representative.get("cluster_quality", ""),
        }
    return compatibility


def _json_float(value: Any) -> float | None:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric) or math.isinf(float(numeric)):
        return None
    return float(numeric)


def _cluster_summary(clusters_dir: Path) -> pd.DataFrame:
    rows = []
    for ontology in ONTOLOGIES:
        for direction in DIRECTIONS:
            clusters_file = clusters_dir / ontology / f"{direction}regulated_clusters.csv"
            if not clusters_file.exists():
                continue
            clusters = pd.read_csv(clusters_file)
            clustered = clusters.loc[pd.to_numeric(clusters["cluster"], errors="coerce").ne(-1)]
            rows.append(
                {
                    "ontology": ontology,
                    "direction": direction,
                    "cluster_count": int(clustered["cluster"].nunique()) if not clustered.empty else 0,
                    "clustered_genes": int(clustered["gene_id"].nunique()) if not clustered.empty else 0,
                    "total_genes": int(clusters["gene_id"].nunique()) if "gene_id" in clusters.columns else 0,
                    "mean_silhouette": _json_float(clustered["mean_silhouette"].mean()) if not clustered.empty else None,
                }
            )
    return pd.DataFrame(rows)


def plot_cluster_summary(summary: pd.DataFrame, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(12, 7))
    if summary.empty:
        ax.text(0.5, 0.5, "No semantic clusters generated", ha="center", va="center", fontsize=16)
        ax.axis("off")
    else:
        labels = [f"{row.ontology}-{row.direction}" for row in summary.itertuples()]
        x = np.arange(len(labels))
        ax.bar(x - 0.18, summary["cluster_count"], width=0.36, label="Clusters")
        ax.bar(x + 0.18, summary["clustered_genes"], width=0.36, label="Clustered genes")
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=35, ha="right")
        ax.set_ylabel("Count")
        ax.set_title("GO Wang semantic clustering")
        ax.legend()
        ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def plot_metrics(summary: pd.DataFrame, metrics_path: Path, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    metrics = _read_metrics(metrics_path)
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    axes[0].axis("off")
    metric_lines = [
        ("Dataset size", metrics.get("Dataset size", "")),
        ("DEGs", metrics.get("Number of DEGs", "")),
        ("Valid GO genes", metrics.get("Number of valid GO-annotated genes", "")),
        ("Representatives to RAG", metrics.get("Representative genes submitted to RAG", "")),
        ("Total clustering time (s)", _json_float(metrics.get("Total clustering time"))),
    ]
    axes[0].text(
        0,
        1,
        "\n".join(f"{label}: {'' if value is None else value}" for label, value in metric_lines),
        va="top",
        fontsize=12,
    )

    if summary.empty or summary["mean_silhouette"].dropna().empty:
        axes[1].text(0.5, 0.5, "No silhouette values", ha="center", va="center")
        axes[1].axis("off")
    else:
        plotted = summary.dropna(subset=["mean_silhouette"])
        labels = [f"{row.ontology}-{row.direction}" for row in plotted.itertuples()]
        axes[1].bar(labels, plotted["mean_silhouette"])
        axes[1].set_title("Mean silhouette")
        axes[1].set_ylim(0, max(0.35, float(plotted["mean_silhouette"].max()) + 0.05))
        axes[1].tick_params(axis="x", rotation=35)
        axes[1].grid(axis="y", alpha=0.25)

    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def _prepare_output_dirs(out_dir: Path) -> tuple[Path, Path, Path]:
    features_dir = out_dir / "features"
    clusters_dir = out_dir / "clusters"
    outputs_dir = out_dir / "outputs"
    for path in [features_dir, clusters_dir]:
        if path.exists():
            shutil.rmtree(path)
    for path in [features_dir, clusters_dir, outputs_dir]:
        path.mkdir(parents=True, exist_ok=True)
    return features_dir, clusters_dir, outputs_dir


def cluster_pipeline(
    file_path: str,
    sheet_name: str | None = None,
    img_final_path: str = "Cluster.png",
    img_metrics_path: str = "Otimizacao_K.png",
    clusters_json_path: str | None = None,
) -> dict[str, Any]:
    out_dir = Path(clusters_json_path).resolve().parent if clusters_json_path else Path(img_final_path).resolve().parent
    out_dir.mkdir(parents=True, exist_ok=True)
    features_dir, clusters_dir, outputs_dir = _prepare_output_dirs(out_dir)
    metrics_path = out_dir / "pipeline_metrics.csv"
    normalized_path = out_dir / "input_normalized.csv"
    features_file = features_dir / "genes_filtered.csv"
    prioritized_path = outputs_dir / "prioritized_genes.csv"
    clusters_json = Path(clusters_json_path or out_dir / "clusters.json")

    raw = read_input_table(file_path, sheet_name=sheet_name)
    normalized = normalize_table(raw)
    normalized.to_csv(normalized_path, index=False)
    deg_mask = (
        normalized["padj"].le(PADJ_MAX)
        & normalized["log2FoldChange"].abs().ge(MIN_ABS_LOG2_FOLD_CHANGE)
    )
    reset_metrics(
        metrics_path,
        **{
            "Dataset size": len(normalized),
            "Number of DEGs": int(deg_mask.sum()),
        },
    )

    filtered = clean_genes(normalized)
    filtered.to_csv(features_file, index=False)

    wang_info = run_wang(features_file, features_dir, metrics_path)
    run_semantic_clustering(features_file, features_dir, clusters_dir, metrics_path)
    representatives = load_representatives(clusters_dir, features_dir, metrics_path=metrics_path)
    prioritized = build_prioritized_genes(representatives, features_file, prioritized_path, metrics_path)
    compatibility_clusters = build_compatibility_clusters(representatives, clusters_dir)

    clusters_json.write_text(
        json.dumps(compatibility_clusters, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    summary = _cluster_summary(clusters_dir)
    plot_cluster_summary(summary, Path(img_final_path))
    plot_metrics(summary, metrics_path, Path(img_metrics_path))

    return {
        "clusters": compatibility_clusters,
        "img_final": img_final_path,
        "img_metrics": img_metrics_path,
        "clusters_json": str(clusters_json),
        "features_dir": str(features_dir),
        "clusters_dir": str(clusters_dir),
        "metrics": str(metrics_path),
        "prioritized_genes": str(prioritized_path),
        "input_normalized": str(normalized_path),
        "cluster_count": len(compatibility_clusters),
        "representative_count": int(len(prioritized)),
        "wang": wang_info,
    }


if __name__ == "__main__":
    import sys

    path = sys.argv[1]
    sheet = sys.argv[2] if len(sys.argv) > 2 else None
    cluster_pipeline(path, sheet_name=sheet)
