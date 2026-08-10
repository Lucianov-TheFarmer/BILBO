from __future__ import annotations

import html
import json
import math
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


RAG_SCHEMA = "bilbo.rag-report.v2"
CLUSTER_SCHEMA = "bilbo.clustering-report.v2"

ONTOLOGIES = {
    "BP": "Uniprot BP",
    "MF": "Uniprot MF",
    "CC": "Uniprot CC",
}

DIRECTIONS = {
    "down": "downregulated",
    "up": "upregulated",
}

COLORS = [
    "#2563eb",
    "#dc2626",
    "#16a34a",
    "#9333ea",
    "#ea580c",
    "#0891b2",
    "#ca8a04",
    "#db2777",
    "#4f46e5",
    "#059669",
    "#7c3aed",
    "#be123c",
]


def _required_file(path: Path) -> Path:
    if not path.is_file() or path.stat().st_size == 0:
        raise FileNotFoundError(
            f"Required non-empty report input not found: {path}"
        )
    return path


def _required_columns(
    frame: pd.DataFrame,
    columns: set[str],
    source: Path,
) -> None:
    missing = sorted(columns.difference(frame.columns))
    if missing:
        raise ValueError(
            f"Missing required columns in {source}: {missing}"
        )


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, float) and math.isnan(value):
        return False
    return str(value).strip().lower() not in {
        "",
        "nan",
        "none",
        "na",
    }


def _scalar(value: Any) -> Any:
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
    return value


def _record(
    row: pd.Series,
    columns: list[str],
) -> dict[str, Any]:
    return {
        column: _scalar(row[column])
        for column in columns
        if column in row.index
    }


def _rank_cluster(
    cluster: pd.DataFrame,
    similarity: pd.DataFrame,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    gene_ids = cluster["gene_id"].astype(str).tolist()

    missing = sorted(
        set(gene_ids).difference(
            similarity.index.astype(str)
        )
    )
    if missing:
        raise ValueError(
            f"Cluster genes absent from Wang matrix: {missing[:10]}"
        )

    matrix = similarity.loc[
        gene_ids,
        gene_ids,
    ].to_numpy(dtype=float)

    if len(cluster) == 1:
        centrality = np.ones(1)
    else:
        centrality = (
            matrix.sum(axis=1) - 1.0
        ) / (len(cluster) - 1)

    ranked = cluster.copy().assign(
        representative_centrality=centrality,
        abs_log2_fold_change=(
            cluster["log2FoldChange"].abs()
        ),
    ).sort_values(
        [
            "representative_centrality",
            "cluster_silhouette",
            "abs_log2_fold_change",
            "gene_id",
        ],
        ascending=[
            False,
            False,
            False,
            True,
        ],
    )

    columns = [
        "gene_id",
        "Name GFF",
        "Uniprot gene names",
        "log2FoldChange",
        "padj",
        "cluster_silhouette",
        "representative_centrality",
        "abs_log2_fold_change",
    ]

    representatives = [
        _record(row, columns)
        for _, row in ranked.head(3).iterrows()
    ]

    return ranked, representatives


def build_report_payload(
    base_payload: dict[str, Any],
    clustering_dir: Path,
    *,
    require_interpretations: bool,
) -> dict[str, Any]:
    clustering_dir = clustering_dir.resolve()
    features_dir = clustering_dir / "features"
    clusters_dir = clustering_dir / "clusters"

    input_path = _required_file(
        clustering_dir / "input_normalized.csv"
    )
    features_path = _required_file(
        features_dir / "genes_filtered.csv"
    )

    raw = pd.read_csv(
        input_path,
        dtype={"gene_id": str},
    )
    genes = pd.read_csv(
        features_path,
        dtype={"gene_id": str},
    )

    _required_columns(
        raw,
        {
            "gene_id",
            *ONTOLOGIES.values(),
        },
        input_path,
    )

    _required_columns(
        genes,
        {
            "gene_id",
            "direction",
            "log2FoldChange",
            "padj",
            "Name GFF",
            "Uniprot gene names",
            *ONTOLOGIES.values(),
        },
        features_path,
    )

    if raw["gene_id"].duplicated().any():
        raise ValueError(
            "Duplicate gene_id in input_normalized.csv"
        )

    if genes["gene_id"].duplicated().any():
        raise ValueError(
            "Duplicate gene_id in genes_filtered.csv"
        )

    interpretation_map = {}

    if require_interpretations:
        interpretations_path = _required_file(
            clusters_dir / "interpretations.csv"
        )
        interpretations = pd.read_csv(
            interpretations_path
        )

        _required_columns(
            interpretations,
            {
                "ontology",
                "direction",
                "cluster",
                "n_genes",
                "interpretation",
            },
            interpretations_path,
        )

        for _, row in interpretations.iterrows():
            key = (
                str(row["ontology"]),
                str(row["direction"]),
                int(row["cluster"]),
            )

            if key in interpretation_map:
                raise ValueError(
                    f"Duplicate interpretation: {key}"
                )

            if not _present(row["interpretation"]):
                raise ValueError(
                    f"Empty interpretation: {key}"
                )

            interpretation_map[key] = {
                "n_genes": int(row["n_genes"]),
                "interpretation": str(
                    row["interpretation"]
                ),
            }

    gene_lookup = genes.set_index(
        "gene_id",
        drop=False,
    )

    clustered_any: set[str] = set()
    clusters = []
    ungrouped = []
    ontology_summary = []
    used_interpretations = set()

    for ontology, go_column in ONTOLOGIES.items():
        matrix_path = _required_file(
            features_dir / f"GO_Wang_{ontology}.csv"
        )

        similarity = pd.read_csv(
            matrix_path,
            index_col=0,
        )
        similarity.index = (
            similarity.index.astype(str)
        )
        similarity.columns = (
            similarity.columns.astype(str)
        )

        memberships = {}
        ontology_clustered = set()
        ontology_noise = set()

        for direction, prefix in DIRECTIONS.items():
            cluster_path = _required_file(
                clusters_dir
                / ontology
                / f"{prefix}_clusters.csv"
            )

            source = pd.read_csv(
                cluster_path,
                dtype={"gene_id": str},
            )

            _required_columns(
                source,
                {
                    "gene_id",
                    "cluster",
                    "cluster_silhouette",
                    "mean_silhouette",
                },
                cluster_path,
            )

            if source["gene_id"].duplicated().any():
                raise ValueError(
                    f"Duplicate gene_id in {cluster_path}"
                )

            unknown = sorted(
                set(source["gene_id"]).difference(
                    gene_lookup.index
                )
            )
            if unknown:
                raise ValueError(
                    f"Genes absent from genes_filtered.csv: "
                    f"{unknown[:10]}"
                )

            metadata_columns = [
                "gene_id",
                "Name GFF",
                "Uniprot gene names",
                "log2FoldChange",
                "padj",
                go_column,
            ]

            frame = source[
                [
                    "gene_id",
                    "cluster",
                    "cluster_silhouette",
                    "mean_silhouette",
                ]
            ].merge(
                genes[metadata_columns],
                on="gene_id",
                how="left",
                validate="one_to_one",
            )

            for gene_id, cluster_id in zip(
                frame["gene_id"],
                frame["cluster"],
            ):
                memberships[str(gene_id)] = (
                    direction,
                    int(cluster_id),
                )

            noise = frame.loc[
                frame["cluster"].eq(-1)
            ].copy()

            ontology_noise.update(
                noise["gene_id"]
            )

            gene_columns = [
                "gene_id",
                "Name GFF",
                "Uniprot gene names",
                "log2FoldChange",
                "padj",
                "cluster_silhouette",
                "mean_silhouette",
                go_column,
            ]

            ungrouped.append(
                {
                    "ontology": ontology,
                    "direction": direction,
                    "n_genes": int(len(noise)),
                    "genes": [
                        _record(row, gene_columns)
                        for _, row in noise.sort_values(
                            "gene_id"
                        ).iterrows()
                    ],
                }
            )

            grouped = frame.loc[
                frame["cluster"].ne(-1)
            ].copy()

            ontology_clustered.update(
                grouped["gene_id"]
            )
            clustered_any.update(
                grouped["gene_id"]
            )

            for cluster_id, group in grouped.groupby(
                "cluster",
                sort=True,
            ):
                key = (
                    ontology,
                    direction,
                    int(cluster_id),
                )

                interpretation = None

                if require_interpretations:
                    if key not in interpretation_map:
                        raise ValueError(
                            "Missing LLM interpretation "
                            f"for cluster {key}"
                        )

                    expected = interpretation_map[key][
                        "n_genes"
                    ]

                    if expected != len(group):
                        raise ValueError(
                            f"Cluster size mismatch for {key}: "
                            f"interpretation={expected}, "
                            f"csv={len(group)}"
                        )

                    interpretation = (
                        interpretation_map[key][
                            "interpretation"
                        ]
                    )
                    used_interpretations.add(key)

                ranked, representatives = _rank_cluster(
                    group,
                    similarity,
                )

                ranked_columns = (
                    gene_columns
                    + ["representative_centrality"]
                )

                clusters.append(
                    {
                        "cluster_id": (
                            f"{ontology}:"
                            f"{direction}:"
                            f"{int(cluster_id)}"
                        ),
                        "ontology": ontology,
                        "direction": direction,
                        "cluster": int(cluster_id),
                        "n_genes": int(len(group)),
                        "mean_silhouette": _scalar(
                            group[
                                "mean_silhouette"
                            ].iloc[0]
                        ),
                        "interpretation": interpretation,
                        "representatives": representatives,
                        "genes": [
                            _record(
                                row,
                                ranked_columns,
                            )
                            for _, row in ranked.iterrows()
                        ],
                    }
                )

        annotated_ids = set(
            raw.loc[
                raw[go_column].map(_present),
                "gene_id",
            ].astype(str)
        )

        matrix_ids = set(similarity.index)

        missing_membership = sorted(
            matrix_ids.difference(memberships)
        )
        if missing_membership:
            raise ValueError(
                f"Wang genes without cluster assignment "
                f"for {ontology}: "
                f"{missing_membership[:10]}"
            )

        ontology_summary.append(
            {
                "ontology": ontology,
                "annotated": len(annotated_ids),
                "wang_eligible": len(matrix_ids),
                "clustered": len(
                    ontology_clustered
                ),
                "ungrouped": len(
                    ontology_noise
                ),
                "clusters": sum(
                    1
                    for item in clusters
                    if item["ontology"] == ontology
                ),
            }
        )

    if require_interpretations:
        unused = sorted(
            set(interpretation_map).difference(
                used_interpretations
            )
        )
        if unused:
            raise ValueError(
                "Interpretations without corresponding "
                f"clusters: {unused}"
            )

    universe = set(
        raw["gene_id"].astype(str)
    )

    annotation_mask = raw[
        list(ONTOLOGIES.values())
    ].apply(
        lambda column: column.map(_present)
    ).any(axis=1)

    annotated_any = set(
        raw.loc[
            annotation_mask,
            "gene_id",
        ].astype(str)
    )

    eligible = set(
        genes["gene_id"].astype(str)
    )

    if not (
        clustered_any
        <= eligible
        <= annotated_any
        <= universe
    ):
        raise ValueError(
            "Coverage sets violate "
            "clustered <= eligible <= annotated <= universe"
        )

    funnel = {
        "without_go": len(
            universe - annotated_any
        ),
        "annotated_not_eligible": len(
            annotated_any - eligible
        ),
        "eligible_not_clustered": len(
            eligible - clustered_any
        ),
        "clustered_any_ontology": len(
            clustered_any
        ),
    }

    if sum(funnel.values()) != len(universe):
        raise AssertionError(
            "Coverage funnel does not sum to DEG universe"
        )

    payload = dict(base_payload)
    payload.pop("semantic_maps", None)

    payload.update(
        {
            "schema_version": (
                RAG_SCHEMA
                if require_interpretations
                else CLUSTER_SCHEMA
            ),
            "method": (
                "bilbo_semantic_clustering_and_rag_v2"
                if require_interpretations
                else "bilbo_semantic_clustering_v2"
            ),
            "coverage": {
                "total_degs": len(universe),
                "annotated_any_go": len(
                    annotated_any
                ),
                "wang_eligible": len(eligible),
                "clustered_any_ontology": len(
                    clustered_any
                ),
                "exclusive_funnel": funnel,
                "ontologies": ontology_summary,
            },
            "clusters": clusters,
            "ungrouped": ungrouped,
        }
    )

    return payload


def _esc(value: Any) -> str:
    return html.escape(
        "" if value is None else str(value),
        quote=True,
    )


def _pct(value: int, total: int) -> str:
    if total == 0:
        return "0.0%"
    return f"{100.0 * value / total:.1f}%"


def _table(
    headers: list[str],
    rows: list[list[Any]],
) -> str:
    head = "".join(
        f"<th>{_esc(header)}</th>"
        for header in headers
    )

    body = "".join(
        "<tr>"
        + "".join(
            f"<td>{_esc(value)}</td>"
            for value in row
        )
        + "</tr>"
        for row in rows
    )

    return (
        "<div class='scroll'><table>"
        f"<thead><tr>{head}</tr></thead>"
        f"<tbody>{body}</tbody>"
        "</table></div>"
    )



# BILBO_CLUSTER_GROUPED_GLOBAL_SEARCH_V1
def _search_blob(*values: Any) -> str:
    parts: list[str] = []

    def visit(value: Any) -> None:
        if value is None:
            return
        if isinstance(value, dict):
            for key, nested in value.items():
                parts.append(str(key))
                visit(nested)
            return
        if isinstance(value, (list, tuple, set)):
            for nested in value:
                visit(nested)
            return
        parts.append(str(value))

    for value in values:
        visit(value)

    return " ".join(" ".join(parts).split())

CLUSTER_BROWSER_CSS = '\n.cluster-filter-tools{\n  display:flex;\n  flex-wrap:wrap;\n  align-items:center;\n  gap:10px;\n  margin:14px 0 18px\n}\n.cluster-filter-tools input{\n  flex:1 1 420px;\n  min-width:240px;\n  padding:11px 13px;\n  border:1px solid var(--line);\n  border-radius:9px;\n  background:#fff;\n  color:var(--ink);\n  font:inherit\n}\n.cluster-filter-status{\n  color:var(--muted);\n  white-space:nowrap\n}\n#cluster-groups{\n  display:grid;\n  gap:12px\n}\n.cluster-group{\n  padding:0;\n  overflow:hidden\n}\n.cluster-group>summary{\n  cursor:pointer;\n  padding:15px;\n  font-weight:700;\n  color:var(--blue);\n  background:var(--soft)\n}\n.cluster-group-body{\n  display:grid;\n  gap:12px;\n  padding:12px\n}\n.cluster-group-body>.cluster{\n  margin:0\n}\n.cluster[hidden],\n.cluster-group[hidden]{\n  display:none!important\n}\n'
CLUSTER_BROWSER_SCRIPT = '\n<script>\n(() => {\n  const normalize = value =>\n    String(value || "")\n      .normalize("NFD")\n      .replace(/[\\u0300-\\u036f]/g, "")\n      .toLowerCase();\n\n  const cards = Array.from(\n    document.querySelectorAll(\n      "details.cluster[data-ontology][data-direction]"\n    )\n  );\n\n  if (!cards.length) return;\n\n  const specifications = [\n    ["BP", "up", "BP — Upregulated"],\n    ["BP", "down", "BP — Downregulated"],\n    ["MF", "up", "MF — Upregulated"],\n    ["MF", "down", "MF — Downregulated"],\n    ["CC", "up", "CC — Upregulated"],\n    ["CC", "down", "CC — Downregulated"]\n  ];\n\n  const host = document.createElement("section");\n  host.id = "cluster-groups";\n  cards[0].parentNode.insertBefore(host, cards[0]);\n\n  const records = [];\n\n  specifications.forEach(([ontology, direction, label]) => {\n    const selected = cards\n      .filter(card =>\n        card.dataset.ontology === ontology &&\n        card.dataset.direction === direction\n      )\n      .sort((left, right) => {\n        const sizeDifference =\n          Number(right.dataset.genes || 0) -\n          Number(left.dataset.genes || 0);\n\n        if (sizeDifference !== 0) return sizeDifference;\n\n        return (\n          Number(left.dataset.cluster || 0) -\n          Number(right.dataset.cluster || 0)\n        );\n      });\n\n    const group = document.createElement("details");\n    group.className = "cluster-group";\n\n    const totalGenes = selected.reduce(\n      (total, card) =>\n        total + Number(card.dataset.genes || 0),\n      0\n    );\n\n    const summary = document.createElement("summary");\n    summary.textContent =\n      `${label} — ${selected.length} clusters, ` +\n      `${totalGenes} genes`;\n\n    const body = document.createElement("div");\n    body.className = "cluster-group-body";\n\n    selected.forEach(card => body.appendChild(card));\n\n    if (!selected.length) {\n      const empty = document.createElement("p");\n      empty.className = "muted";\n      empty.textContent =\n        "No grouped cluster was generated for this category.";\n      body.appendChild(empty);\n    }\n\n    group.append(summary, body);\n    host.appendChild(group);\n\n    records.push({group, cards: selected});\n  });\n\n  let previousInput = Array.from(\n    document.querySelectorAll("input")\n  ).find(input =>\n    normalize(input.placeholder).includes("filter by gene")\n  );\n\n  let input;\n\n  if (previousInput) {\n    input = previousInput.cloneNode(true);\n    previousInput.replaceWith(input);\n  } else {\n    input = document.createElement("input");\n    input.type = "search";\n  }\n\n  input.id = "cluster-global-filter";\n  input.placeholder =\n    "Filter all content: genes, clusters, descriptions, " +\n    "LLM interpretations or RAG evidence";\n\n  const tools = document.createElement("div");\n  tools.className = "cluster-filter-tools";\n\n  const status = document.createElement("span");\n  status.className = "cluster-filter-status";\n\n  if (input.parentElement) {\n    input.parentElement.insertBefore(tools, input);\n  } else {\n    host.parentNode.insertBefore(tools, host);\n  }\n\n  tools.append(input, status);\n\n  const applyFilter = () => {\n    const terms = normalize(input.value)\n      .split(/\\s+/)\n      .filter(Boolean);\n\n    let totalVisible = 0;\n\n    records.forEach(record => {\n      let groupVisible = 0;\n\n      record.cards.forEach(card => {\n        const searchable = normalize(\n          `${card.dataset.search || ""} ${card.textContent}`\n        );\n\n        const matched = terms.every(term =>\n          searchable.includes(term)\n        );\n\n        card.hidden = !matched;\n\n        if (matched) {\n          groupVisible += 1;\n          totalVisible += 1;\n        }\n      });\n\n      record.group.hidden =\n        terms.length > 0 && groupVisible === 0;\n\n      if (terms.length > 0 && groupVisible > 0) {\n        record.group.open = true;\n      }\n    });\n\n    status.textContent =\n      `${totalVisible} of ${cards.length} clusters shown`;\n  };\n\n  input.addEventListener("input", applyFilter);\n  applyFilter();\n})();\n</script>\n'


# BILBO_REPORTS_SEPARATED_RAG_SEARCH_V1
RAG_BROWSER_CSS = '\n.rag-filter-tools{\n  display:flex;\n  flex-wrap:wrap;\n  align-items:center;\n  gap:10px;\n  margin:14px 0 18px\n}\n.rag-filter-tools input{\n  flex:1 1 440px;\n  min-width:240px;\n  padding:11px 13px;\n  border:1px solid var(--line);\n  border-radius:9px;\n  background:#fff;\n  color:var(--ink);\n  font:inherit\n}\n.rag-filter-status{\n  color:var(--muted);\n  white-space:nowrap\n}\n.rag-evidence[hidden]{\n  display:none!important\n}\n'
RAG_BROWSER_SCRIPT = '\n<script>\n(() => {\n  const normalize = value =>\n    String(value || "")\n      .replace(/_2f/gi, "/")\n      .normalize("NFD")\n      .replace(/[\\u0300-\\u036f]/g, "")\n      .toLowerCase();\n\n  const evidenceCards = Array.from(\n    document.querySelectorAll("details.rag-evidence")\n  );\n\n  const headings = Array.from(\n    document.querySelectorAll("h2")\n  );\n\n  const evidenceHeading = headings.find(\n    heading =>\n      normalize(heading.textContent) ===\n      "traceable rag evidence"\n  );\n\n  if (!evidenceHeading) return;\n\n  const tools = document.createElement("div");\n  tools.className = "rag-filter-tools";\n\n  const input = document.createElement("input");\n  input.type = "search";\n  input.id = "rag-global-filter";\n  input.placeholder =\n    "Search RAG material: genes, interpretations, " +\n    "sources, sections or article titles";\n  input.setAttribute(\n    "aria-label",\n    "Search all traceable RAG evidence"\n  );\n\n  const status = document.createElement("span");\n  status.className = "rag-filter-status";\n\n  tools.append(input, status);\n  evidenceHeading.insertAdjacentElement(\n    "afterend",\n    tools\n  );\n\n  const applyFilter = () => {\n    const terms = normalize(input.value)\n      .split(/\\s+/)\n      .filter(Boolean);\n\n    let visible = 0;\n\n    evidenceCards.forEach(card => {\n      const searchable = normalize(\n        `${card.dataset.search || ""} ${card.textContent}`\n      );\n\n      const matches = terms.every(term =>\n        searchable.includes(term)\n      );\n\n      card.hidden = !matches;\n\n      if (matches) {\n        visible += 1;\n\n        if (terms.length > 0) {\n          card.open = true;\n        }\n      }\n    });\n\n    status.textContent =\n      `${visible} of ${evidenceCards.length} evidence records shown`;\n  };\n\n  input.addEventListener("input", applyFilter);\n  applyFilter();\n})();\n</script>\n'

def render_html(
    payload: dict[str, Any],
    title: str,
) -> str:
    coverage = payload["coverage"]
    total = coverage["total_degs"]
    funnel = coverage["exclusive_funnel"]
    is_llm = (
        payload["schema_version"] == RAG_SCHEMA
    )

    css = """
:root{
  --ink:#172033;
  --muted:#667085;
  --line:#d7deea;
  --soft:#f4f7fb;
  --blue:#245b91;
  --card:#fff
}
*{box-sizing:border-box}
body{
  margin:0;
  background:#eef2f7;
  color:var(--ink);
  font:15px/1.48 system-ui,sans-serif
}
main{
  max-width:1500px;
  margin:auto;
  padding:26px
}
h1,h2,h3{line-height:1.18}
h2{
  margin-top:34px;
  border-bottom:2px solid var(--blue);
  padding-bottom:8px
}
.grid{
  display:grid;
  grid-template-columns:repeat(auto-fit,minmax(190px,1fr));
  gap:12px
}
.card,details,.panel{
  background:var(--card);
  border:1px solid var(--line);
  border-radius:12px;
  padding:15px;
  box-shadow:0 2px 7px #17203312
}
.value{
  font-size:28px;
  font-weight:750;
  color:var(--blue)
}
.muted{color:var(--muted)}
.bar{
  height:18px;
  background:#e5e7eb;
  border-radius:10px;
  overflow:hidden
}
.bar span{
  display:block;
  height:100%;
  background:var(--blue)
}
table{
  width:100%;
  border-collapse:collapse;
  font-size:13px
}
th,td{
  padding:8px;
  border-bottom:1px solid var(--line);
  text-align:left;
  vertical-align:top
}
th{
  position:sticky;
  top:0;
  background:var(--soft)
}
.scroll{
  overflow:auto;
  max-height:430px
}
.map{
  width:100%;
  min-width:520px;
  background:#fbfcfe;
  border:1px solid var(--line);
  border-radius:8px
}
.map line{stroke:#aab4c3}
.map text{
  font-size:12px;
  fill:var(--muted);
  text-anchor:middle
}
.rep{
  border-left:4px solid #f59e0b;
  padding-left:10px;
  margin:7px 0
}
.cluster{margin:14px 0}
summary{
  cursor:pointer;
  font-weight:700
}
@media print{
  body{background:#fff}
  main{max-width:none}
  .scroll{
    max-height:none;
    overflow:visible
  }
  .card,details,.panel{
    break-inside:avoid;
    box-shadow:none
  }
}
"""

    output = [
        "<!doctype html><html lang='en'>",
        "<head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width'>",
        # BILBO_INVISIBLE_SCHEMA_META_V1
        (
            "<meta name='bilbo-schema' content='"
            f"{_esc(payload['schema_version'])}'>"
        ),
        f"<title>{_esc(title)}</title>",
        f"<style>{css}{CLUSTER_BROWSER_CSS}"f"{RAG_BROWSER_CSS}</style>""</head><body><main>",
        f"<h1>{_esc(title)}</h1>",
    ]

    cards = [
        (total, "DEGs"),
        (
            coverage["annotated_any_go"],
            "GO annotated",
        ),
        (
            coverage["wang_eligible"],
            "Wang eligible",
        ),
        (
            coverage[
                "clustered_any_ontology"
            ],
            "Clustered in at least one ontology",
        ),
    ]

    output.append("<section class='grid'>")
    for value, label in cards:
        output.append(
            "<div class='card'>"
            f"<div class='value'>{value}</div>"
            f"<strong>{_esc(label)}</strong>"
            f"<div class='muted'>{_pct(value,total)}</div>"
            "</div>"
        )
    output.append("</section>")

    output.append(
        "<h2>Coverage funnel</h2>"
        "<div class='panel'>"
    )

    funnel_labels = {
        "without_go": "No GO annotation",
        "annotated_not_eligible": (
            "Annotated, not Wang eligible"
        ),
        "eligible_not_clustered": (
            "Eligible, never clustered"
        ),
        "clustered_any_ontology": (
            "Clustered in at least one ontology"
        ),
    }

    for key, label in funnel_labels.items():
        value = funnel[key]
        width = (
            100.0 * value / total
            if total
            else 0.0
        )

        output.append(
            f"<p><strong>{_esc(label)}</strong> - "
            f"{value} ({_pct(value,total)})</p>"
            "<div class='bar'>"
            f"<span style='width:{width:.2f}%'></span>"
            "</div>"
        )

    output.append("</div>")

    output.append(
        "<h2>Ontology overview</h2>"
        "<section class='grid'>"
    )

    for item in coverage["ontologies"]:
        output.append(
            "<div class='card'>"
            f"<h3>{item['ontology']}</h3>"
            f"<p>Annotated: <strong>{item['annotated']}</strong></p>"
            f"<p>Wang matrix: <strong>{item['wang_eligible']}</strong></p>"
            f"<p>Clustered: <strong>{item['clustered']}</strong></p>"
            f"<p>Noise (-1): <strong>{item['ungrouped']}</strong></p>"
            f"<p>Clusters: <strong>{item['clusters']}</strong></p>"
            "</div>"
        )

    output.append("</section>")

    output.append(
        "<h2>Interpreted semantic clusters</h2>"
        if is_llm
        else "<h2>Semantic clusters and their genes</h2>"
    )

    rag_by_gene: dict[str, list[dict[str, Any]]] = {}

    for evidence_item in payload.get(
        "rag_gene_evidence",
        [],
    ):
        evidence_gene = str(
            evidence_item.get("gene_id") or ""
        )

        if evidence_gene:
            rag_by_gene.setdefault(
                evidence_gene,
                [],
            ).append(evidence_item)

    for cluster in payload["clusters"]:
        cluster_gene_ids = {
            str(gene.get("gene_id") or "")
            for gene in cluster["genes"]
            if gene.get("gene_id")
        }

        related_rag_evidence = [
            evidence
            for gene_id in cluster_gene_ids
            for evidence in rag_by_gene.get(
                gene_id,
                [],
            )
        ]

        cluster_search_text = _search_blob(
            cluster,
            related_rag_evidence,
        )

        representatives = []

        for item in cluster["representatives"]:
            representatives.append(
                "<div class='rep'>"
                f"<strong>{_esc(item['gene_id'])}</strong> - "
                "centrality "
                f"{_esc(round(item['representative_centrality'],4))}; "
                "silhouette "
                f"{_esc(item.get('cluster_silhouette'))}; "
                "|log2FC| "
                f"{_esc(round(item['abs_log2_fold_change'],4))}"
                "</div>"
            )

        rows = [
            [
                gene.get("gene_id"),
                gene.get("Uniprot gene names"),
                gene.get("log2FoldChange"),
                gene.get("padj"),
                gene.get("cluster_silhouette"),
                gene.get(
                    "representative_centrality"
                ),
                gene.get(
                    ONTOLOGIES[
                        cluster["ontology"]
                    ]
                ),
            ]
            for gene in cluster["genes"]
        ]

        interpretation = ""

        if cluster.get("interpretation"):
            interpretation = (
                "<h3>LLM interpretation</h3>"
                f"<p>{_esc(cluster['interpretation'])}</p>"
            )

        output.append(
            "<details class='cluster' "
            f"data-ontology='{_esc(cluster['ontology'])}' "
            f"data-direction='{_esc(cluster['direction'])}' "
            f"data-cluster='{_esc(cluster['cluster'])}' "
            f"data-genes='{_esc(cluster['n_genes'])}' "
            f"data-search='{_esc(cluster_search_text)}'>"
            "<summary>"
            f"{_esc(cluster['cluster_id'])} - "
            f"{cluster['n_genes']} genes - "
            "mean silhouette "
            f"{_esc(cluster['mean_silhouette'])}"
            "</summary>"
            f"{interpretation}"
            "<h3>Top mathematical representatives</h3>"
            + "".join(representatives)
            + "<h3>All genes in this cluster</h3>"
            + _table(
                [
                    "Gene",
                    "UniProt name",
                    "log2FC",
                    "padj",
                    "Silhouette",
                    "Centrality",
                    "GO annotation",
                ],
                rows,
            )
            + "</details>"
        )

    output.append(
        "<h2>Ungrouped genes (cluster -1)</h2>"
        "<p class='muted'>"
        "These genes are shown for transparency and are "
        "not interpreted as a coherent biological cluster."
        "</p>"
    )

    for group in payload["ungrouped"]:
        rows = [
            [
                gene.get("gene_id"),
                gene.get("Uniprot gene names"),
                gene.get("log2FoldChange"),
                gene.get("padj"),
                gene.get(
                    ONTOLOGIES[
                        group["ontology"]
                    ]
                ),
            ]
            for gene in group["genes"]
        ]

        output.append(
            "<details>"
            "<summary>"
            f"{group['ontology']}:{group['direction']} - "
            f"{group['n_genes']} ungrouped genes"
            "</summary>"
            + _table(
                [
                    "Gene",
                    "UniProt name",
                    "log2FC",
                    "padj",
                    "GO annotation",
                ],
                rows,
            )
            + "</details>"
        )

    if is_llm:
        output.append(
            "<h2>Cross-ontology prioritization</h2>"
            "<p>"
            "Representatives are ranked by Wang centrality, "
            "cluster silhouette, absolute log2 fold change "
            "and gene ID. RAG is restricted to genes that "
            "represent clusters in at least two ontologies."
            "</p>"
        )

        prioritized_rows = [
            [
                item.get("rank"),
                item.get("gene_id"),
                item.get("primary_name"),
                item.get(
                    "represented_ontologies"
                ),
                item.get(
                    "represented_clusters"
                ),
                item.get(
                    "centrality_score"
                ),
                item.get(
                    "min_cluster_quality"
                ),
                item.get(
                    "selected_for_search"
                ),
            ]
            for item in payload.get(
                "prioritized_genes",
                [],
            )
        ]

        output.append(
            _table(
                [
                    "Rank",
                    "Gene",
                    "Name",
                    "Ontologies",
                    "Clusters",
                    "Centrality",
                    "Minimum quality",
                    "RAG selected",
                ],
                prioritized_rows,
            )
        )

        output.append(
            "<h2>Traceable RAG evidence</h2>"
        )

        evidence = payload.get(
            "rag_gene_evidence",
            [],
        )

        if not evidence:
            output.append(
                "<p>No representative met the "
                "multi-ontology RAG rule.</p>"
            )

        for item in evidence:
            chunk_rows = [
                [
                    chunk.get("citation_id")
                    or chunk.get("chunk_id"),
                    str(
                        chunk.get("source") or ""
                    ).replace(
                        "_2F",
                        "/",
                    ).replace(
                        "_2f",
                        "/",
                    ),
                    chunk.get("section"),
                    chunk.get("article_title"),
                ]
                for chunk in item.get(
                    "chunks",
                    [],
                )
            ]

            rag_search_text = _search_blob(
                item
            ).replace(
                "_2F",
                "/",
            ).replace(
                "_2f",
                "/",
            )

            output.append(
                "<details class='rag-evidence' "
                f"data-search='{_esc(rag_search_text)}'>"
                "<summary>"
                f"{_esc(item.get('gene_id'))} - "
                f"{_esc(item.get('primary_name'))}"
                "</summary>"
                f"<p>{_esc(item.get('interpretation'))}</p>"
                + _table(
                    [
                        "Citation",
                        "Source",
                        "Section",
                        "Article",
                    ],
                    chunk_rows,
                )
                + "</details>"
            )

    output.append(
        "<h2>Methodological contract</h2>"
        "<div class='panel'>"
        "<p>"
        "Noise label -1 is never interpreted as a biological "
        "cluster. Cluster membership, Wang matrices, gene "
        "metadata and LLM interpretations are cross-validated "
        "before publication."
        "</p></div>"
        + CLUSTER_BROWSER_SCRIPT
        + RAG_BROWSER_SCRIPT
        + "</main></body></html>"
    )

    rendered = "".join(output)

    # Remove the methodological contract from both reports.
    method_start = rendered.find(
        "<h2>Methodological contract</h2>"
    )

    if method_start >= 0:
        method_end = rendered.find(
            "<script>",
            method_start,
        )

        if method_end < 0:
            raise ValueError(
                "Unable to delimit methodological contract"
            )

        rendered = (
            rendered[:method_start]
            + rendered[method_end:]
        )

    # The RAG report contains only information that is
    # specific to prioritization and traceable evidence.
    if is_llm:
        duplicated_start = rendered.find(
            "<section class='grid'>"
        )
        rag_specific_start = rendered.find(
            "<h2>Cross-ontology prioritization</h2>"
        )

        if (
            duplicated_start < 0
            or rag_specific_start < 0
            or rag_specific_start <= duplicated_start
        ):
            raise ValueError(
                "Unable to separate clustering and RAG sections"
            )

        rendered = (
            rendered[:duplicated_start]
            + rendered[rag_specific_start:]
        )

    return rendered


def render_markdown(
    payload: dict[str, Any],
    title: str,
) -> str:
    coverage = payload["coverage"]

    lines = [
        f"# {title}",
        "",
        f"Schema: `{payload['schema_version']}`",
        "",
        "## Coverage",
        "",
        f"- Unique DEGs: {coverage['total_degs']}",
        (
            "- GO annotated: "
            f"{coverage['annotated_any_go']} "
            f"({_pct(coverage['annotated_any_go'],coverage['total_degs'])})"
        ),
        (
            "- Wang eligible: "
            f"{coverage['wang_eligible']} "
            f"({_pct(coverage['wang_eligible'],coverage['total_degs'])})"
        ),
        (
            "- Clustered in at least one ontology: "
            f"{coverage['clustered_any_ontology']} "
            f"({_pct(coverage['clustered_any_ontology'],coverage['total_degs'])})"
        ),
        "",
        "## Semantic clusters",
        "",
    ]

    for cluster in payload["clusters"]:
        lines.extend(
            [
                (
                    f"### {cluster['cluster_id']} "
                    f"({cluster['n_genes']} genes)"
                ),
                "",
            ]
        )

        if cluster.get("interpretation"):
            lines.extend(
                [
                    str(cluster["interpretation"]),
                    "",
                ]
            )

        representative_names = ", ".join(
            item["gene_id"]
            for item in cluster[
                "representatives"
            ]
        )

        lines.extend(
            [
                (
                    "Top mathematical representatives: "
                    + representative_names
                ),
                "",
                (
                    "| Gene | UniProt name | log2FC | padj "
                    "| Silhouette | Centrality |"
                ),
                "|---|---|---:|---:|---:|---:|",
            ]
        )

        for gene in cluster["genes"]:
            name = str(
                gene.get("Uniprot gene names") or ""
            ).replace("|", "\\|")

            lines.append(
                f"| {gene.get('gene_id')} "
                f"| {name} "
                f"| {gene.get('log2FoldChange')} "
                f"| {gene.get('padj')} "
                f"| {gene.get('cluster_silhouette')} "
                f"| {gene.get('representative_centrality')} |"
            )

        lines.append("")

    lines.extend(
        [
            "## Ungrouped genes",
            "",
            (
                "Label -1 is reported for transparency "
                "and is not biologically interpreted."
            ),
            "",
        ]
    )

    for group in payload["ungrouped"]:
        lines.extend(
            [
                (
                    f"### {group['ontology']}:"
                    f"{group['direction']} "
                    f"({group['n_genes']} genes)"
                ),
                "",
                "| Gene | UniProt name | log2FC | padj |",
                "|---|---|---:|---:|",
            ]
        )

        for gene in group["genes"]:
            name = str(
                gene.get("Uniprot gene names") or ""
            ).replace("|", "\\|")

            lines.append(
                f"| {gene.get('gene_id')} "
                f"| {name} "
                f"| {gene.get('log2FoldChange')} "
                f"| {gene.get('padj')} |"
            )

        lines.append("")

    lines.extend(
        [
            "## Traceable RAG evidence",
            "",
        ]
    )

    for item in payload.get(
        "rag_gene_evidence",
        [],
    ):
        lines.extend(
            [
                (
                    f"### {item.get('gene_id')} - "
                    f"{item.get('primary_name')}"
                ),
                "",
                str(
                    item.get(
                        "interpretation",
                        "",
                    )
                ),
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def generate_clustering_html(
    clustering_dir: Path,
    title: str,
) -> str:
    payload = build_report_payload(
        {},
        clustering_dir,
        require_interpretations=False,
    )

    rendered = render_html(
        payload,
        title,
    )

    if (
        CLUSTER_SCHEMA not in rendered
        or not payload["clusters"]
    ):
        raise ValueError(
            "Clustering report failed strict validation"
        )

    return rendered


def generate_report_bundle(
    base_payload: dict[str, Any],
    clustering_dir: Path,
    output_dir: Path,
    title: str,
) -> dict[str, str]:
    if not output_dir.is_dir():
        raise FileNotFoundError(
            f"Existing LLM output directory not found: {output_dir}"
        )

    payload = build_report_payload(
        base_payload,
        clustering_dir,
        require_interpretations=True,
    )

    html_text = render_html(
        payload,
        title,
    )
    markdown_text = render_markdown(
        payload,
        title,
    )

    if (
        RAG_SCHEMA not in html_text
        or not payload["clusters"]
    ):
        raise ValueError(
            "RAG report failed strict validation"
        )

    targets = {
        "json": output_dir / "data.json",
        "report": output_dir / "report.md",
        "html": output_dir / "report.html",
    }

    staged = {}
    backups = {}
    published = set()

    try:
        for key, target in targets.items():
            handle = tempfile.NamedTemporaryFile(
                mode="w",
                prefix=f".{target.name}.",
                suffix=".tmp",
                dir=output_dir,
                delete=False,
            )
            staged[key] = Path(handle.name)
            handle.close()

        staged["json"].write_text(
            json.dumps(
                payload,
                indent=2,
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )

        staged["report"].write_text(
            markdown_text,
            encoding="utf-8",
        )

        staged["html"].write_text(
            html_text,
            encoding="utf-8",
        )

        checked = json.loads(
            staged["json"].read_text(
                encoding="utf-8"
            )
        )

        if checked.get(
            "schema_version"
        ) != RAG_SCHEMA:
            raise ValueError(
                "Staged JSON schema validation failed"
            )

        if staged["html"].stat().st_size < 5000:
            raise ValueError(
                "Staged HTML is unexpectedly small"
            )

        if staged["report"].stat().st_size < 500:
            raise ValueError(
                "Staged Markdown is unexpectedly small"
            )

        for key, target in targets.items():
            if target.exists():
                handle = tempfile.NamedTemporaryFile(
                    prefix=f".{target.name}.",
                    suffix=".old",
                    dir=output_dir,
                    delete=False,
                )
                backup = Path(handle.name)
                handle.close()

                shutil.copy2(
                    target,
                    backup,
                )
                backups[key] = backup

            os.replace(
                staged[key],
                target,
            )
            published.add(key)

    except Exception:
        for key, target in targets.items():
            backup = backups.get(key)

            if backup and backup.exists():
                os.replace(
                    backup,
                    target,
                )
            elif (
                key in published
                and target.exists()
            ):
                target.unlink()

        raise

    finally:
        for path in [
            *staged.values(),
            *backups.values(),
        ]:
            if path.exists():
                path.unlink()

    return {
        key: str(path)
        for key, path in targets.items()
    }
