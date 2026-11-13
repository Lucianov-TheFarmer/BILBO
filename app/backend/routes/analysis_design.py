"""Save and validate metadata for an additive edgeR model."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db.database import get_db
from ..db.models import AnalysisDesign, User
from ..services.analysis_design import contrast_context, validate_design
from ..utils import get_current_user

router = APIRouter(prefix="/analysis-design")


class DesignRequest(BaseModel):
    contrast_ids: list[int] = Field(min_length=1)
    variables: list[dict] = Field(default_factory=list)


@router.get("/context")
def context(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        return contrast_context(db, user.id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("")
def saved_design(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.query(AnalysisDesign).filter(AnalysisDesign.user_id == user.id).first()
    return {"config": row.config if row else None}


@router.post("/validate")
def validate(request: DesignRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        return validate_design(db, user.id, request.model_dump())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.put("")
def save(request: DesignRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        validated = validate_design(db, user.id, request.model_dump())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    row = db.query(AnalysisDesign).filter(AnalysisDesign.user_id == user.id).first()
    config = {"contrast_ids": request.contrast_ids, "variables": validated["variables"]}
    if row is None:
        row = AnalysisDesign(user_id=user.id, config=config)
        db.add(row)
    else:
        row.config = config
    db.commit()
    return {"config": config, "preview": validated}
