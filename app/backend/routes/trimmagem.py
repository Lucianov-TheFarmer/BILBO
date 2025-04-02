from fastapi import APIRouter, Depends, HTTPException, status, Form
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Sample, User
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
            logger.info(f"Command stderr: {stderr}")

            if process.returncode != 0:
                logger.error(f"Error in trimmagem for {base_name}: {stderr.strip()}")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error in trimmagem for {base_name}: {stderr.strip()}")

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
            logger.info(f"Command stderr: {stderr}")

            if process.returncode != 0:
                logger.error(f"Error in trimmagem for {sample}: {stderr.strip()}")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error in trimmagem for {sample}: {stderr.strip()}")

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
