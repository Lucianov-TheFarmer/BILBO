from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db.database import get_db
from ..db.models import User, SampleStage
from ..utils import get_current_user
from fastapi.responses import FileResponse, JSONResponse
import os
import logging
from ..utils import SECRET_KEY, ALGORITHM
from jose import JWTError, jwt
from fastapi import Request
from ..scripts import llm as llm_script
from ..utils import manager

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/llm/contrasts")
def list_llm_contrasts(user_id: int = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    uid = user_id or current_user.id
    # list SampleStage entries for stage_id=10
    stages = db.query(SampleStage).filter(SampleStage.user_id == int(uid), SampleStage.stage_id == 10).all()
    results = []
    for s in stages:
        out_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../users", str(uid), "llm", s.name))
        files = []
        if os.path.exists(out_dir):
            files = [f for f in os.listdir(out_dir) if f.lower().endswith(('.md', '.json'))]
        results.append({"sheet": s.name, "files": files})
    return {"contrasts": results}


@router.get("/llm/file")
def download_llm_file(file: str, sheet: str, user_id: int, token: str, db: Session = Depends(get_db)):
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

    file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../users", str(user_id), "llm", sheet, file))
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    # determine media type
    media_type = "text/markdown" if file.lower().endswith('.md') else "application/json"
    return FileResponse(path=file_path, filename=os.path.basename(file_path), media_type=media_type)


@router.delete("/llm/{sheet}")
def delete_llm_sheet(sheet: str, user_id: int, token: str, db: Session = Depends(get_db)):
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

    out_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../users", str(user_id), "llm", sheet))
    try:
        if os.path.exists(out_dir):
            for f in os.listdir(out_dir):
                try:
                    os.remove(os.path.join(out_dir, f))
                except Exception:
                    pass
            try:
                os.rmdir(out_dir)
            except Exception:
                pass
    except Exception as ex:
        logger.warning(f"Erro ao excluir LLM files: {ex}")

    try:
        ss = db.query(SampleStage).filter(SampleStage.user_id == int(user_id), SampleStage.stage_id == 10, SampleStage.name == sheet).first()
        if ss:
            db.delete(ss)
            db.commit()
    except Exception as ex:
        logger.warning(f"Erro ao remover SampleStage LLM: {ex}")

    return JSONResponse(content={"message": "LLM sheet deleted"})


@router.post("/llm/run")
async def run_llm_route(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    data = await request.json()
    user_id = data.get("user_id", current_user.id)
    sheets = data.get("sheets") or []
    if isinstance(sheets, str):
        sheets = [sheets]

    results = {}
    for sheet in sheets:
        out_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../users", str(user_id), "llm", sheet))
        os.makedirs(out_dir, exist_ok=True)
        try:
            res = llm_script.run_llm(file_path=None, sheet_name=sheet, out_dir=out_dir, user_id=user_id)
            results[sheet] = {"status": "done", "paths": res}
            try:
                existing = db.query(SampleStage).filter(SampleStage.user_id == int(user_id), SampleStage.stage_id == 10, SampleStage.name == sheet).first()
                if not existing:
                    ss = SampleStage(stage_id=10, name=sheet, sra_code=None, size="", status="Interpreted", user_id=int(user_id))
                    db.add(ss)
                    db.commit()
            except Exception as ex:
                logger.warning(f"Não foi possível criar SampleStage para LLM: {ex}")
        except Exception as e:
            logger.error(f"Erro ao executar LLM para sheet {sheet}: {e}")
            results[sheet] = {"status": "error", "error": str(e)}

    # Notify via websocket that LLM finished
    try:
        await manager.broadcast("LLM completed")
    except Exception:
        pass

    return JSONResponse(content={"results": results})
