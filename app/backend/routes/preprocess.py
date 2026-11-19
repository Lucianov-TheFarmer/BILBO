from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from ..db.database import SessionLocal, get_db
from ..db.models import SampleStage, User
from ..schemas.common import PipelineStatus
from ..services.job_service import create_job, set_job_finished, set_job_running
from ..utils import get_current_user, manager
import os
import asyncio
import subprocess
from pathlib import Path

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

    # Buscar todos os arquivos de quantificação do usuário (stage_id=6, status completed)
    quant_samples = db.query(SampleStage).filter(
        SampleStage.stage_id == 6,
        SampleStage.user_id == user_id,
        SampleStage.status.in_(["COMPLETED", "Completed"])
    ).all()
    sra_to_filename = {s.sra_code: s.name for s in quant_samples}

    # --- VERIFICAÇÃO DE REPETIÇÕES DUPLICADAS ENTRE GRUPOS ---
    file_to_group = {}
    for contrast in contrasts:
        try:
            left, right = contrast.name.split("*")
            group_1 = left.split("(")[0].strip()
            group_2 = right.split("(")[0].strip()
            reps_1 = left[left.find("(")+1:left.find(")")].split(";") if "(" in left and ")" in left else []
            reps_2 = right[right.find("(")+1:right.find(")")].split(";") if "(" in right and ")" in right else []
        except Exception:
            continue

        files_1 = set()
        for sra in reps_1:
            sra = sra.strip()
            filename = sra_to_filename.get(sra)
            if filename:
                files_1.add(filename)
        files_2 = set()
        for sra in reps_2:
            sra = sra.strip()
            filename = sra_to_filename.get(sra)
            if filename:
                files_2.add(filename)

        # Verifica se há interseção entre arquivos dos grupos no mesmo contraste
        if files_1 & files_2:
            raise HTTPException(
                status_code=400,
                detail="Repetições incompatíveis: uma mesma amostra foi selecionada para mais de um grupo em um contraste."
            )

        # Verifica se algum arquivo já foi usado em outro grupo em outros contrastes
        for f in files_1:
            if f in file_to_group and file_to_group[f] != group_1:
                raise HTTPException(
                    status_code=400,
                    detail="Repetições incompatíveis: uma mesma amostra foi selecionada para grupos diferentes em diferentes contrastes."
                )
            file_to_group[f] = group_1
        for f in files_2:
            if f in file_to_group and file_to_group[f] != group_2:
                raise HTTPException(
                    status_code=400,
                    detail="Repetições incompatíveis: uma mesma amostra foi selecionada para grupos diferentes em diferentes contrastes."
                )
            file_to_group[f] = group_2

    # Evitar duplicação de linhas no Targets.txt (mesmo arquivo, grupo e descrição)
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

    # Deduplicação final robusta (preserva ordem)
    lines = list(dict.fromkeys(lines))

    # Caminho correto: users/{user_id}/preprocess/Targets.txt (users está no mesmo nível de app)
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../users", str(user_id), "preprocess"))
    os.makedirs(base_dir, exist_ok=True)
    targets_path = os.path.join(base_dir, "Targets.txt")
    with open(targets_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    # Executar o R em background e acompanhar sua finalização.
    script_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../scripts/preprocess.R")
    )

    job = create_job(db, "preprocess", user_id, {"contrast_ids": contrast_ids})
    log_path = Path(base_dir) / f"preprocess_{job.id}.log"
    try:
        with log_path.open("wb") as log_stream:
            process = await asyncio.create_subprocess_exec(
                "Rscript", script_path, str(user_id), cwd=base_dir,
                stdout=log_stream, stderr=subprocess.STDOUT,
            )
        set_job_running(db, job.id)
    except Exception as e:
        set_job_finished(db, job.id, PipelineStatus.FAILED, error_message=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao iniciar pré-processamento: {e}",
        )

    async def wait_and_notify():
        rc = await process.wait()
        try:
            log_tail = log_path.read_text(encoding="utf-8", errors="replace")[-2000:]
        except OSError:
            log_tail = ""
        detail = log_tail.strip() or f"Rscript terminou com código {rc}."
        with SessionLocal() as job_db:
            set_job_finished(
                job_db, job.id,
                PipelineStatus.COMPLETED if rc == 0 else PipelineStatus.FAILED,
                result={"exit_code": rc, "log_tail": log_tail},
                error_message=None if rc == 0 else f"Pré-processamento falhou (código {rc}): {detail[-1200:]}",
            )

        if rc == 0:
            message = "Pré-processamento finalizado com sucesso!"
        else:
            message = f"Pré-processamento falhou (código {rc}): {detail[-500:]}"

        try:
            await manager.broadcast(message, user_id=user_id)
        except Exception as exc:
            print(f"Erro ao enviar notificação do pré-processamento: {exc}")

    asyncio.create_task(wait_and_notify())

    return {
        "status": "success",
        "message": "Pré-processamento iniciado com sucesso.",
        "pid": process.pid,
        "job_id": job.id,
    }
