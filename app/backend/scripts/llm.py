import os
import json
import glob
import shutil
import subprocess
import tempfile
import time
import urllib.request
import chromadb
from chromadb import EmbeddingFunction, Documents, Embeddings
import ollama

# Vector DB bootstrap configuration
ZENODO_CHROMA_DB_URL = os.getenv(
    "BILBO_RAG_DB_URL",
    "https://zenodo.org/records/19440155/files/chroma_db_BILBO_Plants.rar?download=1",
)
VECTOR_DB_ARCHIVE_NAME = "chroma_db_BILBO_Plants.rar"
VECTOR_DB_DIRNAME = "chroma_db_BILBO_Plants"


def _resolve_users_root():
    configured = os.getenv("USERS_ROOT")
    if configured:
        return os.path.abspath(configured)
    if os.path.isdir("/users"):
        return "/users"
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "users"))


USERS_ROOT = _resolve_users_root()
RAG_MODELS_ROOT = os.path.join(USERS_ROOT, "rag_models")
CHROMA_DB_PATH = os.path.join(RAG_MODELS_ROOT, VECTOR_DB_DIRNAME)
VECTOR_DB_LOCK_PATH = CHROMA_DB_PATH + ".bootstrap.lock"
COLLECTION_NAME = "banco_literatura_bio"

# models (kept from rag.py)
MODELO_LLM = os.getenv("BILBO_LLM_MODEL_OVERRIDE") or os.getenv("LLM_PRIMARY_MODEL", "qwen3:14b")
MODELO_EMBEDDING = "snowflake-arctic-embed2:568m"


def _vector_db_ready(path):
    if not os.path.isdir(path):
        return False
    try:
        return any(True for _ in os.scandir(path))
    except OSError:
        return False


def _download_file(url, destination):
    print(f"[llm.py] ChromaDB ausente. Baixando do Zenodo: {url}")
    with urllib.request.urlopen(url, timeout=120) as response, open(destination, "wb") as output:
        total = int(response.headers.get("Content-Length", "0") or 0)
        downloaded = 0
        last_progress = -1
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            output.write(chunk)
            downloaded += len(chunk)
            if total > 0:
                progress = int((downloaded / total) * 100)
                if progress // 10 != last_progress // 10:
                    print(f"[llm.py] Download ChromaDB: {progress}%")
                last_progress = progress
    print(f"[llm.py] Download concluido: {destination}")


def _extract_rar_archive(archive_path, extract_root):
    commands = [
        ["7z", "x", "-y", f"-o{extract_root}", archive_path],
        ["unrar-free", "x", archive_path, extract_root],
        ["unrar", "x", "-o+", "-y", archive_path, extract_root],
        ["bsdtar", "-xf", archive_path, "-C", extract_root],
    ]
    failures = []
    for command in commands:
        try:
            result = subprocess.run(command, capture_output=True, text=True)
        except FileNotFoundError:
            failures.append(f"{command[0]}: comando nao encontrado")
            continue

        if result.returncode == 0:
            print(f"[llm.py] Arquivo RAR extraido com: {command[0]}")
            return command[0]

        output = (result.stderr or result.stdout or "").strip()
        failures.append(f"{command[0]} retornou {result.returncode}: {output[-500:]}")

    raise RuntimeError(
        "Falha ao extrair chroma_db_BILBO_Plants.rar. "
        "Instale uma ferramenta de extracoes RAR (7z/unrar/bsdtar). "
        f"Detalhes: {' | '.join(failures)}"
    )


def _find_extracted_vector_db(extract_root):
    direct_candidate = os.path.join(extract_root, VECTOR_DB_DIRNAME)
    if os.path.isdir(direct_candidate):
        return direct_candidate

    for root, dirs, _ in os.walk(extract_root):
        if VECTOR_DB_DIRNAME in dirs:
            return os.path.join(root, VECTOR_DB_DIRNAME)
    return None


def _acquire_lock(lock_path):
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as lock_file:
            lock_file.write(str(os.getpid()))
        return True
    except FileExistsError:
        return False


def _release_lock(lock_path):
    try:
        os.unlink(lock_path)
    except FileNotFoundError:
        pass


def _wait_for_external_bootstrap(timeout_seconds=3600, poll_seconds=2):
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if _vector_db_ready(CHROMA_DB_PATH):
            return True
        if not os.path.exists(VECTOR_DB_LOCK_PATH):
            return _vector_db_ready(CHROMA_DB_PATH)
        time.sleep(poll_seconds)
    return False


def ensure_vector_db_available():
    if _vector_db_ready(CHROMA_DB_PATH):
        return {
            "downloaded": False,
            "path": CHROMA_DB_PATH,
            "source": "local",
            "source_url": ZENODO_CHROMA_DB_URL,
        }

    os.makedirs(RAG_MODELS_ROOT, exist_ok=True)
    lock_acquired = _acquire_lock(VECTOR_DB_LOCK_PATH)

    if not lock_acquired:
        print("[llm.py] Aguardando inicializacao do ChromaDB por outro processo...")
        if _wait_for_external_bootstrap():
            return {
                "downloaded": False,
                "path": CHROMA_DB_PATH,
                "source": "local_after_wait",
                "source_url": ZENODO_CHROMA_DB_URL,
            }
        raise RuntimeError("Timeout ao aguardar inicializacao do banco vetorial ChromaDB")

    temp_dir = tempfile.mkdtemp(prefix="bilbo_chromadb_")
    archive_path = os.path.join(temp_dir, VECTOR_DB_ARCHIVE_NAME)
    try:
        if _vector_db_ready(CHROMA_DB_PATH):
            return {
                "downloaded": False,
                "path": CHROMA_DB_PATH,
                "source": "local",
                "source_url": ZENODO_CHROMA_DB_URL,
            }

        _download_file(ZENODO_CHROMA_DB_URL, archive_path)
        extractor = _extract_rar_archive(archive_path, temp_dir)
        extracted_path = _find_extracted_vector_db(temp_dir)
        if not extracted_path:
            raise FileNotFoundError(
                f"Pasta {VECTOR_DB_DIRNAME} nao encontrada apos extracao do arquivo {archive_path}"
            )

        if os.path.isdir(CHROMA_DB_PATH):
            shutil.rmtree(CHROMA_DB_PATH, ignore_errors=True)
        shutil.move(extracted_path, CHROMA_DB_PATH)

        if not _vector_db_ready(CHROMA_DB_PATH):
            raise RuntimeError("Bootstrap do ChromaDB concluido, mas o diretorio final esta vazio")

        print(f"[llm.py] ChromaDB preparado em: {CHROMA_DB_PATH}")
        return {
            "downloaded": True,
            "path": CHROMA_DB_PATH,
            "source": "zenodo",
            "source_url": ZENODO_CHROMA_DB_URL,
            "extractor": extractor,
        }
    finally:
        _release_lock(VECTOR_DB_LOCK_PATH)
        shutil.rmtree(temp_dir, ignore_errors=True)


class FuncaoEmbedding(EmbeddingFunction):
    def __call__(self, entrada: Documents) -> Embeddings:
        vetores = []
        for texto in entrada:
            texto_limpo = texto.replace("\n", " ")
            resposta = ollama.embeddings(model=MODELO_EMBEDDING, prompt=texto_limpo)
            vetores.append(resposta["embedding"])
        return vetores


def inicializar_banco_vetorial():
    bootstrap_info = ensure_vector_db_available()
    if bootstrap_info.get("downloaded"):
        print("[llm.py] Banco vetorial baixado automaticamente no primeiro uso.")
    print(f"[llm.py] Conectando ao ChromaDB em: {CHROMA_DB_PATH}")
    cliente = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    funcao_embedding = FuncaoEmbedding()
    colecao = cliente.get_or_create_collection(name=COLLECTION_NAME, embedding_function=funcao_embedding)
    return colecao, bootstrap_info


def analisar_descricao_cluster(colecao, lista_genes):
    genes_str = ", ".join(lista_genes[:50])
    print(f"[llm.py] [Cluster] Identifying theme ({len(lista_genes)} genes)...")

    consulta = f"biological pathway and function shared by genes: {genes_str}"
    resultados = colecao.query(query_texts=[consulta], n_results=5)

    contexto = ""
    if resultados and resultados.get('documents') and resultados['documents'][0]:
        contexto = "\n".join(resultados['documents'][0])

    prompt_cluster = f"""
    You are a bioinformatics expert.
    Analyze this group of genes: {genes_str} (and others in the same cluster).

    Context from literature:
    {contexto}

    Task:
    Write a SHORT descriptive paragraph (max 4 sentences) defining the identity of this cluster.
    What biological function unites them?
    Start with: "This cluster is characterized by..."
    """

    try:
        resposta = ollama.chat(
            model=MODELO_LLM,
            messages=[{'role': 'user', 'content': prompt_cluster}]
        )
        return resposta['message']['content']
    except Exception as e:
        print(f"[llm.py] Erro no cluster: {e}")
        return "Descrição indisponível."


def analisar_coesao_cluster(colecao, lista_genes, descricao_tema):
    print(f"[llm.py] [Validation] Verifying outliers and cohesion...")

    genes_str = ", ".join(lista_genes[:99])
    if len(lista_genes) > 99:
        genes_str += "..."

    consulta = f"functional differences and distinct pathways among genes: {genes_str}"
    resultados = colecao.query(query_texts=[consulta], n_results=3)

    contexto = ""
    if resultados and resultados.get('documents') and resultados['documents'][0]:
        contexto = "\n".join(resultados['documents'][0])

    prompt_validacao = f"""
    You are a strict molecular biologist reviewer.
    You have a cluster of genes that was described as: "{descricao_tema}".

    List of genes in this cluster: {genes_str}

    Literature Context:
    {contexto}

    Task:
    Critique this cluster. Does it make biological sense? Are there genes that shouldn't be here?

    Return a JSON object with exactly these keys:
    - "cohesion_status": "High", "Medium", or "Low".
    - "justification": A short text explaining why the cluster is good or bad.
    - "core_genes": A list of strings with the top 3-5 genes that BEST represent the theme.
    - "outliers": A list of objects, where each object has {{"gene": "GeneName", "reason": "Why it does not fit"}}. If none, return empty list.
    """

    try:
        resposta = ollama.chat(
            model=MODELO_LLM,
            messages=[{'role': 'user', 'content': prompt_validacao}],
            format='json'
        )
        dados = json.loads(resposta['message']['content'])
        return dados
    except Exception as e:
        print(f"[llm.py] [!] Erro na validação: {e}")
        return {
            "cohesion_status": "Error",
            "justification": "Could not validate due to LLM error.",
            "core_genes": [],
            "outliers": []
        }


def analisar_representante(colecao, gene_rep, descricao_do_cluster):
    print(f"[llm.py] -> Analisando Representante: {gene_rep}...")

    consulta = f"functional role of {gene_rep} in context of {descricao_do_cluster}"
    resultados = colecao.query(query_texts=[consulta], n_results=3)

    contexto_str = ""
    fontes = []
    if resultados and resultados.get('documents') and resultados['documents'][0]:
        contexto_str = "\n\n".join(resultados['documents'][0])
        if resultados.get('metadatas') and resultados['metadatas'][0]:
            fontes = sorted(list(set(m.get('fonte') for m in resultados['metadatas'][0] if m.get('fonte'))))

    prompt_gene = f"""
    You are an expert biologist. Analyze the representative gene '{gene_rep}'.

    CONTEXT - CLUSTER GROUP:
    "{descricao_do_cluster}"

    CONTEXT - LITERATURE:
    {contexto_str}

    Task:
    Return a JSON object with exactly these keys:
    - "gene_name": "{gene_rep}"
    - "biological_function": Description of the gene's function.
    - "molecular_mechanism": Mechanism of action.
    - "cluster_relevance": Why this gene is a good representative for the cluster described above.
    """

    try:
        resposta = ollama.chat(
            model=MODELO_LLM,
            messages=[{'role': 'user', 'content': prompt_gene}],
            format='json'
        )
        dados = json.loads(resposta['message']['content'])
        dados['sources'] = fontes
        return dados
    except Exception as e:
        print(f"[llm.py] [!] Erro gene {gene_rep}: {e}")
        return None


def salvar_resultados(dados, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    json_path = os.path.join(out_dir, "data.json")
    md_path = os.path.join(out_dir, "report.md")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=4, ensure_ascii=False)

    md_lines = ["# Relatório de Clusters Gênicos com Validação de IA\n"]

    for item in dados:
        rep_data = item['representative_analysis']
        val_data = item['validation_analysis']

        md_lines.append(f"## {item['cluster_id']} (Genes: {item['total_genes_in_cluster']})")

        md_lines.append(f"**Group Description:**\n> {item['cluster_description']}\n")

        md_lines.append(f"### Cluster Quality Control (AI Validation)")
        status_icon = "🟢" if val_data.get('cohesion_status') == "High" else "🟡" if val_data.get('cohesion_status') == "Medium" else "🔴"

        md_lines.append(f"**Cohesion Status:** {status_icon} {val_data.get('cohesion_status')}")
        md_lines.append(f"**Analysis:** {val_data.get('justification')}")

        core_genes = ", ".join(val_data.get('core_genes', []))
        md_lines.append(f"**Core Genes (Drivers):** {core_genes}")

        outliers = val_data.get('outliers', [])

        if outliers:
            md_lines.append(f"**Detected Outliers:**")
            for out in outliers:
                md_lines.append(f"* **{out.get('gene')}**: {out.get('reason')}")
        else:
            md_lines.append(f"*No significant outliers detected.*")

        md_lines.append("\n")

        md_lines.append(f"### Mathematical Representative: {rep_data.get('gene_name')}")
        md_lines.append(f"**Function:** {rep_data.get('biological_function')}\n")
        md_lines.append(f"**Mechanism:** {rep_data.get('molecular_mechanism')}\n")
        md_lines.append(f"**Relevance:** {rep_data.get('cluster_relevance')}\n")

        fontes = ", ".join(rep_data.get('sources', []))
        md_lines.append(f"**Sources: _{fontes}_**")
        md_lines.append("---\n")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    print(f"[llm.py] Relatórios salvos: {json_path}, {md_path}")
    return {"report": md_path, "json": json_path}


def executar_pipeline_completo(colecao, dados_clusters, out_dir):
    print("[llm.py] Iniciando Análise...")

    relatorio_final = []

    for nome_cluster, dados in dados_clusters.items():
        print(f"[llm.py] --- Processando {nome_cluster} ---")

        rep_gene = dados.get('representative')
        todos_genes = dados.get('genes', [])

        descricao_cluster = analisar_descricao_cluster(colecao, todos_genes)
        print(f"[llm.py] [Theme]: {descricao_cluster}...")

        dados_validacao = analisar_coesao_cluster(colecao, todos_genes, descricao_cluster)
        dados_rep = None
        if rep_gene:
            dados_rep = analisar_representante(colecao, rep_gene, descricao_cluster)

        if dados_rep:
            item_relatorio = {
                "cluster_id": nome_cluster,
                "cluster_description": descricao_cluster,
                "validation_analysis": dados_validacao,
                "representative_analysis": dados_rep,
                "total_genes_in_cluster": len(todos_genes),
                "genes_list": todos_genes
            }
            relatorio_final.append(item_relatorio)

    return relatorio_final


def run_llm(file_path, sheet_name=None, out_dir=None, user_id=None):
    """Main entry called by the route. Expects `sheet_name` to be the contrast name.

    Will look for clusters JSON at: ../users/{user_id}/clustering/{sheet_name}/clusters.json
    Uses fixed CHROMA_DB_PATH for the vector DB and writes outputs to `out_dir`.
    """
    if out_dir is None:
        if user_id is None:
            raise ValueError("user_id must be provided when out_dir is not specified")
        out_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "users", str(user_id), "llm", sheet_name or "default"))
    os.makedirs(out_dir, exist_ok=True)

    # locate clusters file
    clusters_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".." , "users", str(user_id), "clustering", sheet_name, "clusters.json"))
    if not os.path.exists(clusters_path):
        raise FileNotFoundError(f"clusters.json not found for contrast {sheet_name} at {clusters_path}")

    with open(clusters_path, "r", encoding="utf-8") as f:
        clusters_dict = json.load(f)

    # load articles (if any) and connect to vector DB
    colecao, bootstrap_info = inicializar_banco_vetorial()

    # execute pipeline and save results to out_dir
    relatorio = executar_pipeline_completo(colecao, clusters_dict, out_dir)
    saved = salvar_resultados(relatorio, out_dir)
    saved["vector_db_bootstrap"] = bootstrap_info
    return saved


if __name__ == "__main__":
    # Module intended to be used via import by the backend routes.
    # No CLI behavior is provided in production.
    print("llm.py loaded — call run_llm(file_path=None, sheet_name=..., out_dir=..., user_id=...) from your application.")
