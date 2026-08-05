from __future__ import annotations

import csv
import json
import urllib.request
from pathlib import Path

CLUSTERS_DIR = Path("clusters")
OUTPUT_FILE = CLUSTERS_DIR / "interpretations.csv"

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
MODEL = "gemma4:e4b"
TIMEOUT = 600
NUM_CTX = 32768

ONTOLOGIES = {
    "BP": "Uniprot BP",
    "MF": "Uniprot MF",
    "CC": "Uniprot CC",
}
DIRECTIONS = {
    "down": "downregulated",
    "up": "upregulated",
}
OUTPUT_COLUMNS = ["ontology", "direction", "cluster", "n_genes", "interpretation"]

FOCUS = {
    "BP": (
        "Focus on the shared biological process: which process, response, "
        "pathway, or cellular event connects the cluster."
    ),
    "MF": (
        "Focus on the shared molecular function: which biochemical activity, "
        "binding activity, catalysis, or transport function connects the cluster."
    ),
    "CC": (
        "Focus on the shared cellular localization: which compartment, "
        "membrane, organelle, or cellular complex connects the cluster. Do not "
        "force a shared biological function when the functions are diverse."
    ),
}


def build_prompt(ontology: str) -> str:
    return (
        "Summarize the central theme of this cluster in English, using one "
        "clear and brief sentence. "
        f"{FOCUS[ontology]} "
        'Use only the provided "function" and "go" fields. Do not cite genes, '
        "do not invent information, and mention heterogeneity only if there is "
        "no clear central theme."
    )


def call_model(
    ontology: str,
    evidence: list[dict[str, str]],
    *,
    ollama_url: str = OLLAMA_URL,
    model: str = MODEL,
    timeout: int = TIMEOUT,
    num_ctx: int = NUM_CTX,
) -> str:
    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": build_prompt(ontology)},
            {
                "role": "user",
                "content": json.dumps(evidence, ensure_ascii=False),
            },
        ],
        "options": {"num_ctx": num_ctx, "temperature": 0.2},
    }
    request = urllib.request.Request(
        ollama_url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        result = json.load(response)
    return result["message"]["content"].strip()


def completed_clusters(output_file: Path = OUTPUT_FILE) -> set[tuple[str, str, int]]:
    if not output_file.exists():
        return set()
    with output_file.open(newline="", encoding="utf-8") as handle:
        return {(row["ontology"], row["direction"], int(row["cluster"])) for row in csv.DictReader(handle)}


def run_cluster_interpretation(
    clusters_dir: Path,
    output_file: Path,
    *,
    ollama_url: str = OLLAMA_URL,
    model: str = MODEL,
    timeout: int = TIMEOUT,
    num_ctx: int = NUM_CTX,
) -> dict[str, object]:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    completed = completed_clusters(output_file)
    interpreted = 0

    with output_file.open("a", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=OUTPUT_COLUMNS)
        if output_file.stat().st_size == 0:
            writer.writeheader()

        for ontology, go_column in ONTOLOGIES.items():
            for direction, filename_prefix in DIRECTIONS.items():
                input_file = clusters_dir / ontology / f"{filename_prefix}_clusters.csv"
                with input_file.open(newline="", encoding="utf-8") as handle:
                    rows = list(csv.DictReader(handle))

                clusters = sorted({int(row["cluster"]) for row in rows} - {-1})
                for cluster in clusters:
                    key = (ontology, direction, cluster)
                    if key in completed:
                        continue

                    evidence = [
                        {
                            "function": row["function"].strip(),
                            "go": row[go_column].strip(),
                        }
                        for row in rows
                        if int(row["cluster"]) == cluster
                    ]
                    print(f"{ontology} {direction} cluster {cluster}")
                    interpretation = call_model(
                        ontology,
                        evidence,
                        ollama_url=ollama_url,
                        model=model,
                        timeout=timeout,
                        num_ctx=num_ctx,
                    )
                    writer.writerow(
                        {
                            "ontology": ontology,
                            "direction": direction,
                            "cluster": cluster,
                            "n_genes": len(evidence),
                            "interpretation": interpretation,
                        }
                    )
                    output.flush()
                    completed.add(key)
                    interpreted += 1
    return {"output": str(output_file), "interpreted_clusters": interpreted, "model": model}


def main() -> None:
    run_cluster_interpretation(CLUSTERS_DIR, OUTPUT_FILE)


if __name__ == "__main__":
    main()
