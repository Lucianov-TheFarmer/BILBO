import pandas as pd
import numpy as np
import os
import umap
import matplotlib.pyplot as plt
import seaborn as sns
import matplotlib.colors as mcolors
import json
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans
from sklearn.metrics import pairwise_distances_argmin_min, silhouette_score
from adjustText import adjust_text
import re
from unidecode import unidecode
from nltk.stem import SnowballStemmer

SEED = 42
K_RANGE = range(2, 21)
COL_ID = 'Product GFF'
COL_LFC = 'logFC'
COL_PADJ = 'FDR'
COLS_TXT = ['Uniprot Function', 'Uniprot BP', 'Uniprot CC', 'Uniprot MF']


def clean_text(text):
    if not isinstance(text, str): return ""

    text = re.sub(r'\[.*?\]|\{.*?\}', ' ', text)
    text = unidecode(text).lower()
    text = re.sub(r'[^a-z\s]', ' ', text)
    text = text.replace('function', '').replace('activity', '')

    stemmer = SnowballStemmer("english")
    return " ".join([stemmer.stem(t) for t in text.split() if len(t) > 2])


def load_and_process_data(path, sheet_name=None):
    print(">>> [1/5] Carregando e limpando dados...")
    # If sheet_name is provided, read only that sheet (contrast-specific)
    df = pd.read_excel(path, sheet_name=sheet_name) if sheet_name else pd.read_excel(path)
    df = df.dropna(subset=[COL_LFC, COL_PADJ, COL_ID])

    for col in COLS_TXT:
        if col in df.columns:
            df[col] = df[col].fillna('').apply(clean_text)

    df['text'] = df[COLS_TXT].apply(lambda x: ' '.join(x), axis=1)
    df = df[df['text'].str.len() > 5]
    df['log2FoldChange'] = df[COL_LFC].abs()

    return df


def vectorize_text(df):
    print(">>> [2/5] Vetorizando texto (TF-IDF)...")
    vectorizer = TfidfVectorizer(stop_words='english', min_df=3, max_features=300)
    matrix = vectorizer.fit_transform(df['text']).toarray()
    return matrix, vectorizer


def find_optimal_k(coords, img_metrics_path):
    print(">>> [3/5] Buscando número ideal de clusters (K)...")
    inertias = []
    silhouettes = []

    for k in K_RANGE:
        km = KMeans(n_clusters=k, init='k-means++', random_state=SEED, n_init=100)
        labels = km.fit_predict(coords)

        inertias.append(km.inertia_)
        silhouettes.append(silhouette_score(coords, labels))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    ax1.plot(K_RANGE, inertias, 'bo-', markersize=8)
    ax1.set_title('Elbow Method')
    ax1.set_xlabel('Clusters number (K)')
    ax1.set_xticks(K_RANGE)
    ax1.grid(True)

    ax2.plot(K_RANGE, silhouettes, 'go-', markersize=8)
    ax2.set_title('Silhouette Score')
    ax2.set_xlabel('Clusters number (K)')
    ax2.set_xticks(K_RANGE)
    ax2.grid(True)

    plt.tight_layout()
    plt.savefig(img_metrics_path, dpi=300)
    print(f"    -> Gráfico de métricas salvo: {img_metrics_path}")

    best_k = K_RANGE[np.argmax(silhouettes)]
    print(f"    -> Melhor K encontrado: {best_k} (Score: {max(silhouettes):.3f})")

    return best_k


def analyze_clusters(df, matrix, vectorizer, reps):
    print(f"\n{' ANÁLISE DE CONTEÚDO ':*^50}")

    term_df = pd.DataFrame(matrix, columns=vectorizer.get_feature_names_out())
    term_df['cluster'] = df['cluster'].values
    means = term_df.groupby('cluster').mean()

    for c_id in sorted(means.index):
        top_terms = means.loc[c_id].nlargest(10)
        terms_str = ", ".join([f"{t}" for t, _ in top_terms.items()])

        rep_name = reps.iloc[c_id][COL_ID]

        print(f"Cluster {c_id} | Rep: {rep_name}")
        print(f"   Termos: {terms_str}\n")
    print("*"*50)


def plot_final_map(df, reps, score, k, img_final_path):
    print(">>> [5/5] Gerando mapa...")
    sns.set_style("ticks")
    sns.set_context("paper", font_scale=1.3)

    plt.figure(figsize=(12, 10))

    sorted_clusters = sorted(df['cluster'].unique())
    hue_order = [f"C{i}" for i in sorted_clusters]

    # Build a contrasting palette with enough distinct colors for all clusters
    n_colors = len(sorted_clusters)
    if n_colors <= 20:
        pal = sns.color_palette("tab20", n_colors=n_colors)
    else:
        # use HLS for larger numbers to get evenly spaced hues
        pal = sns.color_palette("hls", n_colors=n_colors)

    # Convert to hex strings to avoid invalid RGBA arguments
    palette = [mcolors.to_hex(c) for c in pal]

    sns.scatterplot(
        data=df, x='x', y='y',
        hue='cluster_label',
        hue_order=hue_order,
        size='log2FoldChange', sizes=(50, 400),
        palette=palette, alpha=0.8,
        edgecolor='white', linewidth=0.5
    )

    plt.scatter(
        reps['x'], reps['y'],
        s=500, facecolors='none', edgecolors='#222222',
        linewidth=2, linestyle='--'
    )

    texts = []
    for _, row in reps.iterrows():
        name = str(row[COL_ID])
        name = name[:15] + "..." if len(name) > 15 else name

        txt = plt.text(
            row['x'], row['y'], name,
            fontsize=10, weight='bold', color='#111111',
            bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="gray", alpha=0.9)
        )
        texts.append(txt)

    adjust_text(texts, arrowprops=dict(arrowstyle='-', color='#444444', lw=1))

    sns.despine(trim=True, offset=10)
    plt.legend(bbox_to_anchor=(1.01, 1), loc='upper left', frameon=False, title=f"K={k}")
    plt.title(f'Cluster Map', pad=20)
    plt.xlabel("UMAP Dimension 1")
    plt.ylabel("UMAP Dimension 2")

    plt.tight_layout()
    plt.savefig(img_final_path, dpi=300)
    print(f"    -> Gráfico salvo: {img_final_path}")


def cluster_pipeline(file_path, sheet_name=None, img_final_path='Cluster.png', img_metrics_path='Otimizacao_K.png', clusters_json_path=None):
    df = load_and_process_data(file_path, sheet_name=sheet_name)
    matrix, vec = vectorize_text(df)

    print(">>> [3/5] Projetando dados (UMAP)...")
    umap_model = umap.UMAP(n_neighbors=20, min_dist=0.0, n_components=2, metric='cosine', random_state=SEED, n_jobs=1)
    coords = umap_model.fit_transform(matrix)
    df['x'], df['y'] = coords[:, 0], coords[:, 1]

    best_k = find_optimal_k(coords, img_metrics_path)

    print(f">>> [4/5] Aplicando KMeans (K={best_k})...")
    kmeans = KMeans(n_clusters=best_k, init='k-means++', random_state=SEED, n_init=100)
    labels = kmeans.fit_predict(coords)

    df['cluster'] = labels
    df['cluster_label'] = [f"C{l}" for l in labels]

    final_score = silhouette_score(coords, labels)
    closest, _ = pairwise_distances_argmin_min(kmeans.cluster_centers_, coords)

    reps = df.iloc[closest].copy()

    analyze_clusters(df, matrix, vec, reps)
    plot_final_map(df, reps, final_score, best_k, img_final_path)

    dados_estruturados = {}

    for c_id in sorted(df['cluster'].unique()):
        genes_do_grupo = df[df['cluster'] == c_id][COL_ID].tolist()
        representante = reps[reps['cluster'] == c_id][COL_ID].values[0]

        dados_estruturados[f"Cluster {c_id}"] = {
            "representative": representante,
            "genes": genes_do_grupo
        }

    print(f">>> Pipeline Finalizada. Dados estruturados para {len(dados_estruturados)} clusters.")

    # Determine clusters_json_path if not provided: save next to img_final_path
    try:
        if clusters_json_path is None:
            img_dir = os.path.dirname(os.path.abspath(img_final_path)) or os.getcwd()
            clusters_json_path = os.path.join(img_dir, 'clusters.json')

        with open(clusters_json_path, 'w', encoding='utf-8') as jf:
            json.dump(dados_estruturados, jf, indent=2, ensure_ascii=False)
        print(f"    -> Clusters JSON salvo: {clusters_json_path}")
    except Exception as e:
        print(f"    [!] Erro ao salvar clusters JSON: {e}")

    return {
        "clusters": dados_estruturados,
        "img_final": img_final_path,
        "img_metrics": img_metrics_path,
        "clusters_json": clusters_json_path,
        "score": float(final_score),
        "k": int(best_k)
    }


if __name__ == "__main__":
    import sys
    path = sys.argv[1]
    cluster_pipeline(path)
