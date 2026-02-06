import os
import glob
import json
import chromadb
from chromadb import EmbeddingFunction, Documents, Embeddings
import ollama
from gene import cluster_pipeline

DIRETORIO_ARTIGOS = "./artigos"
CAMINHO_BANCO_VETORIAL = "./chroma_db_arctic"
NOME_COLECAO = "banco_literatura_bio"

MODELO_LLM = "qwen3:0.6b"
MODELO_EMBEDDING = "snowflake-arctic-embed2:568m"

class FuncaoEmbedding(EmbeddingFunction):
    def __call__(self, entrada: Documents) -> Embeddings:
        vetores = []
        for texto in entrada:
            texto_limpo = texto.replace("\n", " ")
            resposta = ollama.embeddings(model=MODELO_EMBEDDING, prompt=texto_limpo)
            vetores.append(resposta["embedding"])
        return vetores

def ler_artigos():
    if not os.path.exists(DIRETORIO_ARTIGOS):
        os.makedirs(DIRETORIO_ARTIGOS)
        print(f"[AVISO] Pasta '{DIRETORIO_ARTIGOS}' criada.")
        return []

    arquivos = glob.glob(os.path.join(DIRETORIO_ARTIGOS, "*.md"))
    fragmentos = []

    print(f">>> Lendo {len(arquivos)} arquivos de literatura...")
    for caminho_arquivo in arquivos:
        with open(caminho_arquivo, "r", encoding="utf-8") as f:
            conteudo = f.read()

        tamanho_fragmento, sobreposicao = 1000, 200
        for i in range(0, len(conteudo), tamanho_fragmento - sobreposicao):
            segmento = conteudo[i : i + tamanho_fragmento]
            fragmentos.append({
                "texto": segmento,
                "fonte": os.path.basename(caminho_arquivo),
                "id": f"{os.path.basename(caminho_arquivo)}_{i}"
            })
    return fragmentos

def inicializar_banco_vetorial(fragmentos):
    cliente = chromadb.PersistentClient(path=CAMINHO_BANCO_VETORIAL)
    funcao_embedding = FuncaoEmbedding()
    colecao = cliente.get_or_create_collection(name=NOME_COLECAO, embedding_function=funcao_embedding)

    if len(fragmentos) > 0 and colecao.count() == 0:
        print(f">>> Indexando {len(fragmentos)} fragmentos...")
        tamanho_lote = 50
        for i in range(0, len(fragmentos), tamanho_lote):
            lote = fragmentos[i : i + tamanho_lote]
            colecao.add(
                documents=[c["texto"] for c in lote],
                metadatas=[{"fonte": c["fonte"]} for c in lote],
                ids=[c["id"] for c in lote]
            )
    else:
        print(f">>> Banco carregado ({colecao.count()} fragmentos).")
    return colecao

def analisar_descricao_cluster(colecao, lista_genes):
    genes_str = ", ".join(lista_genes[:50])

    print(f"   [Cluster] Identifying theme ({len(lista_genes)} genes)...")

    consulta = f"biological pathway and function shared by genes: {genes_str}"
    resultados = colecao.query(query_texts=[consulta], n_results=5)

    contexto = ""
    if resultados['documents'][0]:
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
        print(f"Erro no cluster: {e}")
        return "Descrição indisponível."

def analisar_coesao_cluster(colecao, lista_genes, descricao_tema):
    print(f"   [Validation] Verifying outliers and cohesion...")

    genes_str = ", ".join(lista_genes[:99])
    if len(lista_genes) > 99:
        genes_str += "..."

    consulta = f"functional differences and distinct pathways among genes: {genes_str}"
    resultados = colecao.query(query_texts=[consulta], n_results=3)

    contexto = ""
    if resultados['documents'][0]:
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
        print(f"      [!] Erro na validação: {e}")
        return {
            "cohesion_status": "Error",
            "justification": "Could not validate due to LLM error.",
            "core_genes": [],
            "outliers": []
        }

def analisar_representante(colecao, gene_rep, descricao_do_cluster):
    print(f"      -> Analisando Representante: {gene_rep}...")

    consulta = f"functional role of {gene_rep} in context of {descricao_do_cluster}"
    resultados = colecao.query(query_texts=[consulta], n_results=3)

    contexto_str = ""
    fontes = []
    if resultados['documents'][0]:
        contexto_str = "\n\n".join(resultados['documents'][0])
        fontes = sorted(list(set(m['fonte'] for m in resultados['metadatas'][0])))

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
        print(f"      [!] Erro gene {gene_rep}: {e}")
        return None

def executar_pipeline_completo(colecao, dados_clusters):
    print("\n>>> Iniciando Análise Hierárquica e Validação...")

    relatorio_final = []

    for nome_cluster, dados in dados_clusters.items():
        print(f"\n--- Processando {nome_cluster} ---")

        rep_gene = dados['representative']
        todos_genes = dados['genes']

        descricao_cluster = analisar_descricao_cluster(colecao, todos_genes)
        print(f"   [Theme]: {descricao_cluster}...")

        dados_validacao = analisar_coesao_cluster(colecao, todos_genes, descricao_cluster)
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

    salvar_resultados(relatorio_final)

def salvar_resultados(dados):
    with open("Relatorio_Final_Estruturado.json", "w", encoding="utf-8") as f:
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

    with open("Relatorio_Final.md", "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    print(f"\n>>> Relatórios salvos com sucesso!")
    print("    - Relatorio_Final_Estruturado.json")
    print("    - Relatorio_Final.md")

if __name__ == "__main__":
    clusters_dict = cluster_pipeline()

    if clusters_dict:
        textos = ler_artigos()
        kb = inicializar_banco_vetorial(textos)

        executar_pipeline_completo(kb, clusters_dict)
    else:
        print("Erro: O pipeline de clusters não retornou dados.")

