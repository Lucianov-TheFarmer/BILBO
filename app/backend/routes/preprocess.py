from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from ..db.database import get_db
from ..db.models import SampleStage, User
from ..utils import get_current_user
import os
import subprocess

router = APIRouter()

@router.post("/preprocess/start")
async def start_preprocess(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Cria a pasta preprocess e o arquivo Targets.txt para os contrastes selecionados.
    """
    data = await request.json()
    contrast_ids = data.get("contrast_ids", [])
    user_id = current_user.id

    if not contrast_ids:
        raise HTTPException(status_code=400, detail="Nenhum contraste selecionado.")

    # Buscar contrastes do usuário
    contrasts = db.query(SampleStage).filter(
        SampleStage.id.in_(contrast_ids),
        SampleStage.user_id == user_id,
        SampleStage.stage_id == 8,
        SampleStage.status == "Contrast"
    ).all()

    if not contrasts:
        raise HTTPException(status_code=404, detail="Contrastes não encontrados.")

    # Buscar todos os arquivos de quantificação do usuário (stage_id=6, status="Completed")
    quant_samples = db.query(SampleStage).filter(
        SampleStage.stage_id == 6,
        SampleStage.user_id == user_id,
        SampleStage.status == "Completed"
    ).all()
    sra_to_filename = {s.sra_code: s.name for s in quant_samples}

    lines = ["files\tgroup\tdescription"]
    for contrast in contrasts:
        # Exemplo de nome: Sun_C1(A1;A2;A3;A4)*Shade_C1(A5;A6;A7;A8)
        try:
            left, right = contrast.name.split("*")
            group_1 = left.split("(")[0].strip()
            group_2 = right.split("(")[0].strip()
            reps_1 = left[left.find("(")+1:left.find(")")].split(";") if "(" in left and ")" in left else []
            reps_2 = right[right.find("(")+1:right.find(")")].split(";") if "(" in right and ")" in right else []
        except Exception:
            continue

        for sra in reps_1:
            sra = sra.strip()
            filename = sra_to_filename.get(sra)
            if filename:
                lines.append(f"../quantification/{filename}\t{group_1}\t{group_1}")
        for sra in reps_2:
            sra = sra.strip()
            filename = sra_to_filename.get(sra)
            if filename:
                lines.append(f"../quantification/{filename}\t{group_2}\t{group_2}")

    # Caminho correto: users/{user_id}/preprocess/Targets.txt (users está no mesmo nível de app)
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../users", str(user_id), "preprocess"))
    os.makedirs(base_dir, exist_ok=True)
    targets_path = os.path.join(base_dir, "Targets.txt")
    with open(targets_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    # Execute o script R em background, passando user_id como argumento
    script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../scripts/preprocess.R"))
    try:
        subprocess.Popen(["Rscript", script_path, str(user_id)])
    except Exception as e:
        # Logue o erro, mas não interrompa a resposta
        print(f"Erro ao executar o script R: {e}")

    return {"status": "success", "message": "Targets.txt criado com sucesso."}
