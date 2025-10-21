import sys
import os
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import FuncFormatter

def generate_multiple_barplot(contrasts_list, deg_xlsx_path, output_path, title="Multiple Contrasts"):
    """
    Gera um barplot múltiplo com os contrastes especificados
    
    Args:
        contrasts_list: Lista de nomes dos contrastes (abas do DEG.xlsx)
        deg_xlsx_path: Caminho para o arquivo DEG.xlsx
        output_path: Caminho de saída para o PNG
        title: Título do gráfico
    """
    if not os.path.exists(deg_xlsx_path):
        raise FileNotFoundError(f"Arquivo DEG.xlsx não encontrado: {deg_xlsx_path}")
    
    # Carrega dados dos contrastes
    data_for_plot = []
    xls = pd.ExcelFile(deg_xlsx_path)
    
    for contrast in contrasts_list:
        if contrast not in xls.sheet_names:
            print(f"Aviso: Contraste '{contrast}' não encontrado no DEG.xlsx")
            continue
            
        df = pd.read_excel(xls, sheet_name=contrast)
        
        if 'logFC' not in df.columns:
            print(f"Aviso: Coluna 'logFC' não encontrada no contraste '{contrast}'")
            continue
            
        # Conta up e down regulados
        up = (df['logFC'] > 1).sum()
        down = (df['logFC'] < -1).sum()
        
        data_for_plot.append({
            'contrast': contrast,
            'up': up,
            'down': down
        })
    
    xls.close()
    
    if not data_for_plot:
        raise ValueError("Nenhum contraste válido encontrado para gerar o gráfico")
    
    # Prepara dados para o gráfico
    contrasts = [item['contrast'] for item in data_for_plot]
    up_values = [item['up'] for item in data_for_plot]
    down_values = [-item['down'] for item in data_for_plot]  # Negativo para mostrar para baixo
    
    # Configurações do gráfico
    fig, ax = plt.subplots(figsize=(max(12, len(contrasts) * 2), 8))
    
    x_pos = np.arange(len(contrasts))
    bar_width = 0.35
    
    # Cores
    up_color = '#1976D2'    # Azul
    down_color = '#D32F2F'  # Vermelho
    
    # Cria as barras
    bars_up = ax.bar(x_pos, up_values, bar_width, color=up_color, label='Up-regulated')
    bars_down = ax.bar(x_pos, down_values, bar_width, color=down_color, label='Down-regulated')
    
    # Adiciona valores nas barras
    max_val = max(max(up_values), max([abs(v) for v in down_values]), 1)
    
    for i, (up, down) in enumerate(zip(up_values, down_values)):
        # Valor para up (positivo)
        ax.text(i, up + max_val*0.02, str(up), ha='center', va='bottom', 
                fontsize=12, color=up_color, fontweight='bold')
        # Valor para down (negativo, mas mostra valor positivo)
        ax.text(i, down - max_val*0.02, str(abs(down)), ha='center', va='top', 
                fontsize=12, color=down_color, fontweight='bold')
    
    # Configurações dos eixos
    ax.set_xlabel('Contrasts', fontsize=14)
    ax.set_ylabel('Number of genes', fontsize=14)
    ax.set_title(title, fontsize=18, weight='bold', pad=20)
    
    # Configura eixo X
    ax.set_xticks(x_pos)
    ax.set_xticklabels(contrasts, rotation=45, ha='right')
    
    # Configura eixo Y para mostrar valores absolutos
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: str(abs(int(x))) if x != 0 else '0'))
    
    # Ajusta limites do eixo Y
    y_margin = max_val * 0.15
    ax.set_ylim(-max_val - y_margin, max_val + y_margin)
    
    # Linha horizontal no zero
    ax.axhline(0, color='black', linewidth=1.2)
    
    # Remove spines superiores e direitas
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    
    # Legenda
    ax.legend(loc='upper right', frameon=False, fontsize=12)
    
    # Layout e salvamento
    plt.tight_layout()
    plt.savefig(output_path, dpi=200, bbox_inches='tight')
    plt.close(fig)
    
    print(f"Barplot múltiplo salvo em: {output_path}")

def main():
    if len(sys.argv) not in [4, 5]:
        print("Uso: python multiple_barplot.py <contrasts_file> <deg_xlsx_path> <output_png_path> [<title>]")
        print("Exemplo: python multiple_barplot.py contrasts.txt /path/DEG.xlsx /path/output.png \"Meu Título\"")
        sys.exit(1)
    
    contrasts_file = sys.argv[1]
    deg_xlsx_path = sys.argv[2]
    output_png_path = sys.argv[3]
    
    # Lê a lista de contrastes do arquivo
    if not os.path.exists(contrasts_file):
        print(f"Erro: Arquivo de contrastes não encontrado: {contrasts_file}")
        sys.exit(1)
    
    with open(contrasts_file, 'r', encoding='utf-8') as f:
        contrasts = [line.strip() for line in f.readlines() if line.strip()]
    
    if not contrasts:
        print("Erro: Nenhum contraste encontrado no arquivo")
        sys.exit(1)
    
    # Usa título fornecido como parâmetro ou extrai do nome do arquivo
    if len(sys.argv) == 5:
        title = sys.argv[4]
    else:
        # Extrai título do nome do arquivo (remove "BARPLOT - " e ".txt")
        title = os.path.basename(contrasts_file)
        if title.startswith("BARPLOT - "):
            title = title[10:]  # Remove "BARPLOT - "
        if title.endswith(".txt"):
            title = title[:-4]  # Remove ".txt"
    
    try:
        generate_multiple_barplot(contrasts, deg_xlsx_path, output_png_path, title)
        print("Barplot múltiplo gerado com sucesso!")
    except Exception as e:
        print(f"Erro ao gerar barplot múltiplo: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()