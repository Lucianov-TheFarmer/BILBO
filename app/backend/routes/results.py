from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import JSONResponse, FileResponse
from sqlalchemy.orm import Session
from ..db.database import get_db
from ..db.models import User
from ..utils import get_current_user, SECRET_KEY, ALGORITHM
import os
import openpyxl
import subprocess
import tempfile
import logging
from jose import jwt, JWTError
import pandas as pd
from fastapi import Query
from fastapi.responses import StreamingResponse

router = APIRouter()

@router.get("/results/deg_sheets")
async def get_deg_sheets(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = request.query_params.get("user_id", current_user.id)
    deg_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../users", str(user_id), "DEG"))
    deg_xlsx = os.path.join(deg_dir, "DEG.xlsx")
    if not os.path.exists(deg_xlsx):
        raise HTTPException(status_code=404, detail="Arquivo DEG.xlsx não encontrado.")
    try:
        wb = openpyxl.load_workbook(deg_xlsx, read_only=True)
        sheet_names = wb.sheetnames
        wb.close()
        return {"sheets": sheet_names}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao ler abas do DEG.xlsx: {e}")

@router.get("/results/barplot_files")
async def get_barplot_files(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = request.query_params.get("user_id", current_user.id)
    deg_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../users", str(user_id), "DEG"))
    if not os.path.exists(deg_dir):
        return {"files": []}
    files = [f for f in os.listdir(deg_dir) if f.startswith("BARPLOT.MULTIPLO - ") and f.endswith(".png")]
    return {"files": files}

@router.post("/results/create_barplot_file")
async def create_barplot_file(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = await request.json()
    user_id = data.get("user_id", current_user.id)
    title = data.get("title", "").strip()
    contrasts = data.get("contrasts", [])
    if not title:
        raise HTTPException(status_code=400, detail="Título obrigatório.")
    if not contrasts:
        raise HTTPException(status_code=400, detail="Selecione pelo menos um contraste.")
    
    deg_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../users", str(user_id), "DEG"))
    deg_xlsx_path = os.path.join(deg_dir, "DEG.xlsx")
    
    if not os.path.exists(deg_xlsx_path):
        raise HTTPException(status_code=404, detail="Arquivo DEG.xlsx não encontrado.")
    
    os.makedirs(deg_dir, exist_ok=True)
    
    # Script R para barplot múltiplo
    barplot_script = os.path.abspath(os.path.join(os.path.dirname(__file__), "../scripts/barplot_multiplo.R"))
    
    if not os.path.exists(barplot_script):
        raise HTTPException(status_code=500, detail="Script barplot_multiplo.R não encontrado.")
    
    try:
        logger = logging.getLogger(__name__)
        
        # Log dos parâmetros recebidos
        logger.info(f"Gerando barplot múltiplo: user_id={user_id}, title='{title}', contrasts={contrasts}")
        logger.info(f"DEG.xlsx path: {deg_xlsx_path}")
        logger.info(f"Script R path: {barplot_script}")
        
        # Prepara argumentos para o script R
        cmd_args = ["Rscript", barplot_script, deg_xlsx_path, deg_dir, title] + contrasts
        logger.info(f"Comando R: {' '.join(cmd_args)}")
        
        process = subprocess.Popen(
            cmd_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=deg_dir  # Define diretório de trabalho
        )
        stdout, stderr = process.communicate()
        
        logger.info(f"R script stdout: {stdout}")
        if stderr:
            logger.warning(f"R script stderr: {stderr}")
        
        if process.returncode != 0:
            logger.error(f"R script failed with return code {process.returncode}")
            raise HTTPException(status_code=500, detail=f"Erro ao executar script R: {stderr}")
        
        filename = f"BARPLOT.MULTIPLO - {title}.png"
        output_file = os.path.join(deg_dir, filename)
        
        # Verifica se o arquivo foi gerado
        if not os.path.exists(output_file):
            logger.error(f"Arquivo de saída não foi gerado: {output_file}")
            raise HTTPException(status_code=500, detail="Arquivo de imagem não foi gerado pelo script R")
        
        logger.info(f"Barplot múltiplo gerado com sucesso: {filename}")
        return {"status": "ok", "file": filename, "message": "Barplot múltiplo gerado com sucesso"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao gerar barplot múltiplo: {e}")

@router.delete("/results/delete_barplot_file")
async def delete_barplot_file(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Accept query params for compatibility with frontend delete calls
    user_id = request.query_params.get("user_id", current_user.id)
    filename = request.query_params.get("filename", "").strip()
    if not filename:
        raise HTTPException(status_code=400, detail="Nome do arquivo obrigatório.")
    deg_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../users", str(user_id), "DEG"))
    file_path = os.path.join(deg_dir, filename)
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            return {"status": "ok", "message": "Arquivo deletado com sucesso"}
        else:
            raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao deletar arquivo: {e}")

@router.get("/results/venn_files")
async def get_venn_files(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = request.query_params.get("user_id", current_user.id)
    deg_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../users", str(user_id), "DEG"))
    if not os.path.exists(deg_dir):
        return {"files": []}
    # List generated Venn diagram PNGs
    files = [f for f in os.listdir(deg_dir) if f.startswith("VENN.DIAGRAM - ") and f.endswith(".png")]
    return {"files": files}

@router.get("/results/heatmap_files")
async def get_heatmap_files(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = request.query_params.get("user_id", current_user.id)
    deg_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../users", str(user_id), "DEG"))
    if not os.path.exists(deg_dir):
        return {"files": []}
    # List generated heatmap PNGs
    files = [f for f in os.listdir(deg_dir) if f.startswith("HEATMAP - ") and f.endswith(".png")]
    return {"files": files}


@router.get("/results/download_deg_sheets")
def download_deg_sheets(sheets: str = Query(None), token: str = Query(...), db: Session = Depends(get_db)):
    """Download an XLSX containing only the requested sheets (comma-separated list)."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")

    user_id = user.id
    deg_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../users", str(user_id), "DEG"))
    deg_xlsx_path = os.path.join(deg_dir, "DEG.xlsx")
    if not os.path.exists(deg_xlsx_path):
        raise HTTPException(status_code=404, detail="Arquivo DEG.xlsx não encontrado.")

    requested = [] if not sheets else [s.strip() for s in sheets.split(",") if s.strip()]

    # If no sheets requested, return the full file
    if not requested:
        return FileResponse(path=deg_xlsx_path, filename=os.path.basename(deg_xlsx_path), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    try:
        # Read requested sheets into pandas and write to a new temporary Excel file
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            tmp_path = tmp.name

        with pd.ExcelWriter(tmp_path, engine="openpyxl") as writer:
            for sheet in requested:
                try:
                    df = pd.read_excel(deg_xlsx_path, sheet_name=sheet)
                    df.to_excel(writer, sheet_name=sheet, index=False)
                except Exception:
                    # Skip missing sheets
                    pass

        return FileResponse(path=tmp_path, filename=f"DEG_selected_sheets_{user_id}.xlsx", media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao gerar arquivo XLSX: {e}")

@router.get("/results/download_image")
def download_deg_image(user_id: int = Query(...), filename: str = Query(...), token: str = Query(...)):
    """Serve an image file from the user's DEG directory."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    deg_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../users", str(user_id), "DEG"))
    file_path = os.path.join(deg_dir, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(path=file_path, filename=os.path.basename(file_path), media_type="application/octet-stream")



@router.post("/results/create_venn_file")
async def create_venn_file(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = await request.json()
    user_id = data.get("user_id", current_user.id)
    title = data.get("title", "").strip()
    contrasts = data.get("contrasts", [])
    if not title:
        raise HTTPException(status_code=400, detail="Título obrigatório.")
    if not contrasts:
        raise HTTPException(status_code=400, detail="Pelo menos um contraste deve ser selecionado.")
    if len(contrasts) < 2 or len(contrasts) > 4:
        raise HTTPException(status_code=400, detail="Diagrama de Venn requer 2-4 contrastes.")
        
    deg_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../users", str(user_id), "DEG"))
    os.makedirs(deg_dir, exist_ok=True)
    
    # Caminhos dos arquivos
    deg_xlsx = os.path.join(deg_dir, "DEG.xlsx")
    png_filename = f"VENN.DIAGRAM - {title}.png"
    png_path = os.path.join(deg_dir, png_filename)
    
    # Verifica se DEG.xlsx existe
    if not os.path.exists(deg_xlsx):
        raise HTTPException(status_code=404, detail="Arquivo DEG.xlsx não encontrado. Execute a análise DEG primeiro.")
    
    try:
        # Cria arquivo temporário com contrastes
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as temp_file:
            for contrast in contrasts:
                temp_file.write(contrast + "\n")
            temp_contrasts_path = temp_file.name
        
        # Executa script de geração do diagrama de Venn
        script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../scripts/venn_diagram.py"))
        
        if not os.path.exists(script_path):
            raise HTTPException(status_code=500, detail="Script venn_diagram.py não encontrado.")
        
        result = subprocess.run(
            ["python", script_path, temp_contrasts_path, deg_xlsx, png_path, title],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        # Remove arquivo temporário
        os.unlink(temp_contrasts_path)
        
        if result.returncode != 0:
            logging.error(f"Erro ao executar venn_diagram.py: {result.stderr}")
            raise HTTPException(status_code=500, detail=f"Erro ao gerar diagrama de Venn: {result.stderr}")
        
        logging.info(f"Diagrama de Venn gerado: {png_filename}")
        return {"status": "ok", "file": png_filename}
        
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="Timeout na geração do diagrama de Venn.")
    except Exception as e:
        logging.error(f"Erro ao criar diagrama de Venn: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao criar diagrama de Venn: {e}")

@router.delete("/results/delete_barplot_file")
async def delete_barplot_file(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = request.query_params.get("user_id", current_user.id)
    filename = request.query_params.get("filename", "").strip()
    
    if not filename:
        raise HTTPException(status_code=400, detail="Nome do arquivo obrigatório.")
    
    # Verifica se é um arquivo de barplot múltiplo válido
    if not filename.startswith("BARPLOT.MULTIPLO - ") or not filename.endswith(".png"):
        raise HTTPException(status_code=400, detail="Arquivo inválido.")
    
    deg_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../users", str(user_id), "DEG"))
    file_path = os.path.join(deg_dir, filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
    
    try:
        os.remove(file_path)
        logging.info(f"Barplot excluído: {filename}")
        return {"status": "ok", "message": "Arquivo excluído com sucesso"}
    except Exception as e:
        logging.error(f"Erro ao excluir barplot: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao excluir arquivo: {e}")

@router.delete("/results/delete_venn_file")
async def delete_venn_file(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = request.query_params.get("user_id", current_user.id)
    filename = request.query_params.get("filename", "").strip()
    
    if not filename:
        raise HTTPException(status_code=400, detail="Nome do arquivo obrigatório.")
    
    # Verifica se é um arquivo de diagrama de Venn válido
    if not filename.startswith("VENN.DIAGRAM - ") or not filename.endswith(".png"):
        raise HTTPException(status_code=400, detail="Arquivo inválido.")
    
    deg_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../users", str(user_id), "DEG"))
    file_path = os.path.join(deg_dir, filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
    
    try:
        os.remove(file_path)
        logging.info(f"Diagrama de Venn excluído: {filename}")
        return {"status": "ok", "message": "Arquivo excluído com sucesso"}
    except Exception as e:
        logging.error(f"Erro ao excluir diagrama de Venn: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao excluir arquivo: {e}")

@router.get("/results/heatmap_files")
async def get_heatmap_files(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = request.query_params.get("user_id", current_user.id)
    deg_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../users", str(user_id), "DEG"))
    if not os.path.exists(deg_dir):
        return {"files": []}
    files = [f for f in os.listdir(deg_dir) if f.startswith("HEATMAP - ") and f.endswith(".png")]
    return {"files": files}

@router.post("/results/create_heatmap_file")
async def create_heatmap_file(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        data = await request.json()
        user_id = data.get("user_id", current_user.id)
        title = data.get("title", "").strip()
        selected_contrasts = data.get("selected_contrasts", [])
        
        if not title:
            raise HTTPException(status_code=400, detail="Título é obrigatório.")
        
        if not selected_contrasts:
            raise HTTPException(status_code=400, detail="Pelo menos um contraste deve ser selecionado.")
        
        # Caminhos
        deg_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../users", str(user_id), "DEG"))
        deg_xlsx = os.path.join(deg_dir, "DEG_full.xlsx")
        
        if not os.path.exists(deg_xlsx):
            raise HTTPException(status_code=404, detail="Arquivo DEG.xlsx não encontrado.")

        # Validação rápida: verifique se cada contraste existe e possui a coluna 'logFC'
        # try:
        #     wb = openpyxl.load_workbook(deg_xlsx, read_only=True, data_only=True)
        #     missing_sheets = []
        #     missing_format = []
        #     sheet_headers = {}
        #     for cname in selected_contrasts:
        #         if cname not in wb.sheetnames:
        #             missing_sheets.append(cname)
        #             continue
        #         ws = wb[cname]
        #         # obtém primeira linha (cabeçalho)
        #         header_row = None
        #         for row in ws.iter_rows(max_row=1, values_only=True):
        #             header_row = row
        #             break
        #         if header_row is None:
        #             missing_format.append((cname, []))
        #             continue
        #         headers = [h if h is not None else "" for h in header_row]
        #         sheet_headers[cname] = headers
        #         # valida formato por posição: precisa ter pelo menos 2 colunas (gene, logFC)
        #         if len(headers) < 2:
        #             missing_format.append((cname, headers))
        #     wb.close()

        #     if missing_sheets:
        #         raise HTTPException(status_code=400, detail=f"Abas não encontradas no DEG_full.xlsx: {missing_sheets}")
        #     if missing_format:
        #         details = []
        #         for c, hdrs in missing_format:
        #             details.append({"contrast": c, "found_columns": hdrs, "message": "esperado pelo menos 2 colunas (gene, logFC)"})
        #         raise HTTPException(status_code=400, detail={"invalid_format": details})
        # except HTTPException:
        #     raise
        # except Exception as e:
        #     logging.error(f"Erro ao validar DEG_full.xlsx antes de gerar heatmap: {e}")
        #     raise HTTPException(status_code=500, detail=f"Erro ao validar arquivo DEG_full.xlsx: {e}")
        
        # Nome do arquivo de saída
        png_filename = f"HEATMAP - {title}.png"
        png_path = os.path.join(deg_dir, png_filename)
        
        # Cria arquivo temporário com os contrastes selecionados
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as temp_file:
            for contrast in selected_contrasts:
                temp_file.write(contrast + '\n')
            temp_contrasts_path = temp_file.name
        
        # Run the heatmap script in a background thread so the request returns immediately
        script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../scripts/heatmap.R"))
        if not os.path.exists(script_path):
            try:
                os.unlink(temp_contrasts_path)
            except Exception:
                pass
            raise HTTPException(status_code=500, detail="Script heatmap.R não encontrado.")

        def _worker():
            # Clear, explicit terminal logs for start and finish
            start_msg = f"[HEATMAP] Iniciando geração: user_id={user_id} title='{title}' contrasts={selected_contrasts}"
            print(start_msg)
            logging.info(start_msg)
            try:
                result = subprocess.run([
                    "Rscript", script_path, temp_contrasts_path, deg_xlsx, png_path, title
                ], capture_output=True, text=True)
                if result.returncode != 0:
                    err_msg = f"[HEATMAP] Erro ao executar heatmap.R (rc={result.returncode}): {result.stderr}"
                    print(err_msg)
                    logging.error(err_msg)
                else:
                    ok_msg = f"[HEATMAP] Heatmap criado com sucesso: {png_path}"
                    print(ok_msg)
                    logging.info(ok_msg)
                    # include stdout for diagnostics
                    if result.stdout:
                        print(f"[HEATMAP] Script output:\n{result.stdout}")
                        logging.info(f"Heatmap script stdout: {result.stdout}")
            except Exception as e:
                exc_msg = f"[HEATMAP] Exceção ao gerar heatmap: {e}"
                print(exc_msg)
                logging.error(exc_msg, exc_info=True)
            finally:
                try:
                    os.unlink(temp_contrasts_path)
                except Exception:
                    pass

        import threading
        threading.Thread(target=_worker, daemon=True).start()

        return {"status": "started", "filename": png_filename, "message": "Geração de heatmap iniciada"}
                
    except Exception as e:
        logging.error(f"Erro ao criar heatmap: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {e}")

@router.delete("/results/delete_heatmap_file")
async def delete_heatmap_file(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = request.query_params.get("user_id", current_user.id)
    filename = request.query_params.get("filename", "").strip()
    
    if not filename:
        raise HTTPException(status_code=400, detail="Nome do arquivo obrigatório.")
    
    # Caminho da pasta DEG do usuário
    deg_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../users", str(user_id), "DEG"))

    logging.info(f"Solicitação de exclusão de heatmap - user_id={user_id} filename={filename} deg_dir={deg_dir}")

    if not os.path.exists(deg_dir):
        logging.error(f"Diretório DEG não encontrado: {deg_dir}")
        raise HTTPException(status_code=404, detail="Diretório DEG do usuário não encontrado.")

    # Aceita nomes com ou sem prefixo 'HEATMAP - '
    candidate_paths = []
    if filename.startswith("HEATMAP - ") and filename.endswith(".png"):
        candidate_paths.append(os.path.join(deg_dir, filename))
    else:
        # tenta localizar um arquivo que contenha o nome passado (sem path)
        for f in os.listdir(deg_dir):
            if f.endswith('.png') and filename in f:
                candidate_paths.append(os.path.join(deg_dir, f))

    if not candidate_paths:
        logging.error(f"Arquivo de heatmap não encontrado para: {filename}")
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")

    # Tenta remover o primeiro candidato válido
    file_path = candidate_paths[0]
    logging.info(f"Removendo arquivo: {file_path}")
    try:
        os.remove(file_path)
        logging.info(f"Heatmap excluído: {file_path}")
        return {"status": "ok", "message": "Arquivo excluído com sucesso"}
    except Exception as e:
        logging.error(f"Erro ao excluir heatmap: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao excluir arquivo: {e}")
