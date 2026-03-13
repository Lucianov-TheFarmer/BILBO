from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional, Tuple
import logging

from sqlalchemy.orm import Session

from ..core.settings import settings
from ..db.database import SessionLocal
from ..db.models import Artifact, AuditLog, PipelineJob, SampleStage
from ..schemas.common import PipelineStatus
from ..scripts import clustering as clustering_script
from ..scripts import llm as llm_script
from ..services.job_service import add_artifact, set_job_finished, set_job_running
from ..utils_paths import ensure_safe_component
from .celery_app import celery_app

logger = logging.getLogger(__name__)
RETRYABLE_EXCEPTIONS = (TimeoutError, OSError, ConnectionError)


def _run(cmd: list[str], cwd: Optional[str] = None, timeout: Optional[int] = None) -> Tuple[int, str, str]:
    process = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        stdout, stderr = process.communicate()
        raise TimeoutError(f"Timed out after {timeout}s running: {' '.join(cmd)}") from exc
    return process.returncode, stdout, stderr


def _job_payload(db: Session, job_id: str) -> tuple[PipelineJob, dict[str, Any]]:
    job = db.query(PipelineJob).filter(PipelineJob.id == job_id).first()
    if job is None:
        raise ValueError(f"Job {job_id} not found")
    return job, (job.payload or {})


def _abs_users(*parts: str) -> Path:
    root = Path(settings.users_root)
    return (root.joinpath(*parts)).resolve()


def _duration_ms(started_at: Optional[datetime], finished_at: Optional[datetime]) -> Optional[int]:
    if not started_at or not finished_at:
        return None
    return int((finished_at - started_at).total_seconds() * 1000)


def _enforce_retention(db: Session, user_id: int) -> None:
    now = datetime.now(timezone.utc)

    if settings.artifact_retention_days > 0:
        artifacts_cutoff = now - timedelta(days=settings.artifact_retention_days)
        old_artifacts = (
            db.query(Artifact)
            .filter(Artifact.user_id == user_id, Artifact.created_at < artifacts_cutoff)
            .all()
        )
        user_root = _abs_users(str(user_id))
        for artifact in old_artifacts:
            try:
                path = Path(artifact.path).resolve()
                if path.exists() and path.is_file():
                    try:
                        path.relative_to(user_root)
                        path.unlink(missing_ok=True)
                    except ValueError:
                        pass
            except Exception:
                pass
            db.delete(artifact)
        if old_artifacts:
            db.commit()

    if settings.audit_retention_days > 0:
        audit_cutoff = now - timedelta(days=settings.audit_retention_days)
        deleted = (
            db.query(AuditLog)
            .filter(AuditLog.user_id == user_id, AuditLog.created_at < audit_cutoff)
            .delete(synchronize_session=False)
        )
        if deleted:
            db.commit()

    if settings.log_retention_days > 0:
        logs_dir = Path("/app/backend/logs")
        if logs_dir.exists():
            logs_cutoff = (now - timedelta(days=settings.log_retention_days)).timestamp()
            for log_file in logs_dir.glob("*.log"):
                try:
                    if log_file.stat().st_mtime < logs_cutoff:
                        log_file.unlink(missing_ok=True)
                except Exception:
                    continue


def _finalize_job(
    db: Session,
    *,
    job_id: str,
    stage: str,
    user_id: int,
    status: PipelineStatus,
    result: Optional[dict[str, Any]] = None,
    error_message: Optional[str] = None,
    exit_code: Optional[int] = None,
) -> None:
    finished = set_job_finished(db, job_id, status, result=result, error_message=error_message)
    logger.info(
        json.dumps(
            {
                "event": "job_finished",
                "job_id": job_id,
                "user_id": user_id,
                "stage": stage,
                "status": finished.status,
                "duration_ms": _duration_ms(finished.started_at, finished.finished_at),
                "exit_code": exit_code,
            }
        )
    )
    _enforce_retention(db, user_id)


@celery_app.task(bind=True, name="pipeline.execute")
def execute_pipeline_job(self, job_id: str):
    db = SessionLocal()
    stage = "unknown"
    user_id = -1
    started_at = time.monotonic()
    try:
        job, payload = _job_payload(db, job_id)
        if job.status == PipelineStatus.CANCELED.value:
            logger.info(json.dumps({"event": "job_skipped_canceled", "job_id": job_id}))
            return
        set_job_running(db, job_id)
        stage = job.stage
        user_id = int(job.user_id)
        logger.info(json.dumps({"event": "job_started", "job_id": job_id, "user_id": user_id, "stage": stage}))

        if stage == "samples_download":
            _handle_samples_download(db, job_id, user_id, payload)
        elif stage == "quality_analysis":
            _handle_quality_analysis(db, job_id, user_id, payload)
        elif stage == "quality_analysis_post_trim":
            _handle_quality_analysis_post_trim(db, job_id, user_id, payload)
        elif stage == "alignment":
            _handle_alignment(db, job_id, user_id, payload)
        elif stage == "quantification":
            _handle_quantification(db, job_id, user_id, payload)
        elif stage == "deg":
            _handle_deg(db, job_id, user_id, payload)
        elif stage == "clustering":
            _handle_clustering(db, job_id, user_id, payload)
        elif stage == "llm":
            _handle_llm(db, job_id, user_id, payload)
        elif stage == "results_barplot":
            _handle_results_barplot(db, job_id, user_id, payload)
        elif stage == "results_venn":
            _handle_results_venn(db, job_id, user_id, payload)
        elif stage == "results_heatmap":
            _handle_results_heatmap(db, job_id, user_id, payload)
        else:
            raise ValueError(f"Unknown stage: {stage}")

    except Exception as exc:  # noqa: BLE001
        if isinstance(exc, RETRYABLE_EXCEPTIONS) and self.request.retries < 2:
            retry_delay = min(300, (2 ** self.request.retries) * 30)
            job = db.query(PipelineJob).filter(PipelineJob.id == job_id).first()
            if job:
                job.status = PipelineStatus.PENDING.value
                job.error_message = str(exc)
                db.commit()
            logger.warning(
                json.dumps(
                    {
                        "event": "job_retry",
                        "job_id": job_id,
                        "user_id": user_id,
                        "stage": stage,
                        "error": str(exc),
                        "retry_in_s": retry_delay,
                        "attempt": self.request.retries + 1,
                    }
                )
            )
            raise self.retry(exc=exc, countdown=retry_delay, max_retries=2)

        try:
            if user_id >= 0:
                _finalize_job(
                    db,
                    job_id=job_id,
                    stage=stage,
                    user_id=user_id,
                    status=PipelineStatus.FAILED,
                    result={"error": str(exc)},
                    error_message=str(exc),
                    exit_code=1,
                )
        except Exception:
            logger.exception("Failed to persist failure status for job %s", job_id)
        logger.error(
            json.dumps(
                {
                    "event": "job_failed",
                    "job_id": job_id,
                    "user_id": user_id,
                    "stage": stage,
                    "duration_ms": int((time.monotonic() - started_at) * 1000),
                    "error": str(exc),
                }
            )
        )
        raise
    finally:
        db.close()


def enqueue_pipeline_job(job_id: str) -> None:
    execute_pipeline_job.apply_async(args=[job_id], task_id=job_id)


def _handle_samples_download(db: Session, job_id: str, user_id: int, payload: dict[str, Any]) -> None:
    sra_code = ensure_safe_component(str(payload["sra_code"]), "sra_code")
    log_file = Path(f"/app/backend/logs/{sra_code}_download.log")

    def _log_tail(max_chars: int = 4000) -> str:
        try:
            return log_file.read_text(encoding="utf-8", errors="replace")[-max_chars:]
        except Exception:
            return ""

    sample = db.query(SampleStage).filter(
        SampleStage.sra_code == sra_code,
        SampleStage.stage_id == 1,
        SampleStage.user_id == user_id,
    ).first()
    if sample:
        sample.status = "RUNNING"
        db.commit()

    try:
        rc, stdout, stderr = _run(["bash", "/app/backend/scripts/download_script.sh", sra_code, str(user_id)], timeout=36000)
    except Exception as exc:
        if sample:
            sample.status = "FAILED"
            db.commit()
        log_tail = _log_tail()
        if log_tail:
            raise RuntimeError(f"Samples download failed for {sra_code}. Log tail:\n{log_tail}") from exc
        raise

    if sample:
        sample.status = "COMPLETED" if rc == 0 else "FAILED"
        db.commit()

    log_tail = _log_tail()
    result = {
        "stdout": stdout[-10000:],
        "stderr": stderr[-10000:],
        "sra_code": sra_code,
        "log_tail": log_tail,
    }
    status = PipelineStatus.COMPLETED if rc == 0 else PipelineStatus.FAILED
    _finalize_job(
        db,
        job_id=job_id,
        stage="samples_download",
        user_id=user_id,
        status=status,
        result=result,
        error_message=None if rc == 0 else (log_tail or stderr[-4000:] or f"download_script failed with rc={rc}"),
        exit_code=rc,
    )


def _handle_quality_analysis(db: Session, job_id: str, user_id: int, payload: dict[str, Any]) -> None:
    samples = payload.get("samples") or []
    outputs: list[dict[str, Any]] = []
    for sample in samples:
        safe_sample = ensure_safe_component(str(sample), "sample")
        rc, stdout, stderr = _run(["bash", "/app/backend/scripts/quality_analysis.sh", safe_sample, str(user_id)], timeout=10800)
        outputs.append({"sample": safe_sample, "rc": rc, "stderr": stderr[-2000:]})
        base = safe_sample.replace("_1.fastq", "").replace("_2.fastq", "")
        for suffix in ["_1", "_2"]:
            row = db.query(SampleStage).filter(
                SampleStage.name == f"{base}{suffix}.html",
                SampleStage.stage_id == 2,
                SampleStage.user_id == user_id,
            ).first()
            if row:
                row.status = "COMPLETED" if rc == 0 else "FAILED"
                db.commit()

    failed = [x for x in outputs if x["rc"] != 0]
    _finalize_job(
        db,
        job_id=job_id,
        stage="quality_analysis",
        user_id=user_id,
        status=PipelineStatus.COMPLETED if not failed else PipelineStatus.FAILED,
        result={"runs": outputs},
        error_message="Some samples failed" if failed else None,
        exit_code=0 if not failed else 1,
    )


def _handle_quality_analysis_post_trim(db: Session, job_id: str, user_id: int, payload: dict[str, Any]) -> None:
    samples = payload.get("samples") or []
    outputs: list[dict[str, Any]] = []
    for sample in samples:
        safe_sample = ensure_safe_component(str(sample), "sample")
        rc, stdout, stderr = _run(["bash", "/app/backend/scripts/quality_analysis_post_trim.sh", safe_sample, str(user_id)], timeout=10800)
        outputs.append({"sample": safe_sample, "rc": rc, "stderr": stderr[-2000:]})
        row_name = safe_sample.replace("_trimmed.fastq", "_post_trim.html")
        row = db.query(SampleStage).filter(
            SampleStage.name == row_name,
            SampleStage.stage_id == 4,
            SampleStage.user_id == user_id,
        ).first()
        if row:
            row.status = "COMPLETED" if rc == 0 else "FAILED"
            db.commit()

    failed = [x for x in outputs if x["rc"] != 0]
    _finalize_job(
        db,
        job_id=job_id,
        stage="quality_analysis_post_trim",
        user_id=user_id,
        status=PipelineStatus.COMPLETED if not failed else PipelineStatus.FAILED,
        result={"runs": outputs},
        error_message="Some samples failed" if failed else None,
        exit_code=0 if not failed else 1,
    )


def _handle_alignment(db: Session, job_id: str, user_id: int, payload: dict[str, Any]) -> None:
    sample = ensure_safe_component(str(payload["sample"]), "sample")
    genome_dir = str(Path(str(payload["genome_dir"])).resolve())
    genome_root = _abs_users("ref_genomes")
    try:
        Path(genome_dir).resolve().relative_to(genome_root)
    except ValueError as exc:
        raise RuntimeError("Invalid genome directory for alignment job") from exc
    threads = int(payload.get("threads", 1))
    additional = payload.get("additional", [])

    alignment_path = _abs_users(str(user_id), "alignment")
    alignment_path.mkdir(parents=True, exist_ok=True)

    rc, stdout, stderr = _run(
        [
            "bash",
            "/app/backend/scripts/alignment.sh",
            sample,
            str(user_id),
            str(alignment_path),
            genome_dir,
            str(threads),
            *[str(x) for x in additional],
        ],
        timeout=172800,
    )

    bam_file = alignment_path / sample / f"{sample}.bam"
    if bam_file.exists():
        add_artifact(db, job_id=job_id, user_id=user_id, kind="bam", path=str(bam_file))
    row = db.query(SampleStage).filter(
        SampleStage.sra_code == sample,
        SampleStage.stage_id == 5,
        SampleStage.user_id == user_id,
    ).first()
    if row:
        row.status = "COMPLETED" if rc == 0 else "FAILED"
        if bam_file.exists():
            size_mb = bam_file.stat().st_size / (1024 * 1024)
            row.size = f"{size_mb:.2f} MB"
        db.commit()

    _finalize_job(
        db,
        job_id=job_id,
        stage="alignment",
        user_id=user_id,
        status=PipelineStatus.COMPLETED if rc == 0 else PipelineStatus.FAILED,
        result={"sample": sample, "stdout": stdout[-5000:]},
        error_message=None if rc == 0 else stderr[-4000:],
        exit_code=rc,
    )


def _handle_quantification(db: Session, job_id: str, user_id: int, payload: dict[str, Any]) -> None:
    samples = payload.get("samples") or []
    feature_type = str(payload["feature_type"])
    id_attribute = str(payload["id_attribute"])
    selected_genome = payload.get("selected_genome")

    outputs: list[dict[str, Any]] = []
    for sample in samples:
        safe_sample = ensure_safe_component(str(sample), "sample")
        cmd = ["bash", "/app/backend/scripts/quantification.sh", safe_sample, str(user_id), feature_type, id_attribute]
        if selected_genome:
            cmd.append(str(selected_genome))
        rc, stdout, stderr = _run(cmd, timeout=10800)
        outputs.append({"sample": safe_sample, "rc": rc, "stderr": stderr[-2000:]})
        txt_name = safe_sample.replace(".bam", ".txt")
        row = db.query(SampleStage).filter(
            SampleStage.name == txt_name,
            SampleStage.stage_id == 6,
            SampleStage.user_id == user_id,
        ).first()
        if row:
            row.status = "COMPLETED" if rc == 0 else "FAILED"
            txt_path = _abs_users(str(user_id), "quantification", txt_name)
            if txt_path.exists():
                row.size = f"{txt_path.stat().st_size / 1024:.2f} KB"
            db.commit()

    failed = [x for x in outputs if x["rc"] != 0]
    job_error: str | None = None
    if failed:
        for item in failed:
            stderr_text = str(item.get("stderr") or "").strip()
            if stderr_text:
                job_error = f"Sample {item['sample']} failed: {stderr_text[-1200:]}"
                break
        if not job_error:
            job_error = "Some samples failed"

    _finalize_job(
        db,
        job_id=job_id,
        stage="quantification",
        user_id=user_id,
        status=PipelineStatus.COMPLETED if not failed else PipelineStatus.FAILED,
        result={"runs": outputs},
        error_message=job_error,
        exit_code=0 if not failed else 1,
    )


def _handle_deg(db: Session, job_id: str, user_id: int, payload: dict[str, Any]) -> None:
    preprocess_dir = _abs_users(str(user_id), "preprocess")
    deg_dir = _abs_users(str(user_id), "DEG")
    deg_dir.mkdir(parents=True, exist_ok=True)
    deg_script = "/app/backend/scripts/DEG.R"

    rc, stdout, stderr = _run(["Rscript", deg_script, str(preprocess_dir), str(deg_dir)], timeout=172800)

    deg_xlsx = deg_dir / "DEG.xlsx"
    if deg_xlsx.exists():
        add_artifact(db, job_id=job_id, user_id=user_id, kind="xlsx", path=str(deg_xlsx))

    _finalize_job(
        db,
        job_id=job_id,
        stage="deg",
        user_id=user_id,
        status=PipelineStatus.COMPLETED if rc == 0 else PipelineStatus.FAILED,
        result={"stdout": stdout[-6000:]},
        error_message=None if rc == 0 else stderr[-4000:],
        exit_code=rc,
    )


def _handle_clustering(db: Session, job_id: str, user_id: int, payload: dict[str, Any]) -> None:
    sheets = payload.get("sheets") or []
    deg_xlsx = _abs_users(str(user_id), "DEG", "DEG.xlsx")
    results: dict[str, Any] = {}
    failed_sheets: list[str] = []

    for sheet in sheets:
        safe_sheet = ensure_safe_component(str(sheet), "sheet")
        out_dir = _abs_users(str(user_id), "clustering", safe_sheet)
        out_dir.mkdir(parents=True, exist_ok=True)
        img_final = out_dir / "cluster.png"
        img_metrics = out_dir / "metrics.png"
        cluster_json = out_dir / "clusters.json"
        try:
            res = clustering_script.cluster_pipeline(
                str(deg_xlsx),
                sheet_name=safe_sheet,
                img_final_path=str(img_final),
                img_metrics_path=str(img_metrics),
                clusters_json_path=str(cluster_json),
            )
            results[safe_sheet] = res
            for artifact in [img_final, img_metrics, cluster_json]:
                if artifact.exists():
                    kind = artifact.suffix.replace(".", "") or "file"
                    add_artifact(db, job_id=job_id, user_id=user_id, kind=kind, path=str(artifact))
            row = db.query(SampleStage).filter(
                SampleStage.user_id == user_id,
                SampleStage.stage_id == 9,
                SampleStage.name == safe_sheet,
            ).first()
            if row:
                row.status = "COMPLETED"
                db.commit()
        except Exception:
            failed_sheets.append(safe_sheet)
            row = db.query(SampleStage).filter(
                SampleStage.user_id == user_id,
                SampleStage.stage_id == 9,
                SampleStage.name == safe_sheet,
            ).first()
            if row:
                row.status = "FAILED"
                db.commit()

    _finalize_job(
        db,
        job_id=job_id,
        stage="clustering",
        user_id=user_id,
        status=PipelineStatus.COMPLETED if not failed_sheets else PipelineStatus.FAILED,
        result={"results": results, "failed_sheets": failed_sheets},
        error_message=None if not failed_sheets else f"Failed sheets: {', '.join(failed_sheets)}",
        exit_code=0 if not failed_sheets else 1,
    )


def _run_llm_with_fallback(user_id: int, sheet: str, out_dir: str) -> dict[str, Any]:
    models = [settings.llm_primary_model] + [m for m in settings.llm_fallback_models if m != settings.llm_primary_model]
    last_error = None
    for model in models:
        os.environ["BILBO_LLM_MODEL_OVERRIDE"] = model
        try:
            result = llm_script.run_llm(file_path=None, sheet_name=sheet, out_dir=out_dir, user_id=user_id)
            result["model_used"] = model
            return result
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
    raise RuntimeError(last_error or "No model could process LLM job")


def _handle_llm(db: Session, job_id: str, user_id: int, payload: dict[str, Any]) -> None:
    sheets = payload.get("sheets") or []
    results: dict[str, Any] = {}
    failed_sheets: list[str] = []
    for sheet in sheets:
        safe_sheet = ensure_safe_component(str(sheet), "sheet")
        out_dir = _abs_users(str(user_id), "llm", safe_sheet)
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            res = _run_llm_with_fallback(user_id, safe_sheet, str(out_dir))
            results[safe_sheet] = res
            for key in ["report", "json"]:
                p = Path(res.get(key, ""))
                if p.exists():
                    add_artifact(db, job_id=job_id, user_id=user_id, kind=p.suffix.replace(".", "") or "file", path=str(p))
            row = db.query(SampleStage).filter(
                SampleStage.user_id == user_id,
                SampleStage.stage_id == 10,
                SampleStage.name == safe_sheet,
            ).first()
            if row:
                row.status = "COMPLETED"
                db.commit()
        except Exception:
            failed_sheets.append(safe_sheet)
            row = db.query(SampleStage).filter(
                SampleStage.user_id == user_id,
                SampleStage.stage_id == 10,
                SampleStage.name == safe_sheet,
            ).first()
            if row:
                row.status = "FAILED"
                db.commit()

    _finalize_job(
        db,
        job_id=job_id,
        stage="llm",
        user_id=user_id,
        status=PipelineStatus.COMPLETED if not failed_sheets else PipelineStatus.FAILED,
        result={"results": results, "failed_sheets": failed_sheets},
        error_message=None if not failed_sheets else f"Failed sheets: {', '.join(failed_sheets)}",
        exit_code=0 if not failed_sheets else 1,
    )


def _handle_results_barplot(db: Session, job_id: str, user_id: int, payload: dict[str, Any]) -> None:
    title = ensure_safe_component(str(payload["title"]), "title")
    contrasts = [str(c) for c in (payload.get("contrasts") or [])]
    deg_dir = _abs_users(str(user_id), "DEG")
    deg_xlsx = deg_dir / "DEG.xlsx"
    script = "/app/backend/scripts/barplot_multiplo.R"
    rc, stdout, stderr = _run(["Rscript", script, str(deg_xlsx), str(deg_dir), title, *contrasts], timeout=3600)

    output_file = deg_dir / f"BARPLOT.MULTIPLO - {title}.png"
    if output_file.exists():
        add_artifact(db, job_id=job_id, user_id=user_id, kind="png", path=str(output_file))

    _finalize_job(
        db,
        job_id=job_id,
        stage="results_barplot",
        user_id=user_id,
        status=PipelineStatus.COMPLETED if rc == 0 else PipelineStatus.FAILED,
        result={"title": title},
        error_message=None if rc == 0 else stderr[-4000:],
        exit_code=rc,
    )


def _handle_results_venn(db: Session, job_id: str, user_id: int, payload: dict[str, Any]) -> None:
    import tempfile

    title = ensure_safe_component(str(payload["title"]), "title")
    contrasts = [str(c) for c in (payload.get("contrasts") or [])]
    deg_dir = _abs_users(str(user_id), "DEG")
    deg_xlsx = deg_dir / "DEG.xlsx"
    png_path = deg_dir / f"VENN.DIAGRAM - {title}.png"
    script = "/app/backend/scripts/venn_diagram.py"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as temp:
        for c in contrasts:
            temp.write(c + "\n")
        temp_path = temp.name

    try:
        rc, stdout, stderr = _run(["python", script, temp_path, str(deg_xlsx), str(png_path), title], timeout=3600)
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass

    if png_path.exists():
        add_artifact(db, job_id=job_id, user_id=user_id, kind="png", path=str(png_path))

    _finalize_job(
        db,
        job_id=job_id,
        stage="results_venn",
        user_id=user_id,
        status=PipelineStatus.COMPLETED if rc == 0 else PipelineStatus.FAILED,
        result={"title": title},
        error_message=None if rc == 0 else stderr[-4000:],
        exit_code=rc,
    )


def _handle_results_heatmap(db: Session, job_id: str, user_id: int, payload: dict[str, Any]) -> None:
    import tempfile

    title = ensure_safe_component(str(payload["title"]), "title")
    selected_contrasts = [str(c) for c in (payload.get("selected_contrasts") or [])]
    deg_dir = _abs_users(str(user_id), "DEG")
    deg_xlsx = deg_dir / "DEG_full.xlsx"
    png_path = deg_dir / f"HEATMAP - {title}.png"
    script = "/app/backend/scripts/heatmap.R"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as temp:
        for c in selected_contrasts:
            temp.write(c + "\n")
        temp_path = temp.name

    try:
        rc, stdout, stderr = _run(["Rscript", script, temp_path, str(deg_xlsx), str(png_path), title], timeout=10800)
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass

    if png_path.exists():
        add_artifact(db, job_id=job_id, user_id=user_id, kind="png", path=str(png_path))

    _finalize_job(
        db,
        job_id=job_id,
        stage="results_heatmap",
        user_id=user_id,
        status=PipelineStatus.COMPLETED if rc == 0 else PipelineStatus.FAILED,
        result={"title": title},
        error_message=None if rc == 0 else stderr[-4000:],
        exit_code=rc,
    )
