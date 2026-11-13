"""Reference genome import dialogs for local files and public HTTPS URLs."""

import asyncio
import base64
import json

import flet as ft
import httpx

from .jobs import wait_with_progress
from .translations import t
from .utils import log_message


async def show_reference_url_modal(page, token):
    lang = page.session.get("lang") or "pt"
    name = ft.TextField(label=t("reference_name", lang), width=550)
    fasta = ft.TextField(label=t("reference_fasta_url", lang), width=550)
    annotation = ft.TextField(label=t("reference_annotation_url", lang), width=550)
    threads = ft.TextField(label=t("reference_threads", lang), value="8", width=120)
    overhang = ft.TextField(label="sjdbOverhang", value="100", width=140)
    status = ft.Text("")
    progress = ft.ProgressBar(value=0, width=500, visible=False)
    recent = ft.Column(height=100, scroll=ft.ScrollMode.AUTO)

    async def load_recent():
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.get("http://bioinfo-container:8890/genomes/import/jobs",
                                            headers={"Authorization": f"Bearer {token}"})
            response.raise_for_status()
            jobs = response.json()
            recent.controls = [ft.Text(t("reference_recent", lang))]
            recent.controls.extend(ft.Text(f"{job['label']}: {job['status']}" +
                                           (f" — {job['error_message']}" if job.get("error_message") else ""),
                                           size=11, selectable=True) for job in jobs)
            recent.height = 100 if jobs else 0
            page.update()
        except Exception:
            recent.height = 0

    async def submit(e):
        try:
            submit_button.disabled = True
            page.update()
            payload = {"label": name.value, "fasta_url": fasta.value,
                       "annotation_url": annotation.value, "threads": int(threads.value),
                       "sjdb_overhang": int(overhang.value)}
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post("http://bioinfo-container:8890/genomes/import/url",
                                             json=payload, headers={"Authorization": f"Bearer {token}"})
            if response.status_code != 202:
                status.value = str(response.json().get("detail", response.text))
                submit_button.disabled = False
                page.update()
                return
            job_id = response.json()["job_id"]
            status.value = t("reference_queued", lang)
            progress.visible = True
            page.update()
            def update(payload):
                data = payload.get("result") or {}
                percent = data.get("progress_percent")
                progress.value = percent / 100 if isinstance(percent, (int, float)) else None
                phase = data.get("phase") or ""
                phase_key = {"download_fasta": "reference_downloading_fasta",
                             "download_annotation": "reference_downloading_annotation",
                             "validating": "reference_validating", "indexing": "reference_indexing"}.get(phase)
                status.value = t(phase_key, lang) if phase_key else str(payload.get("status") or "")
                page.update()

            result = await wait_with_progress(page, token, job_id, t("reference_import", lang), on_update=update)
            status.value = (t("reference_ready", lang) if result["status"] == "COMPLETED"
                            else str(result.get("error_message") or t("reference_failed", lang)))
            progress.value = 1 if result["status"] == "COMPLETED" else 0
            status.color = "red" if result["status"] != "COMPLETED" else "green"
            page.update()
            await load_recent()
        except Exception as exc:
            status.value = str(exc)
            status.color = "red"
            submit_button.disabled = False
            page.update()

    submit_button = ft.TextButton(t("reference_import", lang), on_click=submit)
    dialog = ft.AlertDialog(
        title=ft.Text(t("reference_url_title", lang)),
        content=ft.Container(width=580, height=460, content=ft.Column(scroll=ft.ScrollMode.AUTO, controls=[
            ft.Text(t("reference_help", lang), size=12), name, fasta, annotation,
            ft.Row(controls=[threads, overhang]), progress, status, recent])),
        actions=[ft.TextButton(t("btn_cancel", lang), on_click=lambda e: page.close(dialog)),
                 submit_button])
    page.open(dialog)
    page.run_task(load_recent)


async def show_reference_upload_modal(page, token):
    lang = page.session.get("lang") or "pt"
    copy = {
        "pt": ["Enviar genoma de referência", "Nome do genoma", "FASTA genômico", "Anotação GFF3 ou GTF", "Enviar e indexar", "Enviando", "Validando e criando índice", "Concluído", "Erro"],
        "en": ["Upload reference genome", "Reference name", "Genomic FASTA", "GFF3 or GTF annotation", "Upload and index", "Uploading", "Validating and indexing", "Complete", "Error"],
        "es": ["Subir genoma de referencia", "Nombre del genoma", "FASTA genómico", "Anotación GFF3 o GTF", "Subir e indexar", "Subiendo", "Validando e indexando", "Completado", "Error"],
    }[lang if lang in ("pt", "en", "es") else "pt"]
    html = """<!doctype html><html><meta charset='utf-8'><body style='font:15px sans-serif'>
<h3 id='title'></h3><form id='form'><p><label id='lname'></label><br><input name='label' required maxlength='100'></p>
<p><label id='lfasta'></label><br><input type='file' name='fasta' required accept='.fa,.fasta,.fna,.fa.gz,.fasta.gz,.fna.gz,.fa.zip,.fasta.zip,.fna.zip'></p>
<p><label id='lannotation'></label><br><input type='file' name='annotation' required accept='.gff,.gff3,.gtf,.gff.gz,.gff3.gz,.gtf.gz,.gff.zip,.gff3.zip,.gtf.zip'></p>
<input name='threads' type='hidden' value='8'><input name='sjdb_overhang' type='hidden' value='100'>
<button id='send'></button></form><progress id='bar' value='0' max='100' style='width:95%'></progress><p id='status'></p>
<script>const c=COPY, token=TOKEN; ['title','lname','lfasta','lannotation','send'].forEach((id,i)=>document.getElementById(id).textContent=c[i]);
document.getElementById('form').onsubmit=e=>{e.preventDefault(); const xhr=new XMLHttpRequest();
xhr.open('POST','http://localhost:8890/genomes/import/upload');xhr.setRequestHeader('Authorization','Bearer '+token);
xhr.upload.onprogress=e=>{if(e.lengthComputable){document.getElementById('bar').value=Math.round(e.loaded*100/e.total);document.getElementById('status').textContent=c[5]+' '+document.getElementById('bar').value+'%';}};
xhr.onload=()=>{if(xhr.status!==202){document.getElementById('status').textContent=c[8]+': '+xhr.responseText;return;}
const job=JSON.parse(xhr.responseText).job_id;document.getElementById('status').textContent=c[6];const timer=setInterval(async()=>{
try{const r=await fetch('http://localhost:8890/genomes/import/jobs/'+job,{headers:{Authorization:'Bearer '+token}});
const p=await r.json();if(p.status==='COMPLETED'||p.status==='FAILED'){clearInterval(timer);document.getElementById('status').textContent=p.status==='COMPLETED'?c[7]:c[8]+': '+p.error_message;}
else {document.getElementById('status').textContent=c[6];}}
catch(err){document.getElementById('status').textContent=err.message;}},2000);};xhr.onerror=()=>{document.getElementById('status').textContent=c[8];};
xhr.send(new FormData(e.target));};</script></body></html>""".replace("COPY", json.dumps(copy)).replace("TOKEN", json.dumps(token))
    url = "data:text/html;charset=utf-8;base64," + base64.b64encode(html.encode()).decode()
    dialog = ft.AlertDialog(title=ft.Text(copy[0]),
                            content=ft.Container(width=600, height=340, content=ft.WebView(url=url)),
                            actions=[ft.TextButton(t("btn_cancel", lang), on_click=lambda e: page.close(dialog))])
    page.open(dialog)
