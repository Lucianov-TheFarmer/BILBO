import sys
import pandas as pd
import requests
import time
import threading

def is_plant(lineage, organism=None):
    # Se lineage está vazio, tenta usar o nome do organismo como fallback
    if not lineage and organism:
        organism = organism.lower()
        plant_terms = [
            "arabidopsis", "oryza", "zea", "glycine", "solanum", "vitis", "coffea", "brassica", "gossypium",
            "triticum", "hordeum", "sorghum", "setaria", "brachypodium", "populus", "eucalyptus", "cucumis",
            "cucurbita", "cicer", "phaseolus", "pisum", "medicago", "lotus", "lupinus", "fragaria", "malus",
            "prunus", "pyrus", "citrus", "theobroma", "camellia", "spinacia", "beta vulgaris", "spinach", "lettuce",
            "lettuca", "plant", "plantae"
        ]
        for term in plant_terms:
            if term in organism:
                return True
        return False
    if not lineage:
        return False
    lineage = lineage.lower()
    plant_terms = [
        "viridiplantae", "streptophyta", "embryophyta", "tracheophyta", "euphyllophyta",
        "spermatophyta", "magnoliopsida", "mesangiospermae", "eudicotyledons", "monocots",
        "liliopsida", "chlorophyta", "chloroplast", "plantae", "plant"
    ]
    return any(term in lineage for term in plant_terms)

def fetch_uniprot_info(query):
    url = (
        "https://rest.uniprot.org/uniprotkb/search"
        f"?query={requests.utils.quote(query)}"
        "&fields=organism_name&fields=lineage&fields=gene_names&fields=id"
        "&fields=go_p&fields=go_f&fields=go_c&fields=cc_function"
        "&format=tsv"
    )
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 400:
            return {}
        if resp.status_code != 200 or not resp.text.strip():
            return {}
        lines = resp.text.strip().split("\n")
        if len(lines) < 2:
            return {}
        header = lines[0].split("\t")
        # Parse all results and prioritize plants
        best_data = None
        for line in lines[1:]:
            data = dict(zip(header, line.split("\t")))
            organism = data.get('Organism', '')
            lineage = data.get('Lineage', '')
            has_function = bool(data.get("Function [CC]", "").strip())
            has_ontology = (
                bool(data.get("Gene Ontology (cellular component)", "").strip()) or
                bool(data.get("Gene Ontology (molecular function)", "").strip()) or
                bool(data.get("Gene Ontology (biological process)", "").strip())
            )
            if (is_plant(lineage, organism) and (has_function or has_ontology)):
                best_data = data
                break
        if not best_data:
            for line in lines[1:]:
                data = dict(zip(header, line.split("\t")))
                organism = data.get('Organism', '')
                lineage = data.get('Lineage', '')
                has_function = bool(data.get("Function [CC]", "").strip())
                has_ontology = (
                    bool(data.get("Gene Ontology (cellular component)", "").strip()) or
                    bool(data.get("Gene Ontology (molecular function)", "").strip()) or
                    bool(data.get("Gene Ontology (biological process)", "").strip())
                )
                if has_function or has_ontology:
                    best_data = data
                    break
        if not best_data:
            best_data = dict(zip(header, lines[1].split("\t")))
        return {
            "Uniprot organism": best_data.get("Organism", ""),
            "Uniprot gene names": best_data.get("Gene Names", ""),
            "Uniprot CC": best_data.get("Gene Ontology (cellular component)", ""),
            "Uniprot MF": best_data.get("Gene Ontology (molecular function)", ""),
            "Uniprot BP": best_data.get("Gene Ontology (biological process)", ""),
            "Uniprot Function": best_data.get("Function [CC]", ""),
        }
    except Exception as ex:
        return {}

def annotate_deg_with_uniprot(deg_xlsx_path):
    xls = pd.ExcelFile(deg_xlsx_path)
    sheet_names = xls.sheet_names
    for sheet in sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet)
        # Use Note GFF, depois Product GFF, depois Name GFF
        query_col = None
        if "Note GFF" in df.columns and df["Note GFF"].notna().any():
            query_col = "Note GFF"
        elif "Product GFF" in df.columns and df["Product GFF"].notna().any():
            query_col = "Product GFF"
        # elif "Name GFF" in df.columns and df["Name GFF"].notna().any():
        #     query_col = "Name GFF"
        else:
            # Garante que as colunas Uniprot existam mesmo se não houver query_col
            for col in [
                "Uniprot organism", "Uniprot gene names",
                "Uniprot CC", "Uniprot MF", "Uniprot BP", "Uniprot Function"
            ]:
                if col not in df.columns:
                    df[col] = ""
            # Salva a aba sobrescrevendo (adiciona colunas vazias)
            with pd.ExcelWriter(deg_xlsx_path, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
                df.to_excel(writer, sheet_name=sheet, index=False)
            continue  # Nenhuma coluna disponível para consulta

        # Garante que as colunas Uniprot existam e sejam do tipo objeto
        for col in [
            "Uniprot organism", "Uniprot gene names",
            "Uniprot CC", "Uniprot MF", "Uniprot BP", "Uniprot Function"
        ]:
            if col not in df.columns:
                df[col] = ""
            df[col] = df[col].astype("object")

        for idx, row in df.iterrows():
            query_value = str(row[query_col]).strip()
            if not query_value or query_value == "nan":
                continue
            info = fetch_uniprot_info(query_value)
            for col in [
                "Uniprot organism", "Uniprot gene names",
                "Uniprot CC", "Uniprot MF", "Uniprot BP", "Uniprot Function"
            ]:
                df.at[idx, col] = str(info.get(col, "")) if info else ""

        # Salva a aba sobrescrevendo
        with pd.ExcelWriter(deg_xlsx_path, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
            df.to_excel(writer, sheet_name=sheet, index=False)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python annotate_deg_with_uniprot.py <deg_xlsx_path>")
        sys.exit(1)
    deg_xlsx_path = sys.argv[1]
    annotate_deg_with_uniprot(deg_xlsx_path)
    print("DEG.xlsx anotado com informações do Uniprot.")
