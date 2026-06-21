from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark BILBO clustering and LLM/RAG stages from an existing DEG.xlsx file. "
            "Intermediate files are deleted; only the timing JSON is preserved."
        )
    )
    parser.add_argument("--deg-xlsx", required=True, help="Path to an existing DEG.xlsx workbook.")
    parser.add_argument("--output", default="benchmarks/clustering_llm_times.json", help="Timing JSON output path.")
    parser.add_argument("--sheets", nargs="*", default=None, help="Optional sheet names to benchmark. Defaults to all sheets.")
    parser.add_argument("--repeats", type=int, default=1, help="Number of times to repeat each selected sheet.")
    parser.add_argument("--skip-llm", action="store_true", help="Run clustering only.")
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep temporary benchmark files for debugging. By default, all intermediate files are deleted.",
    )
    return parser.parse_args()


def now_ms() -> int:
    return int(time.perf_counter() * 1000)


def elapsed_ms(start_ms: int) -> int:
    return now_ms() - start_ms


def load_sheet_names(deg_xlsx: Path) -> list[str]:
    try:
        import openpyxl
    except ImportError as exc:
        raise RuntimeError("openpyxl is required to inspect DEG.xlsx sheets.") from exc

    workbook = openpyxl.load_workbook(str(deg_xlsx), read_only=True)
    try:
        return list(workbook.sheetnames)
    finally:
        workbook.close()


def prepare_import_paths(project_root: Path, benchmark_users_root: Path) -> None:
    os.environ["USERS_ROOT"] = str(benchmark_users_root)
    scripts_dir = project_root / "app" / "backend" / "scripts"
    app_dir = project_root / "app"
    for path in [str(scripts_dir), str(app_dir), str(project_root)]:
        if path not in sys.path:
            sys.path.insert(0, path)


def import_clustering_module(project_root: Path, benchmark_users_root: Path):
    prepare_import_paths(project_root, benchmark_users_root)
    import clustering as clustering_script  # type: ignore

    return clustering_script


def import_llm_module(project_root: Path, benchmark_users_root: Path):
    prepare_import_paths(project_root, benchmark_users_root)
    import llm as llm_script  # type: ignore

    return llm_script


def run_clustering(clustering_script: Any, deg_xlsx: Path, sheet: str, out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    start = now_ms()
    try:
        result = clustering_script.cluster_pipeline(
            str(deg_xlsx),
            sheet_name=sheet,
            img_final_path=str(out_dir / "cluster.png"),
            img_metrics_path=str(out_dir / "metrics.png"),
            clusters_json_path=str(out_dir / "clusters.json"),
        )
        return {
            "status": "completed",
            "duration_ms": elapsed_ms(start),
            "clusters_json": str(out_dir / "clusters.json"),
            "cluster_count": len(result.get("clusters", {})) if isinstance(result, dict) else None,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "failed",
            "duration_ms": elapsed_ms(start),
            "error": str(exc),
        }


def run_llm(llm_script: Any, user_id: str, sheet: str, out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    start = now_ms()
    try:
        result = llm_script.run_llm(file_path=None, sheet_name=sheet, out_dir=str(out_dir), user_id=user_id)
        return {
            "status": "completed",
            "duration_ms": elapsed_ms(start),
            "model_used": result.get("model_used"),
            "report": result.get("report"),
            "json": result.get("json"),
            "vector_db_bootstrap": result.get("vector_db_bootstrap"),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "failed",
            "duration_ms": elapsed_ms(start),
            "error": str(exc),
        }


def main() -> int:
    args = parse_args()
    project_root = Path(__file__).resolve().parents[1]
    deg_xlsx = Path(args.deg_xlsx).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()

    if not deg_xlsx.exists():
        raise FileNotFoundError(f"DEG workbook not found: {deg_xlsx}")
    if args.repeats < 1:
        raise ValueError("--repeats must be >= 1")

    all_sheets = load_sheet_names(deg_xlsx)
    selected_sheets = args.sheets or all_sheets
    missing = [sheet for sheet in selected_sheets if sheet not in all_sheets]
    if missing:
        raise ValueError(f"Sheets not found in DEG workbook: {', '.join(missing)}")

    benchmark_id = f"benchmark_{uuid.uuid4().hex}"
    project_users_dir = project_root / "users" / benchmark_id

    total_start = now_ms()
    report: dict[str, Any] = {
        "deg_xlsx": str(deg_xlsx),
        "sheets": selected_sheets,
        "repeats": args.repeats,
        "skip_llm": bool(args.skip_llm),
        "runs": [],
    }

    temp_context = tempfile.TemporaryDirectory(prefix="bilbo_benchmark_")
    temp_root = Path(temp_context.name)
    try:
        clustering_script = import_clustering_module(project_root, temp_root)
        llm_script = None if args.skip_llm else import_llm_module(project_root, temp_root)

        for repeat in range(1, args.repeats + 1):
            for sheet in selected_sheets:
                safe_sheet = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in sheet)
                cluster_dir = project_users_dir / "clustering" / safe_sheet
                llm_dir = project_users_dir / "llm" / safe_sheet

                run_record: dict[str, Any] = {
                    "repeat": repeat,
                    "sheet": sheet,
                    "clustering": run_clustering(clustering_script, deg_xlsx, sheet, cluster_dir),
                }

                if not args.skip_llm:
                    if run_record["clustering"]["status"] == "completed":
                        if llm_script is None:
                            raise RuntimeError("LLM module was not imported.")
                        run_record["llm"] = run_llm(llm_script, benchmark_id, safe_sheet, llm_dir)
                    else:
                        run_record["llm"] = {
                            "status": "skipped",
                            "reason": "clustering failed",
                        }

                report["runs"].append(run_record)

        report["total_duration_ms"] = elapsed_ms(total_start)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Timing report written to: {output}")
        return 0
    finally:
        if not args.keep_temp:
            shutil.rmtree(project_users_dir, ignore_errors=True)
            temp_context.cleanup()
        else:
            print(f"Temporary users directory kept at: {project_users_dir}")
            print(f"Temporary benchmark root kept at: {temp_root}")


if __name__ == "__main__":
    raise SystemExit(main())
