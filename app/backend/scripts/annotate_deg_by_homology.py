"""Annotate DEG proteins with GO from a reviewed plant UniProt homologue.

The GO terms are computationally inferred; the source accession and alignment
statistics are retained for review. The input workbook is never overwritten.
"""

import argparse
import csv
import gzip
import json
import subprocess
from pathlib import Path

import pandas as pd

from extract_deg_proteins import extract


GO_FIELDS = {
    "Uniprot BP": "Gene Ontology (biological process)",
    "Uniprot MF": "Gene Ontology (molecular function)",
    "Uniprot CC": "Gene Ontology (cellular component)",
}


def load_uniprot_metadata(path):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as stream:
        return {row["Entry"]: row for row in csv.DictReader(stream, delimiter="\t")}


def select_hits(path, metadata, min_identity, min_coverage, max_evalue):
    """Choose the strongest qualifying hit carrying GO; score order is DIAMOND's."""
    best = {}
    with Path(path).open(encoding="utf-8") as stream:
        for row in csv.reader(stream, delimiter="\t"):
            query, subject, identity, qstart, qend, qlen, evalue, bitscore = row
            accession = subject.split("|")[1] if "|" in subject else subject
            source = metadata.get(accession)
            if query in best or not source:
                continue
            coverage = (abs(int(qend) - int(qstart)) + 1) / int(qlen)
            if (float(identity) < min_identity or coverage < min_coverage
                    or float(evalue) > max_evalue):
                continue
            if not any(source.get(field, "").strip() for field in GO_FIELDS.values()):
                continue
            best[query] = {
                "accession": accession,
                "identity": float(identity),
                "coverage": coverage,
                "evalue": float(evalue),
                "bitscore": float(bitscore),
                "source": source,
            }
    return best


def annotate(input_book, output_book, hits, extraction, thresholds, database_release):
    if Path(input_book).resolve() == Path(output_book).resolve():
        raise ValueError("Output workbook must differ from input workbook")
    sheets = pd.read_excel(input_book, sheet_name=None)
    total = annotated = 0
    with pd.ExcelWriter(output_book, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            if frame.empty:
                frame.to_excel(writer, sheet_name=name, index=False)
                continue
            ids = frame.iloc[:, 0].astype(str).str.strip()
            total += len(ids)
            for col in [*GO_FIELDS, "Uniprot gene names", "Uniprot Function",
                        "Uniprot organism", "GO evidence", "GO source accession",
                        "GO identity (%)", "GO query coverage (%)", "GO e-value",
                        "GO source database"]:
                if col not in frame:
                    frame[col] = ""
                frame[col] = frame[col].astype(object)
            for index, identifier in ids.items():
                hit = hits.get(identifier)
                if not hit:
                    continue
                source = hit["source"]
                for target, field in GO_FIELDS.items():
                    frame.at[index, target] = source.get(field, "")
                frame.at[index, "Uniprot gene names"] = source.get("Gene Names", "")
                frame.at[index, "Uniprot Function"] = source.get("Protein names", "")
                frame.at[index, "Uniprot organism"] = source.get("Organism", "")
                frame.at[index, "GO evidence"] = "Inferred from protein sequence homology"
                frame.at[index, "GO source accession"] = hit["accession"]
                frame.at[index, "GO identity (%)"] = hit["identity"]
                frame.at[index, "GO query coverage (%)"] = round(hit["coverage"] * 100, 2)
                frame.at[index, "GO e-value"] = hit["evalue"]
                frame.at[index, "GO source database"] = (
                    "UniProtKB/Swiss-Prot Viridiplantae " + database_release)
                annotated += 1
            frame.to_excel(writer, sheet_name=name, index=False)
    return {"rows": total, "go_annotated": annotated, "proteins": extraction,
            "database_release": database_release,
            "thresholds": thresholds, "output": str(output_book)}


def run(args):
    work = Path(args.work_dir)
    work.mkdir(parents=True, exist_ok=True)
    peptides = work / "DEG_proteins.fasta"
    extraction = extract(Path(args.workbook), Path(args.proteins), peptides)
    if not extraction["found"]:
        raise ValueError("No DEG IDs matched the reference protein FASTA")
    hits_file = work / "diamond_hits.tsv"
    subprocess.run([args.diamond, "blastp", "--query", str(peptides),
                    "--db", args.database, "--out", str(hits_file),
                    "--outfmt", "6", "qseqid", "sseqid", "pident", "qstart",
                    "qend", "qlen", "evalue", "bitscore",
                    "--max-target-seqs", "5", "--threads", str(args.threads)], check=True)
    metadata = load_uniprot_metadata(args.metadata)
    hits = select_hits(hits_file, metadata, args.min_identity,
                       args.min_coverage, args.max_evalue)
    thresholds = {"identity_percent": args.min_identity,
                  "query_coverage": args.min_coverage, "max_evalue": args.max_evalue}
    manifest = Path(args.metadata).with_name("viridiplantae_reviewed_manifest.json")
    database_release = (json.loads(manifest.read_text(encoding="utf-8")).get("release", "release unknown")
                        if manifest.is_file() else "release unknown")
    result = annotate(args.workbook, args.output, hits, extraction, thresholds, database_release)
    (work / "homology_summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook")
    parser.add_argument("proteins")
    parser.add_argument("database")
    parser.add_argument("metadata")
    parser.add_argument("output")
    parser.add_argument("work_dir")
    parser.add_argument("--diamond", default="diamond")
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--min-identity", type=float, default=40)
    parser.add_argument("--min-coverage", type=float, default=0.7)
    parser.add_argument("--max-evalue", type=float, default=1e-10)
    print(json.dumps(run(parser.parse_args()), ensure_ascii=False))
