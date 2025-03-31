from fastapi import APIRouter, Depends, HTTPException, status, Form
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Sample, User
from ..utils import get_current_user
import subprocess
import os
import json  # Import JSON for deserialization

router = APIRouter()

@router.post("/trimmagem/")
def start_trimmagem(
    sra_code: str = Form(...),
    threads: int = Form(1),
    phred: str = Form("autodetect"),
    illumina_clip: str = Form(...),  # Receive as string
    sliding_window: str = Form(...),  # Receive as string
    max_info: str = Form(...),  # Receive as string
    leading: int = Form(3),
    trailing: int = Form(3),
    crop: str = Form(None),  # Accept as string to handle empty values
    headcrop: str = Form(None),  # Accept as string to handle empty values
    minlen: int = Form(36),
    avgqual: str = Form(None),  # Accept as string to handle empty values
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = current_user.id
    db_sample = db.query(Sample).filter(Sample.sra_code == sra_code, Sample.user_id == user_id).first()
    if not db_sample:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Sample {sra_code} not found")

    # Deserialize JSON strings
    try:
        illumina_clip = json.loads(illumina_clip)
        sliding_window = json.loads(sliding_window)
        max_info = json.loads(max_info)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid JSON format: {e}")

    # Handle custom adapter
    adapter_file = None
    if illumina_clip["Arquivo adaptadores"] == "Personalizado":
        custom_content = illumina_clip.get("Conteudo personalizado")
        if not custom_content:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Custom adapter content is missing.")
        adapter_file = f"/app/backend/scripts/adapters/custom_adapter_{user_id}.fa"
        with open(adapter_file, "w") as f:
            f.write(custom_content)
        illumina_clip["Arquivo adaptadores"] = adapter_file

    # Convert optional fields to integers or None
    crop = int(crop) if crop and crop.strip() else None
    headcrop = int(headcrop) if headcrop and headcrop.strip() else None
    avgqual = int(avgqual) if avgqual and avgqual.strip() else None

    # Construct the command
    command = [
        "bash",
        "/app/backend/scripts/trimmagem.sh",
        sra_code,
        str(threads),
        phred,
        illumina_clip["Arquivo adaptadores"],  # Use the updated adapter file path
        str(sliding_window),
        str(max_info),
        str(leading),
        str(trailing),
    ]

    if crop is not None:
        command.append(str(crop))
    else:
        command.append("")

    if headcrop is not None:
        command.append(str(headcrop))
    else:
        command.append("")

    command.append(str(minlen))

    if avgqual is not None:
        command.append(str(avgqual))
    else:
        command.append("")

    # Execute the command
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    stdout, stderr = process.communicate()

    if process.returncode != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error in trimmagem: {stderr}")

    # Clean up custom adapter file
    # if adapter_file and os.path.exists(adapter_file):
        # os.remove(adapter_file)

    return {"message": "Trimmagem started successfully", "output": stdout}
