from fastapi import APIRouter, HTTPException, Depends, status, Request
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import SampleStage, User
from ..utils import get_current_user
import logging

router = APIRouter()

@router.get("/contrasts/samples")
def get_completed_samples(stage_id: int = 6, status: str = "Completed", db: Session = Depends(get_db)):
    """
    Fetch samples from sample_stages with the given stage_id and status.
    """
    samples = db.query(SampleStage).filter_by(stage_id=stage_id, status=status).all()
    if not samples:
        raise HTTPException(status_code=404, detail="No samples found.")
    return [{"id": sample.id, "name": sample.name} for sample in samples]

@router.get("/contrasts/")
def list_contrasts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Lista todos os contrastes cadastrados para o usuário autenticado.
    """
    contrasts = db.query(SampleStage).filter(
        SampleStage.stage_id == 8,
        SampleStage.user_id == current_user.id,
        SampleStage.status == "Contrast"
    ).all()
    return [
        {
            "id": contrast.id,
            "name": contrast.name,
            "status": contrast.status,
        }
        for contrast in contrasts
    ]

@router.post("/contrasts/save")
async def save_contrasts(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Recebe os dados de contrastes do frontend e salva no banco de dados.
    """
    logger = logging.getLogger(__name__)
    data = await request.json()
    contrasts = data.get("contrasts", [])
    user_id = current_user.id

    if not contrasts:
        logger.error("Nenhum contraste recebido.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nenhum contraste recebido.")

    logger.info(f"Recebendo {len(contrasts)} contrastes para o usuário {user_id}")

    # Buscar todos os SampleStage relevantes para mapear id -> sra_code
    all_ids = set()
    for contrast in contrasts:
        all_ids.update(contrast.get("repetitions_1", []))
        all_ids.update(contrast.get("repetitions_2", []))
    # Converter ids para int
    all_ids = {int(i) for i in all_ids if i}

    id_to_sra = {}
    if all_ids:
        samples = db.query(SampleStage).filter(SampleStage.id.in_(all_ids)).all()
        id_to_sra = {str(sample.id): sample.sra_code for sample in samples}

    for contrast in contrasts:
        group_1 = contrast.get("group_1")
        group_2 = contrast.get("group_2")
        reps_1 = [str(r) for r in contrast.get("repetitions_1", [])]
        reps_2 = [str(r) for r in contrast.get("repetitions_2", [])]

        # Mapear ids para sra_code
        sra_codes_1 = [id_to_sra.get(r, r) for r in reps_1]
        sra_codes_2 = [id_to_sra.get(r, r) for r in reps_2]

        # Montar o nome no formato desejado
        group_1_str = f"{group_1}({';'.join(sra_codes_1)})" if sra_codes_1 else group_1
        group_2_str = f"{group_2}({';'.join(sra_codes_2)})" if sra_codes_2 else group_2
        contrast_name = f"{group_1_str}*{group_2_str}"

        db.add(SampleStage(
            stage_id=8,  # Use o stage_id desejado
            name=contrast_name,
            status="Contrast",
            user_id=user_id,
        ))

    db.commit()
    logger.info("Contrastes salvos com sucesso.")
    return {"status": "success", "message": "Contrastes salvos com sucesso."}

@router.delete("/contrasts/{contrast_id}")
def delete_contrast(
    contrast_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Remove um contraste do banco de dados pelo id.
    """
    logger = logging.getLogger(__name__)
    contrast = db.query(SampleStage).filter(
        SampleStage.id == contrast_id,
        SampleStage.user_id == current_user.id,
        SampleStage.stage_id == 8,
        SampleStage.status == "Contrast"
    ).first()
    if not contrast:
        logger.error(f"Contrast {contrast_id} not found for user {current_user.id}.")
        raise HTTPException(status_code=404, detail="Contrast not found")
    db.delete(contrast)
    db.commit()
    logger.info(f"Contrast {contrast_id} deleted successfully.")
    return {"message": f"Contrast {contrast_id} deleted successfully."}
