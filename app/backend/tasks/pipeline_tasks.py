from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional, Tuple

from sqlalchemy.orm import Session

from ..core.settings import settings
from ..db.database import SessionLocal
from ..db.models import Artifact, AuditLog, PipelineJob, SampleStage
from ..schemas.common import PipelineStatus
from ..scripts import clustering as clustering_script
from ..scripts import llm as llm_script
from ..services.job_service import add_artifact, set_job_finished, set_job_running
from ..services.rag_bootstrap import ensure_rag_database
from ..utils_paths import ensure_safe_component
from .celery_app import celery_app

logger = logging.getLogger(__name__)
RETRYABLE_EXCEPTIONS = (TimeoutError, OSError, ConnectionError)



# Progresso persistente individual por job
_PROGRESS_CONTEXT = {
    "job_id": None,
    "user_id": None,
    "stage": None,
}


def _job_progress_path(job_id: str, user_id: int) -> Path:
    progress_dir = (
        Path(settings.users_root)
        / str(user_id)
        / "logs"
        / "jobs"
    )
    progress_dir.mkdir(parents=True, exist_ok=True)
    return progress_dir / f"{job_id}.progress.log"


def _append_job_progress(
    job_id: str,
    user_id: int,
    message: str,
) -> None:
    """Adiciona uma mensagem curta ao log individual do job."""
    try:
        path = _job_progress_path(job_id, user_id)
        timestamp = datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        )

        with path.open("a", encoding="utf-8") as stream:
            stream.write(
                f"[{timestamp}] PROGRESS: {message.strip()}\n"
            )
            stream.flush()
    except Exception:
        logger.warning(
            "Não foi possível escrever progresso do job %s",
            job_id,
            exc_info=True,
        )


def _set_progress_context(
    job_id: str,
    user_id: int,
    stage: str,
) -> None:
    _PROGRESS_CONTEXT["job_id"] = job_id
    _PROGRESS_CONTEXT["user_id"] = user_id
    _PROGRESS_CONTEXT["stage"] = stage

    if stage not in ("deg", "clustering", "llm"):
        return

    path = _job_progress_path(job_id, user_id)

    try:
        path.write_text("", encoding="utf-8")
    except OSError:
        logger.warning(
            "Não foi possível inicializar o log do job %s",
            job_id,
            exc_info=True,
        )

    # BILBO_LLM_PROGRESS_PERSISTENCE
    initial_message = {
        "deg": "DEG — job recebido pelo worker.",
        "clustering": (
            "Clusterização — job recebido pelo worker."
        ),
        "llm": (
            "Interpretação LLM/RAG — "
            "job recebido pelo worker."
        ),
    }[stage]

    _append_job_progress(
        job_id,
        user_id,
        initial_message,
    )


def _progress_event(message: str) -> None:
    if _PROGRESS_CONTEXT.get("stage") not in ("deg", "clustering", "llm"):
        return

    job_id = _PROGRESS_CONTEXT.get("job_id")
    user_id = _PROGRESS_CONTEXT.get("user_id")

    if not job_id or user_id is None:
        return

    _append_job_progress(
        str(job_id),
        int(user_id),
        message,
    )



def _call_with_progress(
    label: str,
    function,
    *args,
    **kwargs,
):
    """
    Executa uma função longa emitindo heartbeat a cada 15 segundos.
    """
    import threading

    stop_event = threading.Event()
    started = time.monotonic()

    _progress_event(f"{label} iniciada.")

    def heartbeat():
        while not stop_event.wait(15):
            elapsed = int(time.monotonic() - started)
            _progress_event(
                f"{label} em andamento ({elapsed} s decorridos)."
            )

    thread = threading.Thread(
        target=heartbeat,
        daemon=True,
    )
    thread.start()

    try:
        result = function(*args, **kwargs)
    except Exception as exc:
        elapsed = int(time.monotonic() - started)
        _progress_event(
            f"{label} falhou após {elapsed} s: {str(exc)[:300]}"
        )
        raise
    else:
        elapsed = int(time.monotonic() - started)
        _progress_event(
            f"{label} concluída em {elapsed} s."
        )
        return result
    finally:
        stop_event.set()
        thread.join(timeout=1)


def _deg_command_phase(cmd: list[str]) -> tuple[str, str]:
    """
    Retorna nome curto e mensagem inicial conforme o script executado.
    """
    command_names = {
        Path(str(component)).name.casefold()
        for component in cmd
    }

    if "deg.r" in command_names:
        return (
            "análise diferencial",
            "DEG — iniciando análise estatística no R.",
        )

    if "annotate_deg_with_gff.py" in command_names:
        return (
            "anotação GFF",
            "DEG — iniciando anotação funcional GFF.",
        )

    if "annotate_deg_with_uniprot.py" in command_names:
        return (
            "anotação UniProt",
            "DEG — iniciando anotação funcional UniProt.",
        )

    if "deg_graphs.py" in command_names:
        return (
            "geração de gráficos",
            "DEG — iniciando geração dos gráficos.",
        )

    return "", ""


def _run(
    cmd: list[str],
    cwd: Optional[str] = None,
    timeout: Optional[int] = None,
) -> Tuple[int, str, str]:
    """
    Executa um subprocesso e emite heartbeat para etapas DEG longas.
    """
    phase_name, start_message = _deg_command_phase(cmd)

    if start_message:
        _progress_event(start_message)

    process = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    started = time.monotonic()
    heartbeat_interval = 15
    deadline = (
        started + timeout
        if timeout is not None
        else None
    )

    stdout = ""
    stderr = ""

    while True:
        if deadline is not None:
            remaining = deadline - time.monotonic()

            if remaining <= 0:
                process.kill()
                stdout, stderr = process.communicate()

                if phase_name:
                    _progress_event(
                        f"DEG — {phase_name} excedeu o tempo limite."
                    )

                raise TimeoutError(
                    f"Timed out after {timeout}s running: "
                    f"{' '.join(cmd)}"
                )

            wait_time = min(
                heartbeat_interval,
                max(0.1, remaining),
            )
        else:
            wait_time = heartbeat_interval

        try:
            stdout, stderr = process.communicate(
                timeout=wait_time
            )
            break

        except subprocess.TimeoutExpired:
            if phase_name:
                elapsed = int(time.monotonic() - started)
                _progress_event(
                    f"DEG — {phase_name} em andamento "
                    f"({elapsed} s decorridos)."
                )

    elapsed = int(time.monotonic() - started)

    if phase_name:
        if process.returncode == 0:
            _progress_event(
                f"DEG — {phase_name} concluída "
                f"em {elapsed} s."
            )
        else:
            detail = ""

            if stderr:
                stderr_lines = [
                    line.strip()
                    for line in stderr.splitlines()
                    if line.strip()
                ]
                if stderr_lines:
                    detail = f" Detalhe: {stderr_lines[-1][:300]}"

            _progress_event(
                f"DEG — falha durante {phase_name} "
                f"(código {process.returncode}).{detail}"
            )

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
            db.query(Artifact).filter(Artifact.user_id == user_id, Artifact.created_at < artifacts_cutoff).all()
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

        terminal_statuses = {
            PipelineStatus.COMPLETED.value,
            PipelineStatus.FAILED.value,
            PipelineStatus.CANCELED.value,
        }

        if job.status in terminal_statuses or job.finished_at is not None:
            logger.info(
                json.dumps(
                    {
                        "event": "job_skipped_terminal",
                        "job_id": job_id,
                        "status": job.status,
                        "finished_at": (job.finished_at.isoformat() if job.finished_at else None),
                    }
                )
            )
            return

        set_job_running(db, job_id)
        stage = job.stage
        user_id = int(job.user_id)
        logger.info(json.dumps({"event": "job_started", "job_id": job_id, "user_id": user_id, "stage": stage}))
        _set_progress_context(job_id, user_id, stage)

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
        elif stage == "rag_bootstrap":
            _handle_rag_bootstrap(db, job_id, user_id, payload)
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
            retry_delay = min(300, (2**self.request.retries) * 30)
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
            raise self.retry(exc=exc, countdown=retry_delay, max_retries=2) from exc

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

    sample = (
        db.query(SampleStage)
        .filter(
            SampleStage.sra_code == sra_code,
            SampleStage.stage_id == 1,
            SampleStage.user_id == user_id,
        )
        .first()
    )
    if sample:
        sample.status = "RUNNING"
        db.commit()

    try:
        rc, stdout, stderr = _run(
            ["bash", "/app/backend/scripts/download_script.sh", sra_code, str(user_id)], timeout=36000
        )
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
        rc, stdout, stderr = _run(
            ["bash", "/app/backend/scripts/quality_analysis.sh", safe_sample, str(user_id)], timeout=10800
        )
        outputs.append({"sample": safe_sample, "rc": rc, "stderr": stderr[-2000:]})
        sample_stem = safe_sample
        for extension in (".fastq.gz", ".fq.gz", ".fastq", ".fq"):
            if sample_stem.endswith(extension):
                sample_stem = sample_stem[: -len(extension)]
                break

        row = (
            db.query(SampleStage)
            .filter(
                SampleStage.name == f"{sample_stem}.html",
                SampleStage.stage_id == 2,
                SampleStage.user_id == user_id,
            )
            .first()
        )
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
        rc, stdout, stderr = _run(
            ["bash", "/app/backend/scripts/quality_analysis_post_trim.sh", safe_sample, str(user_id)], timeout=10800
        )
        outputs.append({"sample": safe_sample, "rc": rc, "stderr": stderr[-2000:]})
        row_name = safe_sample
        for suffix in (
            "_trimmed.fastq.gz",
            "_trimmed.fq.gz",
            "_trimmed.fastq",
            "_trimmed.fq",
        ):
            if row_name.endswith(suffix):
                row_name = row_name[: -len(suffix)] + "_post_trim.html"
                break
        row = (
            db.query(SampleStage)
            .filter(
                SampleStage.name == row_name,
                SampleStage.stage_id == 4,
                SampleStage.user_id == user_id,
            )
            .first()
        )
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
    row = (
        db.query(SampleStage)
        .filter(
            SampleStage.sra_code == sample,
            SampleStage.stage_id == 5,
            SampleStage.user_id == user_id,
        )
        .first()
    )
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
        txt_name = safe_sample.replace(".bam", ".txt")

        row = (
            db.query(SampleStage)
            .filter(
                SampleStage.name == txt_name,
                SampleStage.stage_id == 6,
                SampleStage.user_id == user_id,
            )
            .first()
        )

        if row:
            row.status = "RUNNING"
            row.size = None
            db.commit()

        cmd = ["bash", "/app/backend/scripts/quantification.sh", safe_sample, str(user_id), feature_type, id_attribute]
        if selected_genome:
            cmd.append(str(selected_genome))

        try:
            rc, stdout, stderr = _run(cmd, timeout=10800)
        except Exception as exc:
            rc = 1
            stderr = str(exc)
            logger.exception("Quantification failed for %s", safe_sample)

        outputs.append({"sample": safe_sample, "rc": rc, "stderr": stderr[-2000:]})

        if row is None:
            row = (
                db.query(SampleStage)
                .filter(
                    SampleStage.name == txt_name,
                    SampleStage.stage_id == 6,
                    SampleStage.user_id == user_id,
                )
                .first()
            )

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
    gff_annotation_script = "/app/backend/scripts/annotate_deg_with_gff.py"
    uniprot_annotation_script = "/app/backend/scripts/annotate_deg_with_uniprot.py"
    deg_graphs_script = "/app/backend/scripts/deg_graphs.py"

    genome_accession = str(payload.get("genome_accession") or "").strip()

    # --------------------------------------------------------
    # 1. edgeR / DEG
    # --------------------------------------------------------
    rc, stdout, stderr = _run(
        ["Rscript", deg_script, str(preprocess_dir), str(deg_dir)],
        timeout=172800,
    )

    deg_xlsx = deg_dir / "DEG.xlsx"
    deg_full_xlsx = deg_dir / "DEG_full.xlsx"

    annotation_result: dict[str, Any] = {
        "genome_accession": genome_accession,
        "gff": "NOT_RUN",
        "uniprot": "NOT_RUN",
    }

    annotation_error: str | None = None

    # --------------------------------------------------------
    # 2. Anotação funcional somente se DEG terminou
    # --------------------------------------------------------
    if rc == 0:
        if not deg_xlsx.exists():
            annotation_error = "DEG.xlsx não foi produzido."
        elif not genome_accession:
            annotation_error = "Genome accession não informado para anotação funcional."
        else:
            genome_root = _abs_users("ref_genomes")
            genome_dir = _abs_users("ref_genomes", genome_accession)

            # Segurança: impedir acesso fora de ref_genomes
            try:
                genome_dir.resolve().relative_to(genome_root.resolve())
            except ValueError:
                annotation_error = "Diretório de genoma inválido."
            else:
                gff_candidates = [
                    genome_dir / "genomic.gff",
                    genome_dir / "genomic.gff3",
                    genome_dir / "genomic.gtf",
                ]

                gff_path = next((x for x in gff_candidates if x.exists()), None)

                if gff_path is None:
                    annotation_error = f"Arquivo GFF/GTF não encontrado para {genome_accession}."
                else:
                    annotation_result["gff_path"] = str(gff_path)

                    # ------------------------------------------------
                    # GFF
                    # ------------------------------------------------
                    gff_rc, gff_stdout, gff_stderr = _run(
                        [
                            "python",
                            gff_annotation_script,
                            str(deg_xlsx),
                            str(gff_path),
                        ],
                        timeout=7200,
                    )

                    annotation_result["gff"] = "COMPLETED" if gff_rc == 0 else "FAILED"
                    annotation_result["gff_stdout"] = gff_stdout[-3000:]
                    annotation_result["gff_stderr"] = gff_stderr[-3000:]

                    if gff_rc != 0:
                        annotation_error = "Falha na anotação pelo GFF: " + (gff_stderr[-1500:] or f"rc={gff_rc}")
                    else:
                        # --------------------------------------------
                        # UniProt
                        #
                        # Executado somente sobre DEG.xlsx
                        # (genes significativos), evitando dezenas de
                        # milhares de consultas de DEG_full.xlsx.
                        # --------------------------------------------
                        uni_rc, uni_stdout, uni_stderr = _run(
                            [
                                "python",
                                uniprot_annotation_script,
                                str(deg_xlsx),
                            ],
                            timeout=86400,
                        )

                        annotation_result["uniprot"] = "COMPLETED" if uni_rc == 0 else "FAILED"
                        annotation_result["uniprot_stdout"] = uni_stdout[-5000:]
                        annotation_result["uniprot_stderr"] = uni_stderr[-3000:]

                        if uni_rc != 0:
                            annotation_error = "Falha na anotação UniProt: " + (uni_stderr[-1500:] or f"rc={uni_rc}")

    # --------------------------------------------------------
    # 3. Gerar figuras DEG após a anotação funcional
    # --------------------------------------------------------
    if rc == 0 and deg_xlsx.exists() and annotation_error is None:
        graph_rc, graph_stdout, graph_stderr = _run(
            [
                "python",
                deg_graphs_script,
                str(deg_xlsx),
                str(deg_dir),
            ],
            timeout=7200,
        )

        annotation_result["graphs"] = "COMPLETED" if graph_rc == 0 else "FAILED"
        annotation_result["graphs_stdout"] = graph_stdout[-4000:]
        annotation_result["graphs_stderr"] = graph_stderr[-3000:]

        if graph_rc != 0:
            annotation_error = "Falha na geração das figuras DEG: " + (graph_stderr[-1500:] or f"rc={graph_rc}")

    # --------------------------------------------------------
    # 4. Registrar artefatos
    # --------------------------------------------------------
    if deg_xlsx.exists():
        add_artifact(
            db,
            job_id=job_id,
            user_id=user_id,
            kind="xlsx",
            path=str(deg_xlsx),
        )

    if deg_full_xlsx.exists():
        add_artifact(
            db,
            job_id=job_id,
            user_id=user_id,
            kind="xlsx",
            path=str(deg_full_xlsx),
        )

    # DEG só é considerado integralmente concluído quando
    # análise estatística + GFF + UniProt terminam.
    final_ok = rc == 0 and annotation_error is None

    if rc != 0:
        error_message = stderr[-4000:] or f"DEG.R terminou com rc={rc}"
    else:
        error_message = annotation_error

    _finalize_job(
        db,
        job_id=job_id,
        stage="deg",
        user_id=user_id,
        status=PipelineStatus.COMPLETED if final_ok else PipelineStatus.FAILED,
        result={
            "stdout": stdout[-6000:],
            "annotation": annotation_result,
            "deg_xlsx": str(deg_xlsx) if deg_xlsx.exists() else None,
            "deg_full_xlsx": str(deg_full_xlsx) if deg_full_xlsx.exists() else None,
        },
        error_message=error_message,
        exit_code=0 if final_ok else 1,
    )



def _handle_rag_bootstrap(
    db: Session,
    job_id: str,
    user_id: int,
    payload: dict[str, Any],
) -> None:
    del payload
    status = ensure_rag_database()
    _finalize_job(
        db,
        job_id=job_id,
        stage="rag_bootstrap",
        user_id=user_id,
        status=PipelineStatus.COMPLETED,
        result={"rag": status},
        error_message=None,
        exit_code=0,
    )


def _handle_clustering(db: Session, job_id: str, user_id: int, payload: dict[str, Any]) -> None:
    sheets = payload.get("sheets") or []
    deg_xlsx = _abs_users(str(user_id), "DEG", "DEG.xlsx")
    results: dict[str, Any] = {}
    failed_sheets: list[str] = []

    _progress_event(
        f"Clusterização — preparando {len(sheets)} contraste(s)."
    )

    for sheet_index, sheet in enumerate(sheets, start=1):
        safe_sheet = ensure_safe_component(str(sheet), "sheet")

        _progress_event(
            "Clusterização — contraste "
            f"{sheet_index}/{len(sheets)}: {safe_sheet}."
        )

        out_dir = _abs_users(str(user_id), "clustering", safe_sheet)
        out_dir.mkdir(parents=True, exist_ok=True)
        img_final = out_dir / "cluster.png"
        img_metrics = out_dir / "metrics.png"
        cluster_json = out_dir / "clusters.json"
        try:
            res = _call_with_progress(
                f"Clusterização — cálculo semântico de {safe_sheet}",
                clustering_script.cluster_pipeline,
                str(deg_xlsx),
                sheet_name=safe_sheet,
                img_final_path=str(img_final),
                img_metrics_path=str(img_metrics),
                clusters_json_path=str(cluster_json),
            )
            results[safe_sheet] = res
            artifact_paths = [img_final, img_metrics, cluster_json]
            for key in ["metrics", "input_normalized"]:
                value = res.get(key)
                if value:
                    artifact_paths.append(Path(value))
            for key in ["features_dir", "clusters_dir"]:
                value = res.get(key)
                if value:
                    artifact_paths.extend(Path(value).glob("**/*.csv"))

            for artifact in artifact_paths:
                if artifact.exists():
                    kind = artifact.suffix.replace(".", "") or "file"
                    add_artifact(db, job_id=job_id, user_id=user_id, kind=kind, path=str(artifact))

            # Interpretação LLM/RAG executada somente pelo handler manual.
            row = (
                db.query(SampleStage)
                .filter(
                    SampleStage.user_id == user_id,
                    SampleStage.stage_id == 9,
                    SampleStage.name == safe_sheet,
                )
                .first()
            )
            if row is None:
                row = SampleStage(
                    stage_id=9,
                    name=safe_sheet,
                    sra_code=None,
                    size="",
                    status="COMPLETED",
                    user_id=user_id,
                )
                db.add(row)
            else:
                row.status = "COMPLETED"
            db.commit()

            _progress_event(
                f"Clusterização — {safe_sheet} concluída. "
                "Interpretação LLM/RAG aguardando execução manual."
            )
        except Exception as exc:
            _progress_event(
                f"Clusterização — falha no contraste {safe_sheet}: "
                f"{str(exc)[:300]}"
            )
            logger.exception("Clustering failed for user_id=%s sheet=%s: %s", user_id, safe_sheet, exc)
            failed_sheets.append(safe_sheet)
            row = (
                db.query(SampleStage)
                .filter(
                    SampleStage.user_id == user_id,
                    SampleStage.stage_id == 9,
                    SampleStage.name == safe_sheet,
                )
                .first()
            )
            if row:
                row.status = "FAILED"
                db.commit()
    _progress_event(
        "Clusterização — processamento finalizado"
        + (
            " com falhas em: " + ", ".join(failed_sheets)
            if failed_sheets
            else " com sucesso."
        )
    )

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


# BILBO_LLM_DETAILED_PROGRESS_HANDLER
class _LLMDetailedProgressHandler(logging.Handler):
    """Encaminha eventos internos do LLM ao terminal do job."""

    def __init__(self) -> None:
        super().__init__(
            level=logging.WARNING
        )
        self._last_message = ""

    def emit(
        self,
        record: logging.LogRecord,
    ) -> None:
        try:
            message = record.getMessage().strip()

            if (
                not message
                or message == self._last_message
            ):
                return

            self._last_message = message
            parts = message.split()

            if (
                len(parts) == 4
                and parts[0] in {
                    "BP",
                    "MF",
                    "CC",
                }
                and parts[1].lower() in {
                    "up",
                    "down",
                    "upregulated",
                    "downregulated",
                }
                and parts[2].lower() == "cluster"
                and parts[3].isdigit()
            ):
                ontology = parts[0]
                direction = parts[1].lower()
                cluster_number = parts[3]

                direction_label = {
                    "up": "regulação positiva",
                    "upregulated": "regulação positiva",
                    "down": "regulação negativa",
                    "downregulated": "regulação negativa",
                }[direction]

                progress_message = (
                    "Interpretação LLM/RAG — "
                    f"processando cluster {cluster_number} "
                    f"({ontology}, {direction_label})."
                )

            elif message.startswith("Ollama:"):
                progress_message = (
                    "Interpretação LLM/RAG — "
                    + message[len("Ollama:"):].strip()
                )

            else:
                progress_message = (
                    "Interpretação LLM/RAG — "
                    + message[:500]
                )

            _progress_event(progress_message)

        except Exception:
            # Progresso nunca deve interromper a análise.
            return


def _run_llm_with_fallback(user_id: int, sheet: str, out_dir: str) -> dict[str, Any]:
    # BILBO_OLLAMA_MODELS_BEFORE_MANUAL_LLM
    progress_handler = _LLMDetailedProgressHandler()

    progress_loggers = [
        logging.getLogger(
            "backend.scripts.cluster_interpretation"
        ),
        logging.getLogger(
            "backend.scripts.llm"
        ),
        logging.getLogger(
            "backend.services.ollama_bootstrap"
        ),
        logging.getLogger(
            "backend.services.rag_retrieval"
        ),
    ]

    for progress_logger in progress_loggers:
        progress_logger.addHandler(
            progress_handler
        )

    _progress_event(
        "Interpretação LLM/RAG — "
        "verificando modelos e preparando execução."
    )

    try:
        from ..services.ollama_bootstrap import (
            ensure_required_ollama_models,
        )

        ensure_required_ollama_models()

        ensure_rag_database()
        logger.info(
            "Running prototype interpretation pipeline user_id=%s sheet=%s "
            "cluster_model=%s rag_model=%s embedding_model=%s",
            user_id,
            sheet,
            settings.cluster_interpretation_model,
            settings.rag_llm_model,
            settings.rag_embedding_model,
        )
        return llm_script.run_llm(
            file_path=None,
            sheet_name=sheet,
            out_dir=out_dir,
            user_id=user_id,
        )
    finally:
        for progress_logger in progress_loggers:
            progress_logger.removeHandler(
                progress_handler
            )

        _progress_event(
            "Interpretação LLM/RAG — "
            "execução interna finalizada."
        )


def _handle_llm(db: Session, job_id: str, user_id: int, payload: dict[str, Any]) -> None:
    # BILBO_LLM_PROGRESS_CONTEXT
    _set_progress_context(job_id, user_id, "llm")
    _progress_event(
        "Interpretação LLM/RAG — "
        f"job {job_id} iniciado."
    )

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
            for key in [
                "report",
                "html",
                "json",
                "rag_json",
                "cluster_interpretations",
                "prioritized_genes",
            ]:
                p = Path(res.get(key, ""))
                if p.exists():
                    add_artifact(
                        db, job_id=job_id, user_id=user_id, kind=p.suffix.replace(".", "") or "file", path=str(p)
                    )
            row = (
                db.query(SampleStage)
                .filter(
                    SampleStage.user_id == user_id,
                    SampleStage.stage_id == 10,
                    SampleStage.name == safe_sheet,
                )
                .first()
            )
            if row:
                row.status = "COMPLETED"
                db.commit()
        except Exception as exc:
            logger.exception("Prototype LLM/RAG failed for user_id=%s sheet=%s: %s", user_id, safe_sheet, exc)
            failed_sheets.append(safe_sheet)
            row = (
                db.query(SampleStage)
                .filter(
                    SampleStage.user_id == user_id,
                    SampleStage.stage_id == 10,
                    SampleStage.name == safe_sheet,
                )
                .first()
            )
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
