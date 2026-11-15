from .translations import t
import flet as ft
import httpx
import logging
import asyncio
import os
import tempfile
from .utils import log_message
from .urls import public_base_url

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

UPLOAD_COPY = {
    "en": {
        "Selecione arquivos FASTQ": "Select FASTQ files",
        "Clique aqui ou arraste arquivos": "Click here or drag files",
        "Formatos:": "Formats:",
        "Enviar Arquivos": "Upload files",
        "Análise dos arquivos:": "File preview:",
        "Nenhum arquivo analisado!": "No files selected!",
        "Iniciando upload...": "Starting upload...",
        "Processando grupo:": "Processing group:",
        "Grupo ${basename} concluído": "Group ${basename} complete",
        "Finalizando upload...": "Finishing upload...",
        "Aviso: Erro ao finalizar lote": "Warning: batch finalization failed",
        "Aviso:": "Warning:",
        "Upload completo!": "Upload complete!",
        "Adicionar arquivos FASTQ": "Add FASTQ files",
        "Enviando": "Uploading",
    },
    "es": {
        "Selecione arquivos FASTQ": "Seleccione archivos FASTQ",
        "Clique aqui ou arraste arquivos": "Haga clic o arrastre archivos",
        "Formatos:": "Formatos:",
        "Enviar Arquivos": "Cargar archivos",
        "Análise dos arquivos:": "Vista previa de archivos:",
        "Nenhum arquivo analisado!": "¡No se seleccionaron archivos!",
        "Iniciando upload...": "Iniciando carga...",
        "Processando grupo:": "Procesando grupo:",
        "Grupo ${basename} concluído": "Grupo ${basename} terminado",
        "Finalizando upload...": "Finalizando carga...",
        "Aviso: Erro ao finalizar lote": "Aviso: error al finalizar el lote",
        "Aviso:": "Aviso:",
        "Upload completo!": "¡Carga terminada!",
        "Adicionar arquivos FASTQ": "Añadir archivos FASTQ",
        "Enviando": "Subiendo",
    },
}

# UPLOAD_PERSISTENT_GLOBAL_START
_upload_panels = {}
# UPLOAD_PERSISTENT_GLOBAL_END

        
async def show_upload_fastq_modal(page, token, container_menu_direita, tabela_amostras_local, atualizar_tabela, user_id):
    """
    Exibe um modal para upload de arquivos FASTQ usando webviewer
    """
    
    print("DEBUG: show_upload_fastq_modal foi chamada!")
    logger.info("Abrindo modal de upload FASTQ")

    # UPLOAD_PERSISTENT_REOPEN_START
    cache_key = f"{id(page)}:{user_id}"
    cached_panel = _upload_panels.get(cache_key)
    if cached_panel is not None:
        cached_panel.offset = ft.Offset(0, 0)
        page.update()
        return
    # UPLOAD_PERSISTENT_REOPEN_END

    
    # HTML melhorado com estética e detecção SE/PE
    html_content = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Upload FASTQ</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
            background: transparent;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .container {
            background: white;
            border-radius: 15px;
            padding: 30px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            max-width: 600px;
            width: 100%;
        }
        .upload-area {
            border: 2px dashed #667eea;
            border-radius: 10px;
            padding: 30px;
            text-align: center;
            margin: 20px 0;
            transition: all 0.3s ease;
            cursor: pointer;
        }
        .upload-area:hover {
            border-color: #764ba2;
            background: #f8f9ff;
        }
        .upload-icon {
            font-size: 48px;
            color: #667eea;
            margin-bottom: 10px;
        }
        button {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 25px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 600;
            transition: transform 0.2s ease;
            margin: 10px auto;
            display: block;
        }
        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
        }
        #output {
            background: #f8f9fa;
            border-radius: 10px;
            padding: 15px;
            margin-top: 20px;
            white-space: pre-wrap;
            font-family: 'Consolas', monospace;
            font-size: 12px;
            max-height: 300px;
            overflow-y: auto;
        }
        .file-info {
            background: #e3f2fd;
            border-left: 4px solid #2196f3;
            padding: 10px;
            margin: 10px 0;
            border-radius: 5px;
        }
        .sample-group {
            background: #f0f8f0;
            border: 1px solid #4caf50;
            border-radius: 8px;
            padding: 10px;
            margin: 8px 0;
        }
        .sample-header {
            font-weight: bold;
            color: #2e7d32;
            margin-bottom: 5px;
        }
        .file-item {
            font-size: 11px;
            color: #555;
            margin-left: 10px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="upload-area" onclick="document.getElementById('files').click()">
            <div class="upload-icon">📁</div>
            <h3 style="margin: 10px 0; color: #333;">Selecione arquivos FASTQ</h3>
            <p style="color: #666; margin: 5px 0;">Clique aqui ou arraste arquivos</p>
            <p style="color: #999; font-size: 12px;">Formatos: .fastq, .fq, .fastq.gz, .fq.gz</p>
        </div>
        
        <input type="file" id="files" multiple accept=".fastq,.fq,.fastq.gz,.fq.gz" style="display: none;">
        
        <div id="fileAnalysis" style="display: none;"></div>
        
        <button onclick="processAndSend()" id="uploadBtn" style="display: none;">Enviar Arquivos</button>
        
        <progress id="uploadProgress" max="100" value="0" style="width:100%;display:none"></progress>
        <div id="uploadProgressText"></div>
        <div id="output"></div>
    </div>
    
    <script>
        let analysisData = [];
        
        document.getElementById('files').addEventListener('change', function(e) {
            if (e.target.files.length > 0) {
                analyzeFiles(Array.from(e.target.files));
            }
        });
        
        function analyzeFiles(files) {
            const analysis = document.getElementById('fileAnalysis');
            const uploadBtn = document.getElementById('uploadBtn');
            
            // Agrupar arquivos por basename
            const groups = {};
            
            files.forEach(file => {
                let basename = file.name.replace(/\\.(fastq|fq)(\\.gz)?$/i, '');
                let originalBasename = basename;
                
                // Detectar paired-end
                if (/_R[12]_001$/i.test(basename)) {
                    basename = basename.replace(/_R[12]_001$/i, '');
                } else if (/_1$/i.test(basename)) {
                    basename = basename.replace(/_1$/i, '');
                } else if (/_2$/i.test(basename)) {
                    basename = basename.replace(/_2$/i, '');
                } else if (/_R1$/i.test(basename)) {
                    basename = basename.replace(/_R1$/i, '');
                } else if (/_R2$/i.test(basename)) {
                    basename = basename.replace(/_R2$/i, '');
                }
                
                if (!groups[basename]) {
                    groups[basename] = { files: [], type: 'SE', totalSize: 0 };
                }
                
                groups[basename].files.push({
                    file: file,
                    originalName: file.name,
                    size: file.size,
                    isPaired: originalBasename !== basename
                });
                groups[basename].totalSize += file.size;
            });
            
            // Determinar tipo de sequenciamento para cada grupo
            Object.keys(groups).forEach(basename => {
                const group = groups[basename];
                const pairedFiles = group.files.filter(f => f.isPaired);
                
                if (pairedFiles.length >= 2) {
                    group.type = 'PE';
                } else if (pairedFiles.length === 1) {
                    group.type = 'SE (incomplete PE)';
                } else {
                    group.type = 'SE';
                }
            });
            
            // Exibir análise
            let html = '<h4 style="margin: 15px 0 10px 0; color: #333;">Análise dos arquivos:</h4>';
            
            Object.keys(groups).forEach(basename => {
                const group = groups[basename];
                const sizeStr = formatFileSize(group.totalSize);
                
                html += `<div class="sample-group">
                    <div class="sample-header">${basename} - ${group.type} (${sizeStr})</div>`;
                
                group.files.forEach(f => {
                    html += `<div class="file-item">📄 ${f.originalName} (${formatFileSize(f.size)})</div>`;
                });
                
                html += '</div>';
            });
            
            analysis.innerHTML = html;
            analysis.style.display = 'block';
            uploadBtn.style.display = 'block';
            
            analysisData = groups;
        }
        
        function formatFileSize(bytes) {
            if (bytes === 0) return '0 B';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
        }
        
        async function processAndSend() {
            const output = document.getElementById('output');
            
            if (Object.keys(analysisData).length === 0) {
                output.textContent = '❌ Nenhum arquivo analisado!';
                return;
            }
            
            output.textContent = 'Iniciando upload...\\n\\n';
            
            let totalFiles = 0;
            let processedFiles = 0;
            
            // Contar total de arquivos
            Object.values(analysisData).forEach(group => {
                totalFiles += group.files.length;
            });
            
            // Processar cada grupo
            for (const [basename, group] of Object.entries(analysisData)) {
                output.textContent += `📁 Processando grupo: ${basename} (${group.type})\\n`;
                
                // Processar cada arquivo do grupo
                for (const fileInfo of group.files) {
                    const file = fileInfo.file;
                    processedFiles++;
                    
                    output.textContent += `   📄 [${processedFiles}/${totalFiles}] ${file.name}...`;
                    
                    try {
                        const formData = new FormData();
                        formData.append("file", file, file.name);

                        const progressBar = document.getElementById('uploadProgress');
                        const progressText = document.getElementById('uploadProgressText');
                        progressBar.style.display = 'block';
                        const result = await new Promise((resolve, reject) => {
                            const xhr = new XMLHttpRequest();
                            xhr.open('POST', 'http://localhost:8890/upload/fastq');
                            xhr.setRequestHeader('Authorization', 'Bearer """ + token + """');
                            xhr.upload.onprogress = event => {
                                if (event.lengthComputable) {
                                    progressBar.value = Math.round(100 * event.loaded / event.total);
                                    progressText.textContent = `Enviando ${file.name}: ${formatFileSize(event.loaded)}/${formatFileSize(event.total)}`;
                                }
                            };
                            xhr.onload = () => {
                                if (xhr.status < 200 || xhr.status >= 300) reject(new Error(`HTTP ${xhr.status}: ${xhr.responseText}`));
                                else { try { resolve(JSON.parse(xhr.responseText)); } catch (err) { reject(err); } }
                            };
                            xhr.onerror = () => reject(new Error('Upload failed'));
                            xhr.send(formData);
                        });
                        progressText.textContent = `${file.name}: ${formatFileSize(file.size)}/${formatFileSize(file.size)}`;
                        
                        if (result.status === 'saved') {
                            output.textContent += ` ✅\\n`;
                        } else {
                            output.textContent += ` ❌ ${result.message}\\n`;
                        }
                        
                    } catch(e) { 
                        output.textContent += ` ❌ ${e.message}\\n`;
                    }
                }
                
                output.textContent += `   ✅ Grupo ${basename} concluído\\n\\n`;
            }
            
            // Finalizar lote de upload
            output.textContent += 'Finalizando upload...\\n';
            
            try {
                const finalizeResponse = await fetch('http://localhost:8890/upload/finalize', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': 'Bearer """ + token + """'
                    }
                });
                
                if (finalizeResponse.ok) {
                    const finalizeResult = await finalizeResponse.json();
                    output.textContent += `✅ ${finalizeResult.message} (Total: ${finalizeResult.total_samples} amostras)\\n`;
                } else {
                    const errorText = await finalizeResponse.text();
                    output.textContent += `⚠️ Aviso: Erro ao finalizar lote (${finalizeResponse.status}): ${errorText}\\n`;
                }
            } catch(e) {
                output.textContent += `⚠️ Aviso: ${e.message}\\n`;
            }
            
            output.textContent += '\\nUpload completo!';
        }
    </script>
</body>
</html>"""
    html_content = html_content.replace("http://localhost:8890", public_base_url())
    for source, translated in sorted(UPLOAD_COPY.get(page.session.get("lang") or "pt", {}).items(), key=lambda item: -len(item[0])):
        html_content = html_content.replace(source, translated)
    
    # Criar data URL com o HTML
    import base64
    html_encoded = base64.b64encode(html_content.encode("utf-8")).decode("utf-8")
    data_url = f"data:text/html;charset=utf-8;base64,{html_encoded}"

    # O WebView permanece montado mesmo quando o painel é ocultado
    webview = ft.WebView(
        url=data_url,
        expand=True,
    )

    async def ocultar_upload(e):
        # Desloca o painel para fora da tela sem destruir o WebView
        upload_panel.offset = ft.Offset(2, 0)
        page.update()

        try:
            await atualizar_tabela(
                page,
                token,
                container_menu_direita,
                tabela_amostras_local,
            )
        except Exception as exc:
            logger.error(f"Erro ao atualizar tabela após ocultar upload: {exc}")

    upload_card = ft.Container(
        width=760,
        height=700,
        padding=20,
        border_radius=18,
        bgcolor="white",
        shadow=ft.BoxShadow(
            blur_radius=25,
            spread_radius=2,
            color="black38",
        ),
        content=ft.Column(
            expand=True,
            controls=[
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        ft.Text(
                            {"pt": "Adicionar arquivos FASTQ", "en": "Add FASTQ files", "es": "Añadir archivos FASTQ"}.get(page.session.get("lang") or "pt", "Adicionar arquivos FASTQ"),
                            size=22,
                            weight="bold",
                        ),
                        ft.IconButton(
                            icon="close",
                            tooltip=t("hide", page.session.get("lang") or "pt"),
                            on_click=ocultar_upload,
                        ),
                    ],
                ),
                ft.Container(
                    content=webview,
                    expand=True,
                ),
                ft.Row(
                    alignment=ft.MainAxisAlignment.END,
                    controls=[
                        ft.TextButton(
                            t("hide", page.session.get("lang") or "pt"),
                            on_click=ocultar_upload,
                        ),
                    ],
                ),
            ],
        ),
    )

    upload_panel = ft.Container(
        key=f"persistent-upload-{user_id}",
        expand=True,
        alignment=ft.alignment.center,
        bgcolor="#99000000",
        offset=ft.Offset(0, 0),
        content=upload_card,
    )

    _upload_panels[cache_key] = upload_panel
    page.overlay.append(upload_panel)
    page.update()
