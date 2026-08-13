from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def run_checked(arguments: list[str]) -> None:
    print(f"Running: {' '.join(arguments)}", flush=True)
    subprocess.run(arguments, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sequentially prepare every automated artifact required before BILBO expert review."
    )
    parser.add_argument("--genes", type=Path, default=Path("/prototype/outputs/prioritized_genes.csv"))
    parser.add_argument(
        "--cluster-interpretations",
        type=Path,
        default=Path("/prototype/clusters/interpretations.csv"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("/workspace/benchmarks/rag_evaluation/work"),
    )
    parser.add_argument("--query-limit", type=int, default=13)
    parser.add_argument("--batch-size", type=int, default=4)
    args = parser.parse_args()

    python = sys.executable
    run_checked(
        [
            python,
            "-m",
            "benchmarks.rag_evaluation.run_retrieval",
            "--genes",
            str(args.genes),
            "--output-dir",
            str(args.output_dir),
            "--query-limit",
            str(args.query_limit),
            "--top-k",
            "10",
            "--candidate-k",
            "40",
            "--batch-size",
            str(args.batch_size),
        ]
    )

    interpretation_dir = args.output_dir / "current_interpretations"
    run_checked(
        [
            python,
            "-m",
            "benchmarks.rag_evaluation.run_interpretations",
            "--genes",
            str(args.genes),
            "--cluster-interpretations",
            str(args.cluster_interpretations),
            "--output-dir",
            str(interpretation_dir),
            "--gene-limit",
            str(args.query_limit),
        ]
    )

    required = {
        "retrieval_annotations": args.output_dir / "relevance_annotations.csv",
        "retrieval_rankings": args.output_dir / "rankings.csv",
        "retrieval_manifest": args.output_dir / "run_manifest.json",
        "interpretation_annotations": interpretation_dir / "interpretation_annotations.csv",
        "rag_outputs": interpretation_dir / "rag_gene_evidence.json",
        "interpretation_manifest": interpretation_dir / "interpretation_run_manifest.json",
    }
    missing = [str(path) for path in required.values() if not path.is_file()]
    if missing:
        raise RuntimeError(f"Automated preparation ended with missing artifacts: {missing}")
    readiness = {
        "status": "ready_for_expert_review",
        "human_actions_required": [
            "Assign relevance_grade 0/1/2 to every retrieval row.",
            "Assign claim_label and citations_correct to every interpretation claim.",
        ],
        "artifacts": {key: str(path) for key, path in required.items()},
    }
    readiness_path = args.output_dir / "READY_FOR_EXPERT_REVIEW.json"
    readiness_path.write_text(json.dumps(readiness, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    readiness_path.chmod(0o666)
    print(json.dumps(readiness, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
