"""Select proteins whose transcript IDs appear in a DEG workbook."""

import argparse
import json
import zipfile
from contextlib import contextmanager
from pathlib import Path

import openpyxl


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
    else:
        with path.open(encoding="utf-8") as stream:
            yield stream


def extract(workbook: Path, source: Path, output: Path) -> dict:
    wanted = deg_ids(workbook)
    found = set()
    output.parent.mkdir(parents=True, exist_ok=True)
    with fasta_stream(source) as lines, output.open("w", encoding="utf-8") as target:
        selected = False
        for line in lines:
            if line.startswith(">"):
                identifier = line[1:].split(maxsplit=1)[0]
                selected = identifier in wanted and identifier not in found
                if selected:
                    found.add(identifier)
            if selected:
                target.write(line)
    return {"requested": len(wanted), "found": len(found),
            "missing": sorted(wanted - found), "output": str(output)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path)
    parser.add_argument("protein_fasta", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(extract(args.workbook, args.protein_fasta, args.output)))
