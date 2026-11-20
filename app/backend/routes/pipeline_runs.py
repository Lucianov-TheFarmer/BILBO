"""Persistent automatic pipeline plans and run status."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db.database import get_db
from ..db.models import PipelineJob, PipelineRun, PipelineStep, SampleStage, User
from ..services.analysis_design import SAMPLE_NAME, validate_design
from ..core.settings import settings
from ..utils import get_current_user, get_current_user_compat
from ..utils_paths import safe_resolve_user_path

router = APIRouter(prefix="/pipeline")
STAGES = ("qc_raw", "trimming", "qc_trim", "alignment", "quantification", "deg", "clustering", "llm")
SOURCES = {"existing", "sra", "drive", "upload"}


class SamplePlan(BaseModel):
    name: str
    source: str = "existing"
    paired: bool = True


class PipelinePlan(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    samples: list[SamplePlan] = Field(min_length=1, max_length=100)
    stages: dict[str, bool]
    genome: Optional[str] = None
    quality: dict = Field(default_factory=dict)
    trimming: dict = Field(default_factory=dict)
    alignment: dict = Field(default_factory=dict)
    quantification: dict = Field(default_factory=dict)
    deg: dict = Field(default_factory=dict)
    design: Optional[dict] = None
    reuse_existing: bool = True


def _validated_plan(db: Session, user_id: int, plan: PipelinePlan) -> dict:
    config = plan.model_dump()
    if not config["reuse_existing"]:
        raise ValueError("Rerunning existing artifacts is not supported; remove them first")
    names = [sample["name"] for sample in config["samples"]]
    if len(set(names)) != len(names) or any(not SAMPLE_NAME.fullmatch(name) for name in names):
        raise ValueError("Sample names must be unique and contain only letters, numbers, '.', '_' or '-'")
    for sample in config["samples"]:
        if sample["source"] not in SOURCES:
            raise ValueError("Unknown sample source")
        if sample["source"] == "sra" and not re.fullmatch(r"(?:SRR|ERR|DRR)[0-9]+", sample["name"], re.I):
            raise ValueError("SRA samples require a valid SRR, ERR or DRR accession")
    if any(key not in STAGES for key in config["stages"]):
        raise ValueError("Unknown pipeline stage")
    enabled = {name for name, value in config["stages"].items() if value}
    if not enabled:
        raise ValueError("Choose at least one analysis")
    if "clustering" in enabled and "deg" not in enabled:
        raise ValueError("Semantic clustering requires differential analysis in this pipeline")
    if "llm" in enabled and "clustering" not in enabled:
        raise ValueError("LLM interpretation requires semantic clustering in this pipeline")
    if ("alignment" in enabled or "quantification" in enabled or "deg" in enabled) and not config["genome"]:
        raise ValueError("Choose a reference genome")
    if config["genome"]:
        genome = str(config["genome"])
        row = db.query(SampleStage).filter(
            SampleStage.user_id == user_id, SampleStage.stage_id == 7,
            SampleStage.sra_code == genome,
        ).first()
        if row is None:
            raise ValueError("The selected reference genome was not found")
    alignment_threads = int(config["alignment"].get("threads", 8))
    trimming_threads = int(config["trimming"].get("threads", 4))
    if not 1 <= alignment_threads <= 256 or not 1 <= trimming_threads <= 256:
        raise ValueError("Thread count must be between 1 and 256")
    config["alignment"]["threads"] = alignment_threads
    config["trimming"]["threads"] = trimming_threads
    if set(config["quality"]) - {"raw_memory_mb", "post_memory_mb"}:
        raise ValueError("Unknown quality analysis parameter")
    for key in ("raw_memory_mb", "post_memory_mb"):
        quality_memory = int(config["quality"].get(key, 512))
        if not 256 <= quality_memory <= 16384:
            raise ValueError("FastQC memory must be between 256 and 16384 MiB")
        config["quality"][key] = quality_memory
    trimming_memory = int(config["trimming"].get("memory_mb", 1024))
    if not 512 <= trimming_memory <= 32768:
        raise ValueError("Trimmomatic memory must be between 512 and 32768 MiB")
    config["trimming"]["memory_mb"] = trimming_memory
    if set(config["deg"]) - {"diamond_threads"}:
        raise ValueError("Unknown differential analysis parameter")
    diamond_threads = int(config["deg"].get("diamond_threads", 8))
    if not 1 <= diamond_threads <= 256:
        raise ValueError("DIAMOND CPU count must be between 1 and 256")
    config["deg"]["diamond_threads"] = diamond_threads
    trim = config["trimming"]
    if trim.get("phred", "autodetect") not in ("autodetect", "phred33", "phred64"):
        raise ValueError("Invalid Phred encoding")
    adapter = trim.get("illumina_clip") or {}
    allowed_adapters = {"NexteraPE-PE.fa", "TruSeq2-PE.fa", "TruSeq2-SE.fa",
                        "TruSeq3-PE-2.fa", "TruSeq3-PE.fa", "TruSeq3-SE.fa", "Personalizado"}
    if not isinstance(adapter, dict) or adapter.get("Arquivo adaptadores", "TruSeq3-PE.fa") not in allowed_adapters:
        raise ValueError("Invalid adapter selection")
    if adapter.get("Arquivo adaptadores") == "Personalizado":
        content = str(adapter.get("Conteudo personalizado") or "")
        if not content.startswith(">") or len(content) > 100_000:
            raise ValueError("Provide a valid custom adapter FASTA")
    for key in ("leading", "trailing", "minlen", "crop", "headcrop", "avgqual"):
        if trim.get(key) not in (None, ""):
            number = int(trim[key])
            if not 0 <= number <= 10000:
                raise ValueError(f"Invalid trimming parameter: {key}")
            trim[key] = number
    for key in ("Seed mismatches", "Threshold palindromo", "Threshold simples",
                "Comprimento minimo adaptador"):
        if key in adapter:
            number = int(adapter[key])
            if not 0 <= number <= 10000:
                raise ValueError(f"Invalid adapter parameter: {key}")
    for section, keys in (("sliding_window", ("Tamanho janela", "Qualidade minima")),
                          ("max_info", ("Comprimento alvo",))):
        values = trim.get(section) or {}
        if not isinstance(values, dict):
            raise ValueError(f"Invalid {section} settings")
        for key in keys:
            if key in values and not 0 <= int(values[key]) <= 10000:
                raise ValueError(f"Invalid {section} parameter: {key}")
    if "Strictness" in (trim.get("max_info") or {}):
        strictness = float(trim["max_info"]["Strictness"])
        if not 0 <= strictness <= 1:
            raise ValueError("Strictness must be between 0 and 1")
    allowed_star = {"outFilterType", "outFilterMultimapNmax", "alignSJoverhangMin",
                    "alignSJDBoverhangMin", "outFilterMismatchNmax",
                    "outFilterMismatchNoverReadLmax", "alignIntronMin", "alignIntronMax",
                    "alignMatesGapMax"}
    if any(key not in allowed_star | {"threads"} for key in config["alignment"]):
        raise ValueError("Unknown STAR parameter")
    for key, value in config["alignment"].items():
        if key == "threads" or value in (None, ""):
            continue
        if key == "outFilterType":
            if value not in ("Normal", "BySJout"):
                raise ValueError("Invalid STAR filter type")
        elif key == "outFilterMismatchNoverReadLmax":
            if not 0 <= float(value) <= 1:
                raise ValueError(f"Invalid STAR parameter: {key}")
        elif not 0 <= int(value) <= 1_000_000_000:
            raise ValueError(f"Invalid STAR parameter: {key}")
    quant = config["quantification"]
    if not isinstance(quant, dict) or not all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.:-]{0,79}",
                                                str(quant.get(key, default)))
                                                for key, default in (("feature_type", "gene"),
                                                                     ("id_attribute", "ID"))):
        raise ValueError("Invalid quantification feature or attribute")
    if "deg" in enabled:
        if not config["design"]:
            raise ValueError("Configure groups, contrasts and the edgeR model")
        preview = validate_design(db, user_id, config["design"])
        if set(preview["samples"]) != set(names):
            raise ValueError("The pipeline samples must match the selected contrast samples")
        config["design"] = {"contrast_ids": config["design"]["contrast_ids"],
                            "variables": preview["variables"]}
        config["design_snapshot"] = preview
    return config


def _detail(run: PipelineRun) -> dict:
    return {"id": run.id, "status": run.status, "config": run.config,
            "error_message": run.error_message, "created_at": run.created_at,
            "started_at": run.started_at, "finished_at": run.finished_at,
            "steps": [{"id": step.id, "sample": step.sample, "stage": step.stage,
                       "status": step.status, "job_id": step.job_id,
                       "error_message": step.error_message} for step in run.steps]}


@router.get("/options")
def options(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(SampleStage).filter(SampleStage.user_id == user.id,
                                         SampleStage.stage_id == 1).all()
    samples = {}
    for row in rows:
        if row.sra_code:
            samples.setdefault(row.sra_code, []).append({"name": row.name, "status": row.status})
    active_drive = db.query(PipelineJob).filter(
        PipelineJob.user_id == user.id, PipelineJob.stage == "drive_import",
        PipelineJob.status.in_(["PENDING", "RUNNING"])).all()
    for job in active_drive:
        payload = job.payload or {}
        base = payload.get("base")
        if not base or base in samples:
            continue
        samples[base] = [{"name": f"{base}_{file['mate']}.fastq.gz",
                          "status": job.status, "source": "drive"}
                         for file in payload.get("files", []) if file.get("mate") in (1, 2)]
    genomes = db.query(SampleStage).filter(SampleStage.user_id == user.id,
                                            SampleStage.stage_id == 7).all()
    return {"samples": samples, "genomes": [{"id": row.sra_code, "name": row.name,
                                               "status": row.status}
                                             for row in genomes]}


@router.post("/runs", status_code=201)
def create_run(plan: PipelinePlan, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        config = _validated_plan(db, user.id, plan)
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    run = PipelineRun(id=uuid.uuid4().hex, user_id=user.id, status="DRAFT", config=config)
    db.add(run)
    _add_steps(db, run, config)
    db.commit()
    db.refresh(run)
    return _detail(run)


def _add_steps(db: Session, run: PipelineRun, config: dict):
    enabled = {name for name, value in config["stages"].items() if value}
    for sample in config["samples"]:
        for stage in ("input", *[stage for stage in STAGES if stage in enabled and stage not in ("deg", "clustering", "llm")]):
            db.add(PipelineStep(id=uuid.uuid4().hex, run_id=run.id,
                                sample=sample["name"], stage=stage, status="WAITING"))
    for stage in ("deg", "clustering", "llm"):
        if stage in enabled:
            db.add(PipelineStep(id=uuid.uuid4().hex, run_id=run.id,
                                sample="__all__", stage=stage, status="WAITING"))


@router.get("/runs")
def list_runs(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(PipelineRun).filter(PipelineRun.user_id == user.id).order_by(
        PipelineRun.created_at.desc()).limit(30).all()
    return [_detail(row) for row in rows]


@router.get("/runs/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.query(PipelineRun).filter(PipelineRun.id == run_id,
                                       PipelineRun.user_id == user.id).first()
    if row is None:
        raise HTTPException(404, "Pipeline run not found")
    return _detail(row)


@router.put("/runs/{run_id}")
def update_draft(run_id: str, plan: PipelinePlan, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    run = db.query(PipelineRun).filter(PipelineRun.id == run_id,
                                       PipelineRun.user_id == user.id).first()
    if run is None:
        raise HTTPException(404, "Pipeline run not found")
    if run.status != "DRAFT":
        raise HTTPException(409, "Only a draft can be edited")
    try:
        config = _validated_plan(db, user.id, plan)
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    for step in list(run.steps):
        db.delete(step)
    db.flush()
    run.config = config
    _add_steps(db, run, config)
    db.commit()
    db.refresh(run)
    return _detail(run)


@router.delete("/runs/{run_id}")
def delete_draft(run_id: str, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    run = db.query(PipelineRun).filter(PipelineRun.id == run_id,
                                       PipelineRun.user_id == user.id).first()
    if run is None:
        raise HTTPException(404, "Pipeline run not found")
    if run.status != "DRAFT":
        raise HTTPException(409, "Only a draft can be deleted")
    for step in list(run.steps):
        db.delete(step)
    db.delete(run)
    db.commit()
    return {"status": "deleted"}


@router.post("/runs/{run_id}/start")
def start_run(run_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    run = db.query(PipelineRun).filter(PipelineRun.id == run_id,
                                       PipelineRun.user_id == user.id).first()
    if run is None:
        raise HTTPException(404, "Pipeline run not found")
    if run.status != "DRAFT":
        raise HTTPException(409, "Only a draft can be started")
    if db.query(PipelineRun).filter(PipelineRun.user_id == user.id,
                                    PipelineRun.status == "RUNNING").first():
        raise HTTPException(409, "Another pipeline is already running")
    try:
        validated = _validated_plan(db, user.id, PipelinePlan(**run.config))
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    run.config = validated
    run.status = "RUNNING"
    run.started_at = datetime.now(timezone.utc)
    db.commit()
    return _detail(run)


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    run = db.query(PipelineRun).filter(PipelineRun.id == run_id,
                                       PipelineRun.user_id == user.id).first()
    if run is None:
        raise HTTPException(404, "Pipeline run not found")
    if run.status not in ("DRAFT", "RUNNING"):
        raise HTTPException(409, "Pipeline is already finished")
    run.status = "CANCELED"
    run.finished_at = datetime.now(timezone.utc)
    for step in run.steps:
        if step.status == "WAITING":
            step.status = "CANCELED"
    db.commit()
    return _detail(run)


@router.post("/runs/{run_id}/retry")
def retry_run(run_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    run = db.query(PipelineRun).filter(PipelineRun.id == run_id,
                                       PipelineRun.user_id == user.id).first()
    if run is None:
        raise HTTPException(404, "Pipeline run not found")
    if run.status != "FAILED":
        raise HTTPException(409, "Only a failed pipeline can be retried")
    if db.query(PipelineRun).filter(PipelineRun.user_id == user.id,
                                    PipelineRun.status == "RUNNING").first():
        raise HTTPException(409, "Another pipeline is already running")
    for step in run.steps:
        if step.status in ("FAILED", "BLOCKED"):
            step.status = "WAITING"
            step.job_id = None
            step.error_message = None
    run.status = "RUNNING"
    run.error_message = None
    run.finished_at = None
    db.commit()
    return _detail(run)


@router.get("/runs/{run_id}/file/{filename}")
def download_result(run_id: str, filename: str, request: Request,
                    db: Session = Depends(get_db), user: User = Depends(get_current_user_compat)):
    run = db.query(PipelineRun).filter(PipelineRun.id == run_id,
                                       PipelineRun.user_id == user.id).first()
    if run is None or filename not in ("DEG.xlsx", "DEG_full.xlsx"):
        raise HTTPException(404, "Pipeline result not found")
    path = safe_resolve_user_path(settings.users_root, user.id, "pipelines", run.id, "DEG", filename)
    if not path.is_file():
        raise HTTPException(404, "Pipeline result not found")
    return FileResponse(path, filename=filename)
