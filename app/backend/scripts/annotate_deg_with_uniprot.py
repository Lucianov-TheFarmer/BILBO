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

def annotate_deg_with_uniprot(deg_xlsx_path, write_path=None):
    """
    Annotate all sheets in the workbook using UniProt and write the updated workbook in a single operation.

    Parameters:
    - deg_xlsx_path: path to original DEG.xlsx
    - write_path: optional path to write updated workbook. If None, overwrites deg_xlsx_path.
    """
    try:
        sheets = pd.read_excel(deg_xlsx_path, sheet_name=None)
    except Exception as e:
        print(f"[WARN] Could not open Excel file '{deg_xlsx_path}': {e}")
        return

    updated = {}
    # cache results across the entire workbook to avoid duplicate UniProt queries
    uniprot_cache = {}

    try:
        for sheet, df in sheets.items():
            # Ensure df is a DataFrame
            if df is None or df.shape[0] == 0:
                updated[sheet] = df
                continue

            # Determine query column: prefer Note/Product/Name GFF if they contain any non-empty values.
            query_col = None
            def col_has_value(c):
                # treat empty strings as missing by stripping and replacing with NA
                return (c in df.columns) and (df[c].astype(str).str.strip().replace('', pd.NA).notna().any())

            if col_has_value("Note GFF"):
                query_col = "Note GFF"
            elif col_has_value("Product GFF"):
                query_col = "Product GFF"
            elif col_has_value("Name GFF"):
                query_col = "Name GFF"
            else:
                # fallback to the first column (commonly the gene ID column like 'Unnamed: 0')
                first_col = df.columns[0]
                print(f"[INFO] No GFF columns with values found in sheet '{sheet}', falling back to first column '{first_col}' for queries.")
                query_col = first_col

            # Prepare target columns
            for col in [
                "Uniprot organism", "Uniprot gene names",
                "Uniprot CC", "Uniprot MF", "Uniprot BP", "Uniprot Function"
            ]:
                if col not in df.columns:
                    df[col] = ""
                df[col] = df[col].astype("object")

            count = 0
            for idx, row in df.iterrows():
                query_value = str(row[query_col]).strip()
                if not query_value or query_value == "nan":
                    continue
                # reuse cached result when available
                if query_value in uniprot_cache:
                    info = uniprot_cache[query_value]
                else:
                    if count < 5:
                        print(f"\n[DEBUG] Querying Uniprot for: '{query_value}'")
                    info = fetch_uniprot_info(query_value)
                    uniprot_cache[query_value] = info
                    if count < 5:
                        print(f"[DEBUG] Result: {info}")
                    # be polite with UniProt; small delay
                    time.sleep(0.2)
                for col in info:
                    df.at[idx, col] = str(info[col]) if info[col] is not None else ""
                count += 1

            updated[sheet] = df
            # Progress indicator for long runs
            print(f"[INFO] Finished UniProt annotation for sheet: {sheet}")
    except KeyboardInterrupt:
        print("[WARN] UniProt annotation interrupted by user (KeyboardInterrupt). Writing partial results...")
    except Exception as e:
        print(f"[WARN] Error during UniProt annotation: {e}. Writing partial results...")

    # Write all sheets at once to avoid multiple append writes
    out_path = write_path if write_path is not None else deg_xlsx_path
    if not updated:
        print(f"[WARN] Nothing was updated; skipping write to '{out_path}'")
        return
    try:
        with pd.ExcelWriter(out_path, engine="openpyxl", mode="w") as writer:
            # write each original sheet, replacing with updated version when available
            for sheet, original_df in sheets.items():
                df_to_write = updated.get(sheet, original_df)
                if df_to_write is None:
                    import pandas as _pd
                    _pd.DataFrame().to_excel(writer, sheet_name=sheet, index=False)
                else:
                    df_to_write.to_excel(writer, sheet_name=sheet, index=False)
    except Exception as e:
        print(f"[WARN] Failed to write updated workbook to '{out_path}': {e}")
        return

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python annotate_deg_with_uniprot.py <deg_xlsx_path>")
        sys.exit(1)
    deg_xlsx_path = sys.argv[1]
    annotate_deg_with_uniprot(deg_xlsx_path)
    print("DEG.xlsx anotado com informações do Uniprot.")
