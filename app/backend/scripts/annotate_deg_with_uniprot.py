import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

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

def _build_session():
    session = requests.Session()
    retries = Retry(total=4, connect=4, read=4, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries, pool_connections=20, pool_maxsize=20)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def fetch_uniprot_info(query, session):
    url = (
        "https://rest.uniprot.org/uniprotkb/search"
        f"?query={requests.utils.quote(query)}"
        "&fields=organism_name&fields=lineage&fields=gene_names&fields=id"
        "&fields=go_p&fields=go_f&fields=go_c&fields=cc_function"
        "&format=tsv"
    )
    try:
        resp = session.get(url, timeout=10)
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
    uniprot_cache = {}
    session = _build_session()

    try:
        all_queries = set()
        sheet_query_map = {}
        for sheet, df in sheets.items():
            if df is None or df.shape[0] == 0:
                sheet_query_map[sheet] = (df, None)
                continue
            query_col = None

            def col_has_value(c):
                return (c in df.columns) and (df[c].astype(str).str.strip().replace('', pd.NA).notna().any())

            if col_has_value("Note GFF"):
                query_col = "Note GFF"
            elif col_has_value("Product GFF"):
                query_col = "Product GFF"
            elif col_has_value("Name GFF"):
                query_col = "Name GFF"
            else:
                query_col = df.columns[0]
                print(f"[INFO] No GFF columns with values found in sheet '{sheet}', falling back to first column '{query_col}' for queries.")

            sheet_query_map[sheet] = (df, query_col)
            values = (
                df[query_col]
                .astype(str)
                .str.strip()
                .replace("nan", "")
                .replace("", pd.NA)
                .dropna()
                .unique()
                .tolist()
            )
            all_queries.update(values)

        if all_queries:
            print(f"[INFO] Fetching UniProt annotations for {len(all_queries)} unique queries...")

            def _worker(q):
                return q, fetch_uniprot_info(q, session)

            with ThreadPoolExecutor(max_workers=6) as executor:
                futures = [executor.submit(_worker, q) for q in all_queries]
                for future in as_completed(futures):
                    q, info = future.result()
                    uniprot_cache[q] = info

        for sheet, df in sheets.items():
            # Ensure df is a DataFrame
            if df is None or df.shape[0] == 0:
                updated[sheet] = df
                continue

            query_col = sheet_query_map[sheet][1]

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
                info = uniprot_cache.get(query_value, {})
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
