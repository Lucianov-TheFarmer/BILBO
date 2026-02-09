from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from ..db.database import get_db
from ..db.models import User
from ..utils import get_current_user, manager
import os
import openpyxl
from fastapi.responses import JSONResponse
from ..scripts import clustering as clustering_script
import logging
from ..db.models import SampleStage
from fastapi.responses import FileResponse
from ..utils import SECRET_KEY, ALGORITHM
from jose import JWTError, jwt

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/clustering/contrasts")
async def list_contrasts(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    user_id = request.query_params.get("user_id", current_user.id)
    deg_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../users", str(user_id), "DEG"))
    deg_xlsx = os.path.join(deg_dir, "DEG.xlsx")
    if not os.path.exists(deg_xlsx):
        raise HTTPException(status_code=404, detail="Arquivo DEG.xlsx não encontrado.")

    try:
        wb = openpyxl.load_workbook(deg_xlsx, read_only=True)
        sheet_names = wb.sheetnames
        wb.close()
    except Exception as e:
        logger.error(f"Erro ao ler abas do DEG.xlsx: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao ler abas do DEG.xlsx: {e}")

    results = []
    for sheet in sheet_names:
        cluster_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../users", str(user_id), "clustering", sheet))
        clustered = False
        files = []
        if os.path.exists(cluster_dir):
            files = [f for f in os.listdir(cluster_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
            clustered = len(files) > 0
        results.append({"sheet": sheet, "clustered": clustered, "files": files})

    return {"contrasts": results}

@router.post("/clustering/run")
async def run_clustering(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    data = await request.json()
    user_id = data.get("user_id", current_user.id)
    sheets = data.get("sheets") or []
    if isinstance(sheets, str):
        sheets = [sheets]

    deg_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../users", str(user_id), "DEG"))
    deg_xlsx = os.path.join(deg_dir, "DEG.xlsx")
    if not os.path.exists(deg_xlsx):
        raise HTTPException(status_code=404, detail="Arquivo DEG.xlsx não encontrado.")

    results = {}
    for sheet in sheets:
        out_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../users", str(user_id), "clustering", sheet))
        os.makedirs(out_dir, exist_ok=True)
        img_final = os.path.join(out_dir, "cluster.png")
        img_metrics = os.path.join(out_dir, "metrics.png")
        cluster_json = os.path.join(out_dir, "clusters.json")
        try:
            res = clustering_script.cluster_pipeline(deg_xlsx, sheet_name=sheet, img_final_path=img_final, img_metrics_path=img_metrics, clusters_json_path=cluster_json)
            # res contains keys img_final and img_metrics (paths passed)
            results[sheet] = {"status": "done", "img_final": os.path.relpath(img_final, start=os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))), "img_metrics": os.path.relpath(img_metrics, start=os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))), "clusters_json": os.path.relpath(cluster_json, start=os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))}
            # Record clustering result in DB as a SampleStage (stage_id=9)
            try:
                existing = db.query(SampleStage).filter(SampleStage.user_id == int(user_id), SampleStage.stage_id == 9, SampleStage.name == sheet).first()
                if not existing:
                    ss = SampleStage(stage_id=9, name=sheet, sra_code=None, size="", status="Clustered", user_id=int(user_id))
                    db.add(ss)
                    db.commit()
            except Exception as ex:
                logger.warning(f"Não foi possível criar SampleStage para clustering: {ex}")
        except Exception as e:
            logger.error(f"Erro ao executar cluster para sheet {sheet}: {e}")
            results[sheet] = {"status": "error", "error": str(e)}

    # Notify via websocket that clustering finished (simple message)
    await manager.broadcast("Clustering completed")
    return JSONResponse(content={"results": results})


@router.get("/clustering/file")
def download_clustering_file(file: str, sheet: str, user_id: int, token: str, db: Session = Depends(get_db)):
    """Serve a clustering image file after validating token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(User).filter(User.username == username).first()
    if user is None or user.id != int(user_id):
        raise HTTPException(status_code=401, detail="User mismatch or not found")

    file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../users", str(user_id), "clustering", sheet, file))
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(path=file_path, filename=os.path.basename(file_path), media_type="image/png")


@router.delete("/clustering/{sheet}")
def delete_clustering_sheet(sheet: str, user_id: int, token: str, db: Session = Depends(get_db)):
    """Delete clustering files and the corresponding SampleStage entry."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(User).filter(User.username == username).first()
    if user is None or user.id != int(user_id):
        raise HTTPException(status_code=401, detail="User mismatch or not found")

    out_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../users", str(user_id), "clustering", sheet))
    # remove files and directory
    try:
        if os.path.exists(out_dir):
            for f in os.listdir(out_dir):
                fp = os.path.join(out_dir, f)
                try:
                    os.remove(fp)
                except Exception:
                    pass
            try:
                os.rmdir(out_dir)
            except Exception:
                pass
    except Exception as ex:
        logger.warning(f"Erro ao excluir arquivos de clustering: {ex}")

    # remove DB entry
    try:
        ss = db.query(SampleStage).filter(SampleStage.user_id == int(user_id), SampleStage.stage_id == 9, SampleStage.name == sheet).first()
        if ss:
            db.delete(ss)
            db.commit()
    except Exception as ex:
        logger.warning(f"Erro ao remover SampleStage de clustering: {ex}")

    return JSONResponse(content={"message": "Clustering deleted"})
