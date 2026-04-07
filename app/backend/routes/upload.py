import base64
import logging
import os
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..core.settings import settings
from ..db.database import get_db
from ..db.models import SampleStage, User
from ..services.job_service import normalize_status
from ..utils import get_current_user, manager
from ..utils_paths import safe_resolve_user_path
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)

class FileUpload(BaseModel):
    filename: str
    content: str  # conteúdo do arquivo em base64

def calculate_file_size(file_path: str) -> str:
    """Calculate file size and return in appropriate units"""
    try:
        size_bytes = os.path.getsize(file_path)
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024**2:
            return f"{size_bytes/1024:.1f} KB"
        elif size_bytes < 1024**3:
            return f"{size_bytes/(1024**2):.1f} MB"
        else:
            return f"{size_bytes/(1024**3):.1f} GB"
    except Exception as e:
        logger.error(f"Erro ao calcular tamanho do arquivo {file_path}: {e}")
        return "Unknown"

def extract_basename_from_filename(filename: str) -> str:
    """Extract basename from FASTQ filename"""
    # Remove .fastq, .fq extensions
    name = filename.replace('.fastq.gz', '').replace('.fq.gz', '').replace('.fastq', '').replace('.fq', '')
    
    # Remove common paired-end suffixes
    suffixes = ['_1', '_2', '_R1', '_R2']
    for suffix in suffixes:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
            break
    
    return name

def detect_sequencing_type(filename: str) -> str:
    """Detect if file is from single-end or paired-end sequencing"""
    if any(suffix in filename for suffix in ['_1.', '_2.', '_R1.', '_R2.']):
        return "Paired-End"
    return "Single-End"

@router.post("/upload/fastq")
async def upload_fastq_file(data: FileUpload, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Endpoint para salvar arquivos FASTQ e adicionar ao banco de dados"""
    try:
        # Determinar basename e tipo de sequenciamento
        filename = data.filename
        basename = extract_basename_from_filename(filename)
        sequencing_type = detect_sequencing_type(filename)
        
        # Criar diretório
        user_dir = safe_resolve_user_path(settings.users_root, current_user.id, "samples", basename)
        user_dir.mkdir(parents=True, exist_ok=True)
        
        # Salvar arquivo
        file_path = user_dir / Path(filename).name
        
        # Decodificar conteúdo base64
        file_content = base64.b64decode(data.content)
        
        with open(file_path, 'wb') as f:
            f.write(file_content)
        
        # Calcular tamanho do arquivo
        file_size = calculate_file_size(file_path)
        
        # Verificar se já existe entrada no banco para este basename e usuário
        existing_sample = db.query(SampleStage).filter(
            SampleStage.sra_code == basename,
            SampleStage.stage_id == 1,
            SampleStage.user_id == current_user.id
        ).first()
        
        if not existing_sample:
            # Criar nova entrada no banco de dados para stage 1 (samples)
            new_sample = SampleStage(
                stage_id=1,
                name=filename,
                sra_code=basename,
                size=file_size,
                status="COMPLETED",
                user_id=current_user.id,
            )
            db.add(new_sample)
            db.commit()
            db.refresh(new_sample)
            
            logger.info(f"Nova amostra criada no banco: {basename} - {filename}")
        else:
            # Atualizar entrada existente se necessário
            existing_sample.status = normalize_status("completed")
            existing_sample.size = file_size
            db.commit()
            
            logger.info(f"Amostra existente atualizada: {basename} - {filename}")
        
        # Enviar mensagem para o terminal
        terminal_message = f"Upload da amostra {filename} concluído"
        await manager.broadcast(terminal_message, user_id=current_user.id)

        logger.info(
            "FASTQ upload saved: user_id=%s basename=%s filename=%s size=%s sequencing_type=%s",
            current_user.id,
            basename,
            filename,
            file_size,
            sequencing_type,
        )
        
        return {
            "status": "saved", 
            "path": str(file_path),
            "basename": basename,
            "size": file_size,
            "sequencing_type": sequencing_type,
            "database_updated": True
        }
        
    except Exception as e:
        failing_filename = getattr(data, "filename", "unknown")
        logger.exception("Erro ao salvar arquivo FASTQ: user_id=%s filename=%s", current_user.id, failing_filename)
        await manager.broadcast(f"❌ Erro no upload: {failing_filename} - {str(e)}", user_id=current_user.id)
        return {"status": "error", "message": str(e)}

@router.post("/upload/finalize")
async def finalize_upload_batch(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Finalizar lote de upload e enviar mensagem consolidada"""
    try:
        # Contar amostras do usuário
        total_samples = db.query(SampleStage).filter(
            SampleStage.user_id == current_user.id,
            SampleStage.stage_id == 1
        ).count()
        
        # Enviar mensagem de finalização
        final_message = f"Upload finalizado! Total de amostras: {total_samples}"
        await manager.broadcast(final_message, user_id=current_user.id)
        
        return {
            "status": "finalized",
            "total_samples": total_samples,
            "message": "Upload batch completed successfully"
        }
        
    except Exception as e:
        logger.error(f"Erro ao finalizar lote de upload: {e}")
        await manager.broadcast(f"❌ Erro ao finalizar upload: {str(e)}", user_id=current_user.id)
        return {"status": "error", "message": str(e)}
