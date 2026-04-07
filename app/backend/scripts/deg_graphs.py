import sys
import os
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

def plot_deg_graphs(sheet_name, df, output_dir):
    # Conta up e down regulados
    up = (df['logFC'] > 1).sum()
    down = (df['logFC'] < -1).sum()
    # Dados para o gráfico
    values = [up, -down]
    colors = ['#1976D2', '#D32F2F']  # azul, vermelho
    labels = ['Up-regulated', 'Down-regulated']

    # Tamanho semelhante ao save_png("edgeR_MDS.png", width=12, height=8, ...)
    fig, ax = plt.subplots(figsize=(12, 8))
    bar_width = 0.18  # barras mais finas

    bars = [
        ax.bar(0, up, color=colors[0], width=bar_width, label=labels[0]),
        ax.bar(0, down, color=colors[1], width=bar_width, bottom=-down, label=labels[1])
    ]

    max_val = max(up, down, 1)
    ax.set_ylim(-max_val * 1.15, max_val * 1.15)
    ax.set_xticks([0])
    ax.set_xticklabels([''])    # Eixo y simétrico

    # Customiza os rótulos do eixo y para mostrar apenas valores positivos
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: str(abs(int(x))) if x != 0 else '0'))

    # Adiciona valores nas barras
    ax.text(0, up + max_val*0.04, str(up), ha='center', va='bottom', fontsize=18, color=colors[0], fontweight='bold')
    ax.text(0, -down - max_val*0.04, str(down), ha='center', va='top', fontsize=18, color=colors[1], fontweight='bold')
    # Título (apenas nome da aba, centralizado e ajustado)
    ax.set_title(sheet_name, fontsize=22, weight='bold', pad=22)
    # Remove spines extras
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    # Linha horizontal no zero
    ax.axhline(0, color='black', linewidth=1.2)
    # Legenda abaixo do gráfico, centralizada
    fig.legend(bars, labels, loc='lower center', bbox_to_anchor=(0.5, -0.08), ncol=2, frameon=False, fontsize=16)
    # Deixa o eixo x mais largo visualmente
    ax.set_xlim(-0.7, 0.7)
    plt.tight_layout(rect=[0, 0.05, 1, 1])
    # Salva o gráfico
    output_path = os.path.join(output_dir, f"BARPLOT.ISOLADO - {sheet_name}.png")
    plt.savefig(output_path, dpi=200, bbox_inches='tight')
    plt.close(fig)

    # --- MA plot ---
    # Só plota se tiver as colunas necessárias
    if 'logFC' in df.columns and 'logCPM' in df.columns:
        fig_ma, ax_ma = plt.subplots(figsize=(12, 8))
        ax_ma.scatter(df['logCPM'], df['logFC'], c='grey', alpha=0.6, s=18, edgecolor='none')
        # Destaca up e down
        ax_ma.scatter(df.loc[df['logFC'] > 1, 'logCPM'], df.loc[df['logFC'] > 1, 'logFC'], c='#1976D2', label='Up-regulated', s=22)
        ax_ma.scatter(df.loc[df['logFC'] < -1, 'logCPM'], df.loc[df['logFC'] < -1, 'logFC'], c='#D32F2F', label='Down-regulated', s=22)
        ax_ma.axhline(1, color='#1976D2', linestyle='--', linewidth=1)
        ax_ma.axhline(-1, color='#D32F2F', linestyle='--', linewidth=1)
        ax_ma.axhline(0, color='black', linewidth=1)
        ax_ma.set_xlabel('logCPM', fontsize=18)
        ax_ma.set_ylabel('logFC', fontsize=18)
        ax_ma.set_title(f"{sheet_name}", fontsize=22, weight='bold', pad=22)
        plt.tight_layout()
        output_ma = os.path.join(output_dir, f"MA.ISOLADO - {sheet_name}.png")
        plt.savefig(output_ma, dpi=200, bbox_inches='tight')
        plt.close(fig_ma)

    # --- Volcano plot ---
    # Só plota se tiver as colunas necessárias
    if 'logFC' in df.columns and 'FDR' in df.columns:
        import numpy as np
        fig_volcano, ax_volcano = plt.subplots(figsize=(12, 8))
        # Calcula -log10(FDR), trata FDR zero
        fdrs = df['FDR'].replace(0, 1e-300)
        neglog_fdr = -np.log10(fdrs)
        # Cores para up/down/other
        colors = np.where(df['logFC'] > 1, '#1976D2', np.where(df['logFC'] < -1, '#D32F2F', 'grey'))
        ax_volcano.scatter(df['logFC'], neglog_fdr, c=colors, alpha=0.6, s=18, edgecolor='none')
        # Linhas de corte
        ax_volcano.axvline(1, color='#1976D2', linestyle='--', linewidth=1)
        ax_volcano.axvline(-1, color='#D32F2F', linestyle='--', linewidth=1)
        ax_volcano.axhline(-np.log10(0.05), color='black', linestyle='--', linewidth=1)
        ax_volcano.set_xlabel('logFC', fontsize=18)
        ax_volcano.set_ylabel('-logFDR', fontsize=18)
        ax_volcano.set_title(f"{sheet_name}", fontsize=22, weight='bold', pad=22)
        
        plt.tight_layout()
        output_volcano = os.path.join(output_dir, f"VOLCANO.ISOLADO - {sheet_name}.png")
        plt.savefig(output_volcano, dpi=200, bbox_inches='tight')
        plt.close(fig_volcano)

    # --- Ontology frequency plot ---
    # Espera colunas: GO_BP, GO_MF, GO_CC (ajuste se necessário)
    go_cols = {
        "BP": "Uniprot BP",
        "MF": "Uniprot MF",
        "CC": "Uniprot CC"
    }
    freq_data = []
    for cat, col in go_cols.items():
        if col in df.columns:
            # Conta frequência de cada termo (pode ser separado por ; ou |)
            terms = df[col].dropna().astype(str).str.split(r";|,|\|").explode().str.strip()
            terms = terms[terms != ""]
            top_terms = terms.value_counts().head(15)
            for term, count in top_terms.items():
                freq_data.append({"Term": term, "Count": count, "Category": cat})

    if freq_data:
        freq_df = pd.DataFrame(freq_data)
        freq_df['Term'] = freq_df['Term'].astype(str)
        # Remove código GO entre colchetes dos nomes dos termos
        import re
        def remove_go_code(term):
            return re.sub(r"\s*\[.*?\]", "", term).strip()
        freq_df['TermNoGO'] = freq_df['Term'].apply(remove_go_code)
        cat_colors = {"BP": "#1976D2", "MF": "#388E3C", "CC": "#FBC02D"}
        import seaborn as sns
        fig_onto, ax_onto = plt.subplots(figsize=(12, 8))
        plot_df = freq_df.copy()
        plot_df['Term+Cat'] = plot_df['TermNoGO'] + " (" + plot_df['Category'] + ")"
        sns.barplot(
            data=plot_df,
            y="Term+Cat",
            x="Count",
            hue="Category",
            dodge=False,
            palette=cat_colors,
            ax=ax_onto
        )
        ax_onto.set_xlabel("Frequency", fontsize=16)
        ax_onto.set_ylabel("GO term", fontsize=16)
        # Remove legenda
        ax_onto.legend_.remove()
        # Centraliza o título manualmente considerando o tamanho da figura
        fig_width = fig_onto.get_size_inches()[0]
        fig_onto.suptitle(
            f"Top 15 GO terms - {sheet_name}",
            fontsize=20,
            weight='bold',
            x=0.5,
            y=0.96,
            ha='center'
        )
        plt.tight_layout(rect=[0, 0, 1, 0.96])
        output_onto = os.path.join(output_dir, f"ONTO_FREQ.ISOLADO - {sheet_name}.png")
        plt.savefig(output_onto, dpi=200, bbox_inches='tight')
        plt.close(fig_onto)

def main():
    if len(sys.argv) != 3:
        print("Uso: python deg_graphs.py <deg_xlsx_path> <output_dir>")
        sys.exit(1)
    deg_xlsx_path = sys.argv[1]
    output_dir = sys.argv[2]
    xls = pd.ExcelFile(deg_xlsx_path)
    for sheet in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet)
        if 'logFC' not in df.columns:
            continue
        plot_deg_graphs(sheet, df, output_dir)
        print(f"Gráficos DEG salvos para aba: {sheet}")

if __name__ == "__main__":
    main()
