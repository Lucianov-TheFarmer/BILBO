import sys
import os
import pandas as pd
import matplotlib.pyplot as plt
from venny4py.venny4py import venny4py

def get_significant_genes(df, gene_column='Unnamed: 0', fdr_threshold=0.05, logfc_threshold=1):
    """
    Extrai genes significativos de um dataframe DEG
    
    Args:
        df: DataFrame com dados DEG
        gene_column: Nome da coluna com IDs dos genes
        fdr_threshold: Threshold de FDR (padrão 0.05)
        logfc_threshold: Threshold de |logFC| (padrão 1)
    
    Returns:
        set: Conjunto de genes significativos
    """
    if 'FDR' not in df.columns or 'logFC' not in df.columns:
        raise ValueError("Colunas 'FDR' e 'logFC' são obrigatórias")
    
    # Filtra genes significativos
    significant = df[(df['FDR'] < fdr_threshold) & (abs(df['logFC']) > logfc_threshold)]
    
    # Retorna conjunto de IDs dos genes
    return set(significant[gene_column].astype(str))

def generate_venn_diagram(contrasts_list, deg_xlsx_path, output_path, title="Venn Diagram"):
    """
    Gera diagrama de Venn padronizado usando venny4py
    """
    if not os.path.exists(deg_xlsx_path):
        raise FileNotFoundError(f"Arquivo DEG.xlsx não encontrado: {deg_xlsx_path}")
    
    if len(contrasts_list) < 2 or len(contrasts_list) > 4:
        raise ValueError("Diagrama de Venn suporta apenas 2-4 contrastes")
    
    # Carrega dados dos contrastes
    gene_sets = {}
    xls = pd.ExcelFile(deg_xlsx_path)
    
    for contrast in contrasts_list:
        if contrast not in xls.sheet_names:
            print(f"Aviso: Contraste '{contrast}' não encontrado no DEG.xlsx")
            continue
            
        df = pd.read_excel(xls, sheet_name=contrast)
        
        try:
            genes = get_significant_genes(df)
            gene_sets[contrast] = genes
            print(f"Contraste '{contrast}': {len(genes)} genes significativos")
        except Exception as e:
            print(f"Erro ao processar contraste '{contrast}': {e}")
            continue
    
    xls.close()
    
    if len(gene_sets) < 2:
        raise ValueError("Pelo menos 2 contrastes válidos são necessários")
    
    # Prepara os dados para venny4py - usa apenas os nomes dos contrastes como labels
    sets_dict = {}
    for i, (contrast_name, gene_set) in enumerate(gene_sets.items()):
        # Usa nomes simples como Set1, Set2, etc. para labels limpos
        sets_dict[contrast_name] = gene_set
    
    # Gera o diagrama usando venny4py
    try:
        # Muda para o diretório onde o arquivo deve ser salvo
        original_dir = os.getcwd()
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.chdir(output_dir)
        
        # venny4py gera automaticamente e salva o diagrama
        venny4py(sets=sets_dict)
        
        # venny4py cria arquivos com nomes específicos baseados no número de conjuntos
        num_sets = len(sets_dict)
        generated_file = f"Venn_{num_sets}.png"
        
        # Move o arquivo gerado para o local correto com o nome correto
        if os.path.exists(generated_file):
            final_filename = os.path.basename(output_path)
            if generated_file != final_filename:
                if os.path.exists(final_filename):
                    os.remove(final_filename)  # Remove arquivo existente se houver
                os.rename(generated_file, final_filename)
            
            print(f"Diagrama de Venn salvo em: {output_path}")
        else:
            print(f"Erro: Arquivo {generated_file} não foi criado pelo venny4py")
        
        # Volta para o diretório original
        os.chdir(original_dir)
        
    except Exception as e:
        print(f"Erro ao gerar diagrama com venny4py: {e}")
        # Volta para o diretório original em caso de erro
        try:
            os.chdir(original_dir)
        except:
            pass

def main():
    if len(sys.argv) not in [4, 5]:
        print("Uso: python venn_diagram.py <contrasts_file> <deg_xlsx_path> <output_png_path> [<title>]")
        print("Exemplo: python venn_diagram.py contrasts.txt /path/DEG.xlsx /path/output.png \"Meu Venn\"")
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
    
    if len(contrasts) < 2 or len(contrasts) > 4:
        print("Erro: Diagrama de Venn requer 2-4 contrastes")
        sys.exit(1)
    
    # Usa título fornecido como parâmetro ou extrai do nome do arquivo
    if len(sys.argv) == 5:
        title = sys.argv[4]
    else:
        # Extrai título do nome do arquivo
        title = os.path.basename(contrasts_file)
        if title.startswith("VENN - "):
            title = title[7:]  # Remove "VENN - "
        if title.endswith(".txt"):
            title = title[:-4]  # Remove ".txt"
    
    try:
        generate_venn_diagram(contrasts, deg_xlsx_path, output_png_path, title)
        print("Diagrama de Venn gerado com sucesso!")
    except Exception as e:
        print(f"Erro ao gerar diagrama de Venn: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()