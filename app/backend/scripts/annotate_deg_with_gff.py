import os
import sys
import pandas as pd

def parse_gff_attributes(attr_str):
    attrs = {}
    for item in attr_str.split(";"):
        if "=" in item:
            key, val = item.split("=", 1)
            attrs[key] = val
    return attrs

def load_gff_info(gff_path):
    gff_info = {}
    with open(gff_path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("#"):
                continue
            parts = line.strip().split("\t")
            if len(parts) < 9:
                continue
            feature_type = parts[2]
            attrs = parse_gff_attributes(parts[8])
            if feature_type in ("gene", "mRNA", "transcript"):
                gene_id = attrs.get("ID")
                name = attrs.get("Name")
                product = attrs.get("Product")
                note = attrs.get("Note")
                if gene_id:
                    gff_info[gene_id] = {
                        "Name": name,
                        "Product": product,
                        "Note": note
                    }
    return gff_info

def find_gff_for_gene(gene_id, gff_info):
    if gene_id in gff_info:
        return gff_info[gene_id]
    for key in gff_info:
        if gene_id.startswith(key) or key.startswith(gene_id):
            return gff_info[key]
    return {}

def annotate_deg_xlsx(deg_xlsx_path, gff_path):
    gff_info = load_gff_info(gff_path)
    xls = pd.ExcelFile(deg_xlsx_path)
    sheet_names = xls.sheet_names
    dfs = {}
    for sheet in sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet)
        if df.shape[0] == 0:
            dfs[sheet] = df
            continue
        gene_ids = df.index.astype(str) if df.index.name is not None and df.index.name.lower().startswith("gene") else df.iloc[:,0].astype(str)
        name_gff = []
        product_gff = []
        note_gff = []
        for gid in gene_ids:
            info = find_gff_for_gene(gid, gff_info)
            name_gff.append(info.get("Name") if info.get("Name") is not None else "")
            product_gff.append(info.get("Product") if info.get("Product") is not None else "")
            note_gff.append(info.get("Note") if info.get("Note") is not None else "")
        # Decide quais colunas adicionar
        df["Name GFF"] = name_gff
        if any(product_gff):
            df["Product GFF"] = product_gff
        elif any(note_gff):
            df["Note GFF"] = note_gff
        dfs[sheet] = df
    with pd.ExcelWriter(deg_xlsx_path, engine="openpyxl", mode="w") as writer:
        for sheet, df in dfs.items():
            df.to_excel(writer, sheet_name=sheet, index=False)

if __name__ == "__main__":
    # Uso: python annotate_deg_with_gff.py <deg_xlsx_path> <gff_path>
    if len(sys.argv) != 3:
        print("Uso: python annotate_deg_with_gff.py <deg_xlsx_path> <gff_path>")
        sys.exit(1)
    deg_xlsx_path = sys.argv[1]
    gff_path = sys.argv[2]
    annotate_deg_xlsx(deg_xlsx_path, gff_path)
    print("DEG.xlsx anotado com Name GFF e Product GFF.")
