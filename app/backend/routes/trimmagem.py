from fastapi import APIRouter, Depends, HTTPException, status, Form
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import SampleStage, User  # Substitua 'Sample' por 'SampleStage'
from ..utils import get_current_user
import subprocess
import os
import json
import logging

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

router = APIRouter()

@router.post("/trimmagem/")
def start_trimmagem(
    selected_samples: str = Form(...),  # Recebe os samples selecionados como string JSON
    threads: int = Form(1),
    phred: str = Form("autodetect"),
    illumina_clip: str = Form(...),
    sliding_window: str = Form(...),
    max_info: str = Form(...),
    leading: int = Form(3),
    trailing: int = Form(3),
    crop: str = Form(None),
    headcrop: str = Form(None),
    minlen: int = Form(36),
    avgqual: str = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    logger.info("Starting trimmagem process...")
    try:
        user_id = current_user.id
        logger.info(f"User ID: {user_id}")
        base_path = f"../users/{user_id}/samples"
        trimmed_path = f"../users/{user_id}/trimmed"
        logger.info(f"Base path: {base_path}, Trimmed path: {trimmed_path}")

        logger.info(f"Selected samples: {selected_samples}")
        # Deserialize JSON strings
        try:
            illumina_clip = json.loads(illumina_clip)
            sliding_window = json.loads(sliding_window)
            max_info = json.loads(max_info)
            selected_samples = json.loads(selected_samples)  # Lista de amostras selecionadas
            logger.info("Parameters deserialized successfully.")
        except json.JSONDecodeError as e:
            logger.error(f"Error deserializing parameters: {e}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid JSON format: {e}")

        # Classificar amostras em PE e SE
        paired_samples = []
        single_samples = []

        for sample in selected_samples:
            if sample.endswith("_2.fastq"):
                paired_samples.append(sample.replace("_2.fastq", ""))  # Adiciona o prefixo base do par
            elif sample.endswith("_1.fastq") and f"{sample.replace('_1.fastq', '_2.fastq')}" not in selected_samples:
                single_samples.append(sample)  # Adiciona como SE se não houver par correspondente

        # Remover duplicatas de pares
        paired_samples = list(set(paired_samples))
        logger.info(f"Paired samples: {paired_samples}")
        logger.info(f"Single samples: {single_samples}")

        # Handle custom adapter
        adapter_file = None
        if illumina_clip["Arquivo adaptadores"] == "Personalizado":
            custom_content = illumina_clip.get("Conteudo personalizado")
            if not custom_content:
                logger.error("Custom adapter content is missing.")
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Custom adapter content is missing.")
            adapter_file = f"/app/backend/scripts/adapters/custom_adapter_{user_id}.fa"
            with open(adapter_file, "w") as f:
                f.write(custom_content)
            illumina_clip["Arquivo adaptadores"] = adapter_file  # Atualiza para usar o caminho do arquivo personalizado
            logger.info(f"Custom adapter file created at {adapter_file}")

        # Processar amostras PE
        for base_name in paired_samples:
            command = [
                "bash",
                "/app/backend/scripts/trimmagem.sh",
                f"{base_name}",
                str(threads),
                phred,
                json.dumps(illumina_clip),
                json.dumps(sliding_window),
                json.dumps(max_info),
                str(leading),
                str(trailing),
                crop if crop else "",
                headcrop if headcrop else "",
                str(minlen),
                avgqual if avgqual else "",
                base_path,
                trimmed_path,
            ]

            logger.info(f"Executing command for paired sample {base_name}: {' '.join(command)}")
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            stdout, stderr = process.communicate()

            logger.info(f"Command stdout: {stdout}")
            if stderr.strip():  # Log stderr only if it contains meaningful content
                logger.error(f"Command stderr: {stderr.strip()}")

            if process.returncode != 0:
                logger.error(f"Error in trimmagem for {base_name}: {stderr.strip()}")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error in trimmagem for {base_name}: {stderr.strip()}")

            # Obter o sample_id original
            db_sample_stage = db.query(SampleStage).filter(
                SampleStage.sra_code == base_name,
                SampleStage.stage_id == 1,
                SampleStage.user_id == user_id,
            ).first()
            if not db_sample_stage:
                logger.error(f"Sample {base_name} not found in stage 1.")
                continue

            # Criar registros no banco de dados para os resultados da trimmagem
            for suffix in ["_1", "_2"]:
                trimmed_name = f"{base_name}{suffix}_trimmed.fastq"
                trimmed_size = os.path.getsize(f"{trimmed_path}/{trimmed_name}")  # Obter o tamanho do arquivo
                db_sample_stage_trimmed = SampleStage(
                    sample_id=db_sample_stage.sample_id,  # Reutilizar o sample_id original
                    stage_id=3,  # ID do estágio de trimmagem
                    name=trimmed_name,
                    sra_code=base_name,
                    size=f"{trimmed_size / (1024 * 1024):.2f} MB",  # Converter para MB
                    status="Completed",
                    user_id=user_id,
                )
                db.add(db_sample_stage_trimmed)
            db.commit()

            logger.info(f"Trimmagem completed successfully for paired sample {base_name}.")

        # Processar amostras SE
        for sample in single_samples:
            command = [
                "bash",
                "/app/backend/scripts/trimmagem.sh",
                sample,
                str(threads),
                phred,
                json.dumps(illumina_clip),
                json.dumps(sliding_window),
                json.dumps(max_info),
                str(leading),
                str(trailing),
                crop if crop else "",
                headcrop if headcrop else "",
                str(minlen),
                avgqual if avgqual else "",
                base_path,
                trimmed_path,
            ]

            logger.info(f"Executing command for single sample {sample}: {' '.join(command)}")
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            stdout, stderr = process.communicate()

            logger.info(f"Command stdout: {stdout}")
            if stderr.strip():  # Log stderr only if it contains meaningful content
                logger.error(f"Command stderr: {stderr.strip()}")

            if process.returncode != 0:
                logger.error(f"Error in trimmagem for {sample}: {stderr.strip()}")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error in trimmagem for {sample}: {stderr.strip()}")

            # Obter o sample_id original
            db_sample_stage = db.query(SampleStage).filter(
                SampleStage.name == sample,
                SampleStage.stage_id == 1,
                SampleStage.user_id == user_id,
            ).first()
            if not db_sample_stage:
                logger.error(f"Sample {sample} not found in stage 1.")
                continue

            # Criar registro no banco de dados para o resultado da trimmagem
            trimmed_name = f"{sample}_trimmed.fastq"
            trimmed_size = os.path.getsize(f"{trimmed_path}/{trimmed_name}")  # Obter o tamanho do arquivo
            db_sample_stage_trimmed = SampleStage(
                sample_id=db_sample_stage.sample_id,  # Reutilizar o sample_id original
                stage_id=3,  # ID do estágio de trimmagem
                name=trimmed_name,
                sra_code=sample.split("_")[0],
                size=f"{trimmed_size / (1024 * 1024):.2f} MB",  # Converter para MB
                status="Completed",
                user_id=user_id,
            )
            db.add(db_sample_stage_trimmed)
        db.commit()

        logger.info(f"Trimmagem completed successfully for single sample {sample}.")

        # Limpar arquivo de adaptadores personalizados
        if adapter_file and os.path.exists(adapter_file):
            os.remove(adapter_file)
            logger.info(f"Custom adapter file {adapter_file} removed.")

        logger.info("Trimmagem process completed successfully.")
        response = {"message": "Trimmagem completed successfully"}
        logger.info(f"Returning response: {response}")
        return response
    except Exception as e:
        logger.error(f"Unexpected error in trimmagem route: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred.")

@router.post("/trimmagem/update_status")
async def update_trimmagem_status(sra_code: str = Form(...), status: str = Form(...), db: Session = Depends(get_db)):
    db_sample_stage = db.query(SampleStage).filter(SampleStage.sra_code == sra_code, SampleStage.stage_id == 3).first()
    if not db_sample_stage:
        raise HTTPException(status_code=404, detail="Sample not found")
    db_sample_stage.status = status
    db.commit()

    return {"message": f"Trimmagem status for {sra_code} updated to {status}"}

@router.delete("/trimmagem/{sample_name}")
async def delete_trimmed_sample(sample_name: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    user_id = current_user.id
    trimmed_path = f"../users/{user_id}/trimmed/{sample_name}"

    # Verificar e excluir arquivos _trimmed.fastq e _unpaired.fastq
    for suffix in ["_trimmed.fastq", "_unpaired.fastq"]:
        file_path = trimmed_path.replace("_trimmed.fastq", suffix)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"Arquivo {file_path} excluído com sucesso do sistema de arquivos.")
            except Exception as e:
                logger.error(f"Erro ao excluir arquivo {file_path} do sistema de arquivos: {e}")
                raise HTTPException(status_code=500, detail=f"Erro ao excluir arquivo {file_path} do sistema de arquivos.")
        else:
            logger.warning(f"Arquivo {file_path} não encontrado para exclusão.")

    # Remover a entrada correspondente no banco de dados
    db_sample_stage = db.query(SampleStage).filter(
        SampleStage.name == sample_name,
        SampleStage.stage_id == 3,
        SampleStage.user_id == user_id
    ).first()

    if not db_sample_stage:
        logger.warning(f"Amostra trimmada {sample_name} não encontrada no banco de dados para exclusão.")
        return {"message": f"Amostra trimmada {sample_name} já foi excluída ou não existe."}

    try:
        db.delete(db_sample_stage)
        db.commit()
        logger.info(f"Amostra trimmada {sample_name} excluída com sucesso do banco de dados.")
        return {"message": f"Amostra trimmada {sample_name} excluída com sucesso."}
    except Exception as e:
        logger.error(f"Erro ao excluir amostra trimmada {sample_name} do banco de dados: {e}")
        raise HTTPException(status_code=500, detail="Erro ao excluir amostra trimmada do banco de dados.")