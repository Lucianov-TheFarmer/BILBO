import os
import sys
import re
import pandas as pd

def parse_gff_attributes(attr_str):
    """Parse attribute field from GFF or GTF lines into a dict.

    Supports both GFF (key=value;key2=value2) and GTF (key "value"; key2 "value2";) formats.
    """
    attrs = {}
    if not attr_str:
        return attrs
    # Split by semicolon but be robust to trailing/leading spaces
    parts = [p.strip() for p in attr_str.split(";") if p.strip()]
    for item in parts:
        # GFF style: key=value
        if "=" in item:
            key, val = item.split("=", 1)
            attrs[key.strip()] = val.strip().strip('"')
            continue
        # GTF style: key "value" (possibly with trailing semicolon already removed)
        m = re.match(r'^(\S+)\s+"([^"]+)"', item)
        if m:
            key = m.group(1)
            val = m.group(2)
            attrs[key.strip()] = val.strip()
            continue
        # Fallback: split by whitespace
        parts_ws = item.split()
        if len(parts_ws) >= 2:
            attrs[parts_ws[0].strip()] = parts_ws[1].strip().strip('"')
    return attrs


def normalize_id(x):
    """Normalize gene/transcript IDs for robust matching.

    Steps:
    - convert to string and strip
    - remove common leading prefixes like 'gene-', 'rna-', 'cds-', 'id-'
    - remove non-alphanumeric characters (underscores, dashes, colons, etc.)
    - uppercase for consistent comparison
    """
    if x is None:
        return ""
    s = str(x).strip()
    # remove common leading prefixes (e.g. gene-, rna-, cds-, id-)
    s = re.sub(r'^[A-Za-z]+[-_:]', '', s)
    # remove any non-alphanumeric characters
    s = re.sub(r'[^A-Za-z0-9]', '', s)
    return s.upper()

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
                # Normalize common attribute key names across GFF and GTF
                gene_id = attrs.get("ID") or attrs.get("gene_id") or attrs.get("GeneID") or attrs.get("gene")
                # Prefer explicit Name, then gene, then gene_id as display name
                name = attrs.get("Name") or attrs.get("gene") or attrs.get("gene_name") or None
                # Product/note can appear under several keys
                product = attrs.get("Product") or attrs.get("product") or attrs.get("product_name") or attrs.get("description")
                note = attrs.get("Note") or attrs.get("note") or attrs.get("description")
                if gene_id:
                    # store using normalized ID for robust matching
                    norm = normalize_id(gene_id)
                    # prefer first occurrence if duplicates
                    if norm not in gff_info:
                        gff_info[norm] = {
                            "Name": name,
                            "Product": product,
                            "Note": note
                        }
    return gff_info

def find_gff_for_gene(gene_id, gff_info):
    # Always normalize the incoming gene_id and lookup directly
    norm = normalize_id(gene_id)
    return gff_info.get(norm, {})

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

        # Save processed dataframe for this sheet
        dfs[sheet] = df
        # Progress indicator for long runs
        print(f"[INFO] Finished GFF annotation for sheet: {sheet}")
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
