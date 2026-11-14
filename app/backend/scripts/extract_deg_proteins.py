"""Select one protein per DEG ID, resolving gene IDs through GFF transcripts."""

import argparse
import gzip
import json
import zipfile
from contextlib import contextmanager
from pathlib import Path

import openpyxl

from annotate_deg_with_gff import parse_gff_attributes


def deg_ids(workbook: Path) -> set[str]:
    book = openpyxl.load_workbook(workbook, read_only=True, data_only=True)
    ids = set()
    try:
        for sheet in book:
            for row in sheet.iter_rows(min_row=2, min_col=1, max_col=1, values_only=True):
                if row[0] is not None:
                    ids.add(str(row[0]).strip())
    finally:
        book.close()
    return ids - {""}


@contextmanager
def fasta_stream(path: Path):
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            members = [item for item in archive.infolist()
                       if not item.is_dir() and item.filename.lower().endswith(
                           (".fa", ".faa", ".fasta", ".pep"))]
            if len(members) != 1:
                raise ValueError("Expected exactly one protein FASTA in the ZIP archive")
            with archive.open(members[0]) as stream:
                yield (line.decode("utf-8", errors="replace") for line in stream)
    elif path.suffix.lower() == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            yield stream
    else:
        with path.open(encoding="utf-8") as stream:
            yield stream


def _aliases(identifier: str) -> set[str]:
    return {identifier, identifier.removeprefix("gene-"),
            identifier.removeprefix("rna-"), identifier.removeprefix("transcript-")}


def _protein_candidates(gff: Path, wanted: set[str]) -> dict[str, set[str]]:
    """Map transcript and protein IDs to the DEG gene IDs they represent."""
    lookup: dict[str, set[str]] = {}
    for gene in wanted:
        for alias in _aliases(gene):
            lookup.setdefault(alias, set()).add(gene)
    transcripts: dict[str, set[str]] = {}
    with gff.open(encoding="utf-8") as stream:
        for line in stream:
            if line.startswith("#"):
                continue
            fields = line.rstrip("\n\r").split("\t")
            if len(fields) < 9 or fields[2].lower() not in ("mrna", "transcript"):
                continue
            attributes = parse_gff_attributes(fields[8])
            transcript = attributes.get("ID") or attributes.get("transcript_id")
            parents = (attributes.get("Parent") or attributes.get("gene_id") or "").split(",")
            genes = set()
            for parent in parents:
                matches = ({parent} if parent in wanted else
                           set().union(*(lookup.get(alias, set()) for alias in _aliases(parent))))
                if len(matches) == 1:
                    genes.update(matches)
            if transcript and genes:
                transcripts.setdefault(transcript, set()).update(genes)
    candidates = {transcript: set(genes) for transcript, genes in transcripts.items()}
    if transcripts:
        with gff.open(encoding="utf-8") as stream:
            for line in stream:
                if line.startswith("#"):
                    continue
                fields = line.rstrip("\n\r").split("\t")
                if len(fields) < 9 or fields[2].lower() != "cds":
                    continue
                attributes = parse_gff_attributes(fields[8])
                protein = attributes.get("protein_id") or attributes.get("proteinId")
                if not protein:
                    continue
                parents = (attributes.get("Parent") or attributes.get("transcript_id") or "").split(",")
                for parent in parents:
                    if parent in transcripts:
                        candidates.setdefault(protein, set()).update(transcripts[parent])
    return candidates


def extract(workbook: Path, source: Path, output: Path, gff: Path = None) -> dict:
    wanted = deg_ids(workbook)
    candidates = _protein_candidates(gff, wanted) if gff else {}
    selected: dict[str, tuple[str, str, bool]] = {}
    output.parent.mkdir(parents=True, exist_ok=True)
    with fasta_stream(source) as lines:
        identifier = None
        chunks = []

        def finish_record():
            if not identifier or not chunks:
                return
            sequence = "".join(chunks)
            genes = candidates.get(identifier, set()) | ({identifier} if identifier in wanted else set())
            for gene in genes:
                direct = gene == identifier
                previous = selected.get(gene)
                if (previous is None or (direct and not previous[2]) or
                        (direct == previous[2] and len(sequence) > len(previous[1]))):
                    selected[gene] = (identifier, sequence, direct)

        for line in lines:
            if line.startswith(">"):
                finish_record()
                identifier = line[1:].split(maxsplit=1)[0]
                chunks = []
            elif identifier in candidates or identifier in wanted:
                chunks.append(line.strip())
        finish_record()
    with output.open("w", encoding="utf-8") as target:
        for gene in sorted(selected):
            source_id, sequence, _ = selected[gene]
            target.write(f">{gene} source={source_id}\n")
            for offset in range(0, len(sequence), 80):
                target.write(sequence[offset:offset + 80] + "\n")
    return {"requested": len(wanted), "found": len(selected),
            "missing": sorted(wanted - selected.keys()),
            "source_ids": {gene: value[0] for gene, value in selected.items()},
            "output": str(output)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path)
    parser.add_argument("protein_fasta", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--gff", type=Path)
    args = parser.parse_args()
    result = extract(args.workbook, args.protein_fasta, args.output, args.gff)
    print(json.dumps({key: value for key, value in result.items() if key != "source_ids"}))
