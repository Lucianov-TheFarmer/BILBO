from fastapi import APIRouter, Depends, HTTPException, status, Form
from sqlalchemy.orm import Session
from ..db.database import get_db
from ..db.models import SampleStage, User  # Substitua 'Sample' por 'SampleStage'
from ..services.job_service import normalize_status
from ..utils import get_current_user, manager
import subprocess
import os
import json
import logging
import asyncio
import re

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

router = APIRouter()


_FASTQ_EXTENSION_RE = re.compile(
    r"\.(?:fastq|fq)(?:\.gz)?$",
    re.IGNORECASE,
)

_FASTQ_PAIR_RE = re.compile(
    r"^(?P<base>.+?)_R?(?P<mate>[12])"
    r"(?P<ext>\.(?:fastq|fq)(?:\.gz)?)$",
    re.IGNORECASE,
)


def _strip_fastq_extension(name: str) -> str:
    return _FASTQ_EXTENSION_RE.sub("", str(name))


def _parse_fastq_name(name: str):
    """Retorna basename, mate e extensão."""
    match = _FASTQ_PAIR_RE.match(str(name))
    if match:
        return (
            match.group("base"),
            int(match.group("mate")),
            match.group("ext"),
        )

    return _strip_fastq_extension(name), None, None


def _sample_sra_code(name: str) -> str:
    basename, _, _ = _parse_fastq_name(name)
    return basename


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

        # Agrupar FASTQ por basename e mate.
        grouped_samples = {}
        single_samples = []

        for sample in selected_samples:
            base_name, mate, _ = _parse_fastq_name(sample)

            if mate in (1, 2):
                grouped_samples.setdefault(base_name, {})[mate] = sample
            else:
                single_samples.append(sample)

        paired_samples = []

        for base_name, mates in grouped_samples.items():
            if 1 in mates and 2 in mates:
                paired_samples.append(base_name)
            else:
                # Uma leitura selecionada sem seu mate é tratada como single-end.
                single_samples.extend(mates.values())

        paired_samples = sorted(set(paired_samples))
        single_samples = list(dict.fromkeys(single_samples))

        logger.info(f"Paired samples: {paired_samples}")
        logger.info(f"Single samples: {single_samples}")

        # Create DB entries with status RUNNING for expected trimmed outputs
        try:
            for base_name in paired_samples:
                for suffix in ["_1", "_2"]:
                    trimmed_name = f"{base_name}{suffix}_trimmed.fastq.gz"
                    exists = db.query(SampleStage).filter(
                        SampleStage.name == trimmed_name,
                        SampleStage.stage_id == 3,
                        SampleStage.user_id == user_id
                    ).first()
                    if not exists:
                        db_sample_stage_trimmed = SampleStage(
                            stage_id=3,
                            name=trimmed_name,
                            sra_code=base_name,
                            size=None,
                            status="RUNNING",
                            user_id=user_id,
                        )
                        db.add(db_sample_stage_trimmed)

            for sample in single_samples:
                sample_base = _strip_fastq_extension(sample)
                trimmed_name = f"{sample_base}_trimmed.fastq.gz"
                exists = db.query(SampleStage).filter(
                    SampleStage.name == trimmed_name,
                    SampleStage.stage_id == 3,
                    SampleStage.user_id == user_id
                ).first()
                if not exists:
                    db_sample_stage_trimmed = SampleStage(
                        stage_id=3,
                            name=trimmed_name,
                            sra_code=_sample_sra_code(sample),
                            size=None,
                            status="RUNNING",
                            user_id=user_id,
                        )
                    db.add(db_sample_stage_trimmed)

            db.commit()
            try:
                asyncio.run(manager.broadcast(f"Trimmagem iniciada para: {paired_samples + single_samples}", user_id=user_id))
            except Exception as e:
                logger.warning(f"Não foi possível enviar broadcast de início de trimmagem: {e}")
        except Exception as e:
            logger.error(f"Erro ao criar entradas In Progress para trimmagem: {e}")

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

                for suffix in ("_1", "_2"):
                    failed_row = db.query(SampleStage).filter(
                        SampleStage.name == f"{base_name}{suffix}_trimmed.fastq.gz",
                        SampleStage.stage_id == 3,
                        SampleStage.user_id == user_id,
                    ).first()
                    if failed_row:
                        failed_row.status = "FAILED"

                db.commit()

                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=(
                        f"Error in trimmagem for {base_name}. "
                        f"Consulte /tmp/{base_name}_trimmagem.log"
                    ),
                )

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
                trimmed_name = f"{base_name}{suffix}_trimmed.fastq.gz"
                # Avoid duplicate entries: check if trimmed sample already exists
                exists = db.query(SampleStage).filter(
                    SampleStage.name == trimmed_name,
                    SampleStage.stage_id == 3,
                    SampleStage.user_id == user_id
                ).first()
                if exists:
                    # Update existing RUNNING entry to COMPLETED and set size
                    try:
                        trimmed_size = os.path.getsize(f"{trimmed_path}/{trimmed_name}")
                    except Exception:
                        trimmed_size = 0
                    exists.size = f"{trimmed_size / (1024 * 1024):.2f} MB"
                    exists.status = "COMPLETED"
                    db.add(exists)
                else:
                    try:
                        trimmed_size = os.path.getsize(f"{trimmed_path}/{trimmed_name}")  # Obter o tamanho do arquivo
                    except Exception:
                        trimmed_size = 0
                    db_sample_stage_trimmed = SampleStage(
                        stage_id=3,  # ID do estágio de trimmagem
                        name=trimmed_name,
                        sra_code=base_name,
                        size=f"{trimmed_size / (1024 * 1024):.2f} MB",  # Converter para MB
                        status="COMPLETED",
                        user_id=user_id,
                    )
                    db.add(db_sample_stage_trimmed)
            db.commit()

            logger.info(f"Trimmagem completed successfully for paired sample {base_name}.")

            # Enviar mensagem de conclusão via WebSocket
            try:
                asyncio.run(manager.broadcast(f"Trimmagem concluída para {base_name}", user_id=user_id))
            except Exception as e:
                logger.warning(f"Não foi possível enviar mensagem WebSocket: {e}")

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

                failed_name = f"{_strip_fastq_extension(sample)}_trimmed.fastq.gz"
                failed_row = db.query(SampleStage).filter(
                    SampleStage.name == failed_name,
                    SampleStage.stage_id == 3,
                    SampleStage.user_id == user_id,
                ).first()

                if failed_row:
                    failed_row.status = "FAILED"
                    db.commit()

                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=(
                        f"Error in trimmagem for {sample}. "
                        f"Consulte o log em /tmp."
                    ),
                )

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
            # sample may include the suffix like '_1.fastq' - normalize base name
            sample_base = _strip_fastq_extension(sample)
            trimmed_name = f"{sample_base}_trimmed.fastq.gz"
            # Update existing RUNNING entry to COMPLETED or insert new
            exists = db.query(SampleStage).filter(
                SampleStage.name == trimmed_name,
                SampleStage.stage_id == 3,
                SampleStage.user_id == user_id
            ).first()
            if exists:
                try:
                    trimmed_size = os.path.getsize(f"{trimmed_path}/{trimmed_name}")
                except Exception:
                    trimmed_size = 0
                exists.size = f"{trimmed_size / (1024 * 1024):.2f} MB"
                exists.status = "COMPLETED"
                db.add(exists)
            else:
                try:
                    trimmed_size = os.path.getsize(f"{trimmed_path}/{trimmed_name}")  # Obter o tamanho do arquivo
                except Exception:
                    trimmed_size = 0
                db_sample_stage_trimmed = SampleStage(
                    stage_id=3,  # ID do estágio de trimmagem
                    name=trimmed_name,
                    sra_code=sample_base.split("_")[0],
                    size=f"{trimmed_size / (1024 * 1024):.2f} MB",  # Converter para MB
                    status="COMPLETED",
                    user_id=user_id,
                )
                db.add(db_sample_stage_trimmed)
        db.commit()

        logger.info(f"Trimmagem completed successfully for single sample {sample}.")

        # Enviar mensagem de conclusão via WebSocket
        # try:
        #     asyncio.run(manager.broadcast(f"Trimmagem concluída para {sample}"))
        # except Exception as e:
        #     logger.warning(f"Não foi possível enviar mensagem WebSocket: {e}")

        # Limpar arquivo de adaptadores personalizados
        if adapter_file and os.path.exists(adapter_file):
            os.remove(adapter_file)
            logger.info(f"Custom adapter file {adapter_file} removed.")

        logger.info("Trimmagem process completed successfully.")
        response = {"message": "Trimmagem completed successfully"}
        logger.info(f"Returning response: {response}")
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error in trimmagem route: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {e}",
        )

@router.post("/trimmagem/update_status")
async def update_trimmagem_status(
    sra_code: str = Form(...),
    status: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db_sample_stage = db.query(SampleStage).filter(
        SampleStage.sra_code == sra_code,
        SampleStage.stage_id == 3,
        SampleStage.user_id == current_user.id,
    ).first()
    if not db_sample_stage:
        raise HTTPException(status_code=404, detail="Sample not found")
    normalized = normalize_status(status)
    db_sample_stage.status = normalized
    db.commit()
    # Broadcast update to frontend so UI can refresh
    try:
        await manager.broadcast(f"Trimmagem {sra_code} status: {normalized}", user_id=current_user.id)
    except Exception as e:
        logger.warning(f"Failed to broadcast trimmagem status: {e}")

    return {"message": f"Trimmagem status for {sra_code} updated to {normalized}"}

@router.delete("/trimmagem/{sample_name}")
async def delete_trimmed_sample(
    sample_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = current_user.id

    if os.path.basename(sample_name) != sample_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid sample name",
        )

    trimmed_root = os.path.abspath(
        f"../users/{user_id}/trimmed"
    )

    file_path = os.path.abspath(
        os.path.join(trimmed_root, sample_name)
    )

    if os.path.commonpath([trimmed_root, file_path]) != trimmed_root:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid sample path",
        )

    if os.path.isfile(file_path):
        os.remove(file_path)
        logger.info(
            "Arquivo trimmado removido: %s",
            file_path,
        )

    # Limpeza apenas de resíduos produzidos por versões antigas.
    for suffix in (
        "_trimmed.fastq.gz",
        "_trimmed.fastq",
    ):
        if sample_name.endswith(suffix):
            stem = sample_name[:-len(suffix)]

            for old_suffix in (
                "_unpaired.fastq",
                "_unpaired.fastq.gz",
            ):
                legacy = os.path.join(
                    trimmed_root,
                    stem + old_suffix,
                )

                if os.path.isfile(legacy):
                    os.remove(legacy)

            break

    db_sample_stage = db.query(SampleStage).filter(
        SampleStage.name == sample_name,
        SampleStage.stage_id == 3,
        SampleStage.user_id == user_id,
    ).first()

    if db_sample_stage:
        db.delete(db_sample_stage)
        db.commit()

    return {
        "message": (
            f"Amostra trimmada {sample_name} "
            "excluída com sucesso."
        )
    }
