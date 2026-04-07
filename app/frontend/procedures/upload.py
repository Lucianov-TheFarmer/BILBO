import flet as ft
import httpx
import logging
import asyncio
import os
import tempfile
from .utils import log_message

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
        
async def show_upload_fastq_modal(page, token, container_menu_direita, tabela_amostras_local, atualizar_tabela, user_id):
    """
    Exibe um modal para upload de arquivos FASTQ usando webviewer
    """
    
    print("DEBUG: show_upload_fastq_modal foi chamada!")
    logger.info("Abrindo modal de upload FASTQ")
    
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
                if (/_1$/i.test(basename)) {
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
                        // Ler arquivo como ArrayBuffer para converter para base64
                        const arrayBuffer = await file.arrayBuffer();
                        const uint8Array = new Uint8Array(arrayBuffer);
                        
                        // Converter para base64
                        let binary = '';
                        for (let j = 0; j < uint8Array.length; j++) {
                            binary += String.fromCharCode(uint8Array[j]);
                        }
                        const base64Content = btoa(binary);
                        
                        // Enviar para backend
                        const response = await fetch('http://localhost:8000/upload/fastq', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json', 
                                'Authorization': 'Bearer """ + token + """'
                            },
                            body: JSON.stringify({
                                filename: file.name,
                                content: base64Content,
                                user_id: """ + str(user_id) + """
                            })
                        });
                        
                        if (!response.ok) {
                            throw new Error(`HTTP ${response.status}`);
                        }
                        
                        const result = await response.json();
                        
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
                const finalizeResponse = await fetch('http://localhost:8000/upload/finalize', {
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
    
    # Criar data URL com o HTML
    import base64
    html_encoded = base64.b64encode(html_content.encode('utf-8')).decode('utf-8')
    data_url = f"data:text/html;charset=utf-8;base64,{html_encoded}"
    
    # Criar WebView com data URL
    webview = ft.WebView(
        url=data_url,
        expand=True
    )
    async def fechar_modal(e):
        """Fecha o modal e atualiza a tabela"""
        dlg_modal_upload_fastq.open = False
        page.update()
        
        # Atualizar tabela de amostras após fechar o modal
        try:
            await atualizar_tabela(page, token, container_menu_direita, tabela_amostras_local)
        except Exception as e:
            logger.error(f"Erro ao atualizar tabela após upload: {e}")
            await log_message(page, f"⚠️ Erro ao atualizar tabela: {e}")
    
    # Criar o modal
    dlg_modal_upload_fastq = ft.AlertDialog(
        modal=True,
        title=ft.Text("Adicionar arquivos FASTQ"),
        content=ft.Container(
            width=700,
            height=600,
            content=webview
        ),
        actions=[
            ft.TextButton(
                "Fechar",
                on_click=fechar_modal
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    
    # Exibir o modal
    page.open(dlg_modal_upload_fastq)
