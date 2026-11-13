"""Configure contrasts and edgeR metadata together in one transaction."""

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db.database import get_db
from ..db.models import AnalysisDesign, PipelineJob, SampleStage, User
from ..services.analysis_design import SAMPLE_NAME, validate_design, validate_design_context
from ..utils import get_current_user

router = APIRouter(prefix="/contrasts/configure")
GROUP_NAME = re.compile(r"^[^*();\t\r\n]{1,40}$")


class ContrastConfiguration(BaseModel):
    known_ids: list[int] = Field(default_factory=list)
    contrasts: list[dict] = Field(default_factory=list)
    variables: list[dict] = Field(default_factory=list)


def _available_samples(db: Session, user_id: int) -> set[str]:
    rows = db.query(SampleStage.sra_code).filter(
        SampleStage.user_id == user_id, SampleStage.stage_id.in_([1, 6])).all()
    available = {name for (name,) in rows if name}
    jobs = db.query(PipelineJob).filter(
        PipelineJob.user_id == user_id, PipelineJob.stage == "drive_import",
        PipelineJob.status.in_(["PENDING", "RUNNING"])).all()
    available.update((job.payload or {}).get("base") for job in jobs)
    available.discard(None)
    return available


def _prepared(db: Session, user_id: int, request: ContrastConfiguration):
    if not request.contrasts:
        raise ValueError("Add at least one contrast before validating the model")
    available = _available_samples(db, user_id)
    owned = {row.id: row for row in db.query(SampleStage).filter(
        SampleStage.user_id == user_id, SampleStage.stage_id == 8,
        SampleStage.status == "Contrast").all()}
    if len(set(request.known_ids)) != len(request.known_ids) or not set(request.known_ids) <= set(owned):
        raise ValueError("The contrast list changed; reopen the editor")
    used_ids = set()
    groups = {}
    prepared = []
    context = {"samples": groups, "contrasts": []}
    for index, item in enumerate(request.contrasts):
        identifier = item.get("id")
        if identifier is not None:
            if not isinstance(identifier, int) or identifier not in request.known_ids or identifier in used_ids:
                raise ValueError("Invalid or duplicate contrast ID")
            used_ids.add(identifier)
        left = str(item.get("group_1") or "").strip()
        right = str(item.get("group_2") or "").strip()
        if not GROUP_NAME.fullmatch(left) or not GROUP_NAME.fullmatch(right) or left == right:
            raise ValueError("Enter two different valid group names")
        sides = []
        for number, group in ((1, left), (2, right)):
            names = item.get(f"repetitions_{number}") or []
            if not isinstance(names, list) or not names or any(not isinstance(name, str) for name in names):
                raise ValueError("Choose distinct samples for both groups")
            if len(names) != len(set(names)):
                raise ValueError("Choose distinct samples for both groups")
            if any(not isinstance(name, str) or not SAMPLE_NAME.fullmatch(name) or name not in available
                   for name in names):
                raise ValueError("A selected sample is unavailable; refresh the sample list")
            for name in names:
                if name in groups and groups[name] != group:
                    raise ValueError(f"Sample {name} belongs to multiple groups")
                groups[name] = group
            sides.append({"group": group, "samples": names})
        name = f"{left}({';'.join(sides[0]['samples'])})*{right}({';'.join(sides[1]['samples'])})"
        prepared.append((identifier, name))
        context["contrasts"].append({"id": identifier if identifier is not None else -(index + 1),
                                     "name": name, "positive": sides[0], "negative": sides[1]})
    preview = validate_design_context(context, {"variables": request.variables})
    return owned, prepared, preview


@router.post("/validate")
def preview_configuration(request: ContrastConfiguration, db: Session = Depends(get_db),
                          user: User = Depends(get_current_user)):
    try:
        return _prepared(db, user.id, request)[2]
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("")
def save_configuration(request: ContrastConfiguration, db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    try:
        if not request.contrasts:
            owned = {row.id: row for row in db.query(SampleStage).filter(
                SampleStage.user_id == user.id, SampleStage.stage_id == 8,
                SampleStage.status == "Contrast").all()}
            if not set(request.known_ids) <= set(owned):
                raise ValueError("The contrast list changed; reopen the editor")
            for identifier in request.known_ids:
                db.delete(owned[identifier])
            design = db.query(AnalysisDesign).filter(AnalysisDesign.user_id == user.id).first()
            if design:
                db.delete(design)
            db.commit()
            return {"config": None, "preview": None, "contrasts": []}
        owned, prepared, _ = _prepared(db, user.id, request)
        keep = set()
        for identifier, name in prepared:
            if identifier is None:
                row = SampleStage(user_id=user.id, stage_id=8, name=name, status="Contrast")
                db.add(row)
                db.flush()
            else:
                row = owned[identifier]
                row.name = name
            keep.add(row.id)
        for identifier in set(request.known_ids) - keep:
            db.delete(owned[identifier])
        db.flush()
        preview = validate_design(db, user.id, {"contrast_ids": sorted(keep),
                                                "variables": request.variables})
        config = {"contrast_ids": sorted(keep), "variables": preview["variables"]}
        design = db.query(AnalysisDesign).filter(AnalysisDesign.user_id == user.id).first()
        if design is None:
            db.add(AnalysisDesign(user_id=user.id, config=config))
        else:
            design.config = config
        db.commit()
        return {"config": config, "preview": preview,
                "contrasts": [{"id": row.id, "name": row.name} for row in
                              db.query(SampleStage).filter(SampleStage.id.in_(keep)).all()]}
    except ValueError as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc
    except Exception:
        db.rollback()
        raise
