from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run only BILBO semantic clustering and local RAG from an existing DEG workbook."
    )
    parser.add_argument("--deg-xlsx", required=True, help="Path to an existing DEG.xlsx workbook.")
    parser.add_argument("--sheet", required=True, help="Workbook sheet/contrast to process.")
    parser.add_argument(
        "--output-dir",
        default="/output",
        help="Directory that will receive clustering and RAG artifacts.",
    )
    parser.add_argument(
        "--run-id",
        default="standalone",
        help="Stable run identifier used below the output directory.",
    )
    parser.add_argument("--skip-rag", action="store_true", help="Run semantic clustering only.")
    return parser.parse_args()


def safe_name(value: str, *, field: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-")
    if not normalized:
        raise ValueError(f"{field} must contain at least one alphanumeric character")
    return normalized


def run(args: argparse.Namespace) -> dict[str, Any]:
    deg_xlsx = Path(args.deg_xlsx).expanduser().resolve()
    if not deg_xlsx.is_file():
        raise FileNotFoundError(f"DEG workbook not found: {deg_xlsx}")

    output_root = Path(args.output_dir).expanduser().resolve()
    run_id = safe_name(args.run_id, field="run-id")
    sheet_dir = safe_name(args.sheet, field="sheet")
    users_root = output_root / "runs"
    os.environ["USERS_ROOT"] = str(users_root)

    # Imports happen after USERS_ROOT is configured so the production modules
    # resolve every generated artifact inside the standalone output directory.
    from . import clustering
    from . import llm

    clustering_dir = users_root / run_id / "clustering" / sheet_dir
    clustering_dir.mkdir(parents=True, exist_ok=True)
    clustering_result = clustering.cluster_pipeline(
        str(deg_xlsx),
        sheet_name=args.sheet,
        img_final_path=str(clustering_dir / "cluster.png"),
        img_metrics_path=str(clustering_dir / "metrics.png"),
        clusters_json_path=str(clustering_dir / "clusters.json"),
    )

    result: dict[str, Any] = {
        "run_id": run_id,
        "sheet": args.sheet,
        "deg_xlsx": str(deg_xlsx),
        "clustering": clustering_result,
        "rag": None,
    }
    if not args.skip_rag:
        rag_dir = users_root / run_id / "llm" / sheet_dir
        result["rag"] = llm.run_llm(
            file_path=None,
            sheet_name=sheet_dir,
            out_dir=str(rag_dir),
            user_id=run_id,
        )

    manifest = users_root / run_id / "run.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    result["manifest"] = str(manifest)
    return result


def main() -> int:
    result = run(parse_args())
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
