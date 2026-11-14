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


def load_protein_sequences(path):
    sequences = {}
    identifier = None
    with Path(path).open(encoding="utf-8") as stream:
        for line in stream:
            if line.startswith(">"):
                identifier = line[1:].split()[0]
                sequences[identifier] = []
            elif identifier is not None:
                sequences[identifier].append(line.strip())
    return {identifier: "".join(lines) for identifier, lines in sequences.items()}


def select_hits(path, metadata, min_identity, min_coverage, max_evalue):
    """Choose the strongest qualifying hit carrying GO; score order is DIAMOND's."""
    best = {}
    aligned = set()
    qualified_without_go = set()
    with Path(path).open(encoding="utf-8") as stream:
        for row in csv.reader(stream, delimiter="\t"):
            query, subject, identity, qstart, qend, qlen, evalue, bitscore = row
            aligned.add(query)
            accession = subject.split("|")[1] if "|" in subject else subject
            source = metadata.get(accession)
            if query in best or not source:
                continue
            coverage = (abs(int(qend) - int(qstart)) + 1) / int(qlen)
            if (float(identity) < min_identity or coverage < min_coverage
                    or float(evalue) > max_evalue):
                continue
            if not any(source.get(field, "").strip() for field in GO_FIELDS.values()):
                qualified_without_go.add(query)
                continue
            best[query] = {
                "accession": accession,
                "identity": float(identity),
                "coverage": coverage,
                "evalue": float(evalue),
                "bitscore": float(bitscore),
                "source": source,
            }
    return best, aligned, qualified_without_go


def annotate(input_book, output_book, hits, aligned, qualified_without_go,
             sequences, extraction, thresholds, database_release):
    if Path(input_book).resolve() == Path(output_book).resolve():
        raise ValueError("Output workbook must differ from input workbook")
    sheets = pd.read_excel(input_book, sheet_name=None)
    total = annotated = over_excel_limit = missing_sequences = 0
    statuses = {"existing_go": 0, "no_sequence": 0, "no_alignment": 0, "below_threshold": 0,
                "homologue_without_go": 0, "go_inferred": 0}
    with pd.ExcelWriter(output_book, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            if frame.empty:
                frame.to_excel(writer, sheet_name=name, index=False)
                continue
            ids = frame.iloc[:, 0].astype(str).str.strip()
            total += len(ids)
            for col in [*GO_FIELDS, "Uniprot gene names", "Uniprot protein name", "Uniprot Function",
                        "Uniprot function source",
                        "Uniprot organism", "GO evidence", "Protein sequence",
                        "Protein length (aa)", "Protein source ID", "Homology status", "Homology accession",
                        "Homology identity (%)", "Homology query coverage (%)",
                        "Homology e-value", "Homology database"]:
                if col not in frame:
                    frame[col] = ""
                frame[col] = frame[col].astype(object)
            for index, identifier in ids.items():
                sequence = sequences.get(identifier, "")
                if not sequence:
                    missing_sequences += 1
                frame.at[index, "Protein length (aa)"] = len(sequence)
                frame.at[index, "Protein source ID"] = extraction["source_ids"].get(identifier, "")
                if len(sequence) > 32767:
                    over_excel_limit += 1
                frame.at[index, "Protein sequence"] = (
                    sequence if len(sequence) <= 32767 else "See homology/DEG_proteins.fasta")
                if any("GO:" in str(frame.at[index, column]) for column in GO_FIELDS):
                    frame.at[index, "Homology status"] = "existing_go"
                    statuses["existing_go"] += 1
                    annotated += 1
                    continue
                hit = hits.get(identifier)
                if not hit:
                    status = ("no_sequence" if not sequence else
                              "no_alignment" if identifier not in aligned else
                              "homologue_without_go" if identifier in qualified_without_go
                              else "below_threshold")
                    frame.at[index, "Homology status"] = status
                    statuses[status] += 1
                    continue
                source = hit["source"]
                for target, field in GO_FIELDS.items():
                    frame.at[index, target] = source.get(field, "")
                frame.at[index, "Uniprot gene names"] = source.get("Gene Names", "")
                frame.at[index, "Uniprot protein name"] = source.get("Protein names", "")
                function_comment = source.get("Function [CC]", "").strip()
                frame.at[index, "Uniprot Function"] = function_comment or source.get("Protein names", "")
                frame.at[index, "Uniprot function source"] = (
                    "UniProt FUNCTION comment" if function_comment else "Protein name fallback")
                frame.at[index, "Uniprot organism"] = source.get("Organism", "")
                frame.at[index, "GO evidence"] = "Inferred from protein sequence homology"
                frame.at[index, "Homology status"] = "go_inferred"
                frame.at[index, "Homology accession"] = hit["accession"]
                frame.at[index, "Homology identity (%)"] = hit["identity"]
                frame.at[index, "Homology query coverage (%)"] = round(hit["coverage"] * 100, 2)
                frame.at[index, "Homology e-value"] = hit["evalue"]
                frame.at[index, "Homology database"] = (
                    "UniProtKB/Swiss-Prot Viridiplantae " + database_release)
                annotated += 1
                statuses["go_inferred"] += 1
            frame.to_excel(writer, sheet_name=name, index=False)
    return {"rows": total, "go_annotated": annotated,
            "sequences_over_excel_cell_limit": over_excel_limit,
            "sequences_missing": missing_sequences,
            "homology_statuses": statuses,
            "proteins": {key: value for key, value in extraction.items()
                         if key != "source_ids"},
            "database_release": database_release,
            "thresholds": thresholds, "output": str(output_book)}


def run(args):
    work = Path(args.work_dir)
    work.mkdir(parents=True, exist_ok=True)
    peptides = work / "DEG_proteins.fasta"
    extraction = extract(Path(args.workbook), Path(args.proteins), peptides,
                         Path(args.gff) if args.gff else None)
    if not extraction["found"]:
        raise ValueError("No DEG IDs matched the reference protein FASTA")
    sequences = load_protein_sequences(peptides)
    hits_file = work / "diamond_hits.tsv"
    subprocess.run([args.diamond, "blastp", "--query", str(peptides),
                    "--db", args.database, "--out", str(hits_file),
                    "--outfmt", "6", "qseqid", "sseqid", "pident", "qstart",
                    "qend", "qlen", "evalue", "bitscore",
                    "--max-target-seqs", "5", "--threads", str(args.threads)], check=True)
    metadata = load_uniprot_metadata(args.metadata)
    hits, aligned, qualified_without_go = select_hits(
        hits_file, metadata, args.min_identity, args.min_coverage, args.max_evalue)
    thresholds = {"identity_percent": args.min_identity,
                  "query_coverage": args.min_coverage, "max_evalue": args.max_evalue}
    manifest = Path(args.metadata).with_name("viridiplantae_reviewed_manifest.json")
    database_release = (json.loads(manifest.read_text(encoding="utf-8")).get("release", "release unknown")
                        if manifest.is_file() else "release unknown")
    result = annotate(args.workbook, args.output, hits, aligned, qualified_without_go,
                      sequences, extraction, thresholds, database_release)
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
    parser.add_argument("--gff")
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--min-identity", type=float, default=40)
    parser.add_argument("--min-coverage", type=float, default=0.7)
    parser.add_argument("--max-evalue", type=float, default=1e-10)
    print(json.dumps(run(parser.parse_args()), ensure_ascii=False))
