"""Celery import and STAR indexing for user supplied references."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

from ..core.settings import settings
from ..db.database import SessionLocal
from ..db.models import PipelineJob, SampleStage
from ..schemas.common import PipelineStatus
from ..services.job_service import append_job_event, set_job_finished, set_job_running
from ..services.reference_import import (
    download_public_file, gff3_to_star_gtf, materialize,
    validate_annotation, validate_fasta, validate_protein_fasta,
)
from .celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="reference.import")
def import_reference(job_id: str) -> None:
    db = SessionLocal()
    root = Path(settings.users_root) / "ref_genomes"
    incoming = root / "_incoming" / job_id
    final = None
    row = None
    try:
        job = set_job_running(db, job_id)
        payload = job.payload or {}
        accession = payload["accession"]
        final = root / accession
        row = db.query(SampleStage).filter(SampleStage.id == payload["row_id"],
                                           SampleStage.user_id == job.user_id).first()
        if row is None or final.exists():
            raise ValueError("Invalid or duplicate reference")
        row.status = "RUNNING"
        db.commit()
        source = payload["source"]
        if source["type"] == "url":
            append_job_event(job.user_id, job_id, "Referência: iniciando download dos arquivos.")
            incoming.mkdir(parents=True, exist_ok=False)
            local = {}
            for kind in ("fasta", "annotation", "protein"):
                if kind not in source:
                    continue
                url = source[kind]
                filename = unquote(Path(urlsplit(url).path).name)
                local[kind] = incoming / filename
                def progress(_kind, written, total):
                    _progress(db, job, "download_" + kind, written, total)
                download_public_file(url, local[kind], kind, progress)
        elif source["type"] == "upload":
            append_job_event(job.user_id, job_id, "Referência: usando arquivos enviados.")
            incoming = Path(source["directory"])
            if incoming.resolve().parent != (root / "_incoming").resolve():
                raise ValueError("Invalid upload staging path")
            local = {kind: Path(source[kind]) for kind in ("fasta", "annotation", "protein")
                     if kind in source}
            if any(path.resolve().parent != incoming.resolve() for path in local.values()):
                raise ValueError("Invalid upload file path")
        else:
            raise ValueError("Unknown reference source")

        _progress(db, job, "validating", 0, 0)
        append_job_event(job.user_id, job_id, "Referência: validando FASTA e anotação.")
        final.mkdir(parents=True, exist_ok=False)
        materialize(local["fasta"], final / "genomic.fa", "fasta")
        unpacked_annotation = final / "annotation.unpacked"
        annotation_ext = materialize(local["annotation"], unpacked_annotation, "annotation")
        annotation_path = final / ("genomic.gtf" if annotation_ext == ".gtf" else "genomic.gff3")
        unpacked_annotation.replace(annotation_path)
        fasta_ids = validate_fasta(final / "genomic.fa")
        validate_annotation(annotation_path, fasta_ids, annotation_ext)
        if "protein" in local:
            protein_path = final / "protein.fa"
            materialize(local["protein"], protein_path, "protein")
            protein_count = validate_protein_fasta(protein_path)
            logger.info("Reference %s has %s protein sequences", accession, protein_count)
        if annotation_ext != ".gtf":
            gff3_to_star_gtf(annotation_path, final / "genomic.gtf")
        _progress(db, job, "indexing", 0, 0)
        append_job_event(job.user_id, job_id, "Referência: construindo índice STAR.")
        command = ["bash", "/app/backend/scripts/index_genome_star.sh", str(final),
                   str(payload["sjdb_overhang"]), str(payload["threads"])]
        run = subprocess.run(command, capture_output=True, text=True, timeout=172800)
        if run.returncode or not (final / "STAR_index" / "Genome").is_file():
            log = Path("/app/backend/logs/index_genome_star.log")
            tail = log.read_text(errors="replace")[-3000:] if log.exists() else run.stderr[-3000:]
            raise RuntimeError("STAR indexing failed: " + tail)
        size = sum(path.stat().st_size for path in final.rglob("*") if path.is_file())
        row.status = "COMPLETED"
        row.size = f"{size / 1024**3:.2f} GB"
        set_job_finished(db, job_id, PipelineStatus.COMPLETED,
                         result={"accession": accession, "progress_percent": 100,
                                 "progress_message": "Reference ready"})
        db.commit()
    except Exception as exc:
        logger.exception("Reference import failed for job %s", job_id)
        if row is not None:
            row.status = "FAILED"
            db.commit()
        set_job_finished(db, job_id, PipelineStatus.FAILED, error_message=str(exc)[:4000])
        if final is not None:
            shutil.rmtree(final, ignore_errors=True)
    finally:
        shutil.rmtree(incoming, ignore_errors=True)
        db.close()


def _progress(db, job: PipelineJob, phase: str, written: int, total: int) -> None:
    previous_phase = (job.result or {}).get("phase")
    if phase != previous_phase and phase.startswith("download_"):
        append_job_event(job.user_id, job.id, f"Referência: baixando {phase.removeprefix('download_')}.")
    if total and phase == "download_fasta":
        percent = round(35 * written / total, 1)
    elif total and phase == "download_annotation":
        percent = round(35 + 35 * written / total, 1)
    elif phase == "validating":
        percent = 75
    else:
        percent = None
    job.result = {"phase": phase, "bytes": written, "total_bytes": total,
                  "progress_percent": percent, "progress_message": phase}
    db.add(job)
    db.commit()
