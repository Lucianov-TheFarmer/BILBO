"""Cache a versioned reviewed-plant UniProt database for DIAMOND annotation."""

import argparse
import fcntl
import gzip
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import requests


QUERY = "(taxonomy_id:33090) AND (reviewed:true)"
FIELDS = "accession,protein_name,gene_names,organism_name,cc_function,go_p,go_f,go_c"
BASE = "https://rest.uniprot.org/uniprotkb/stream"


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def valid_snapshot(db, tsv, manifest):
    if not all(path.is_file() and path.stat().st_size for path in (db, tsv, manifest)):
        return None
    try:
        info = json.loads(manifest.read_text(encoding="utf-8"))
        if (info.get("fields") == FIELDS
                and info.get("database_sha256") == sha256(db)
                and info.get("metadata_sha256") == sha256(tsv)):
            return info
    except (OSError, ValueError):
        pass
    return None


def download(session, destination, fmt, fields=None):
    params = {"compressed": "true", "format": fmt, "query": QUERY}
    if fields:
        params["fields"] = fields
    with session.get(BASE, params=params, stream=True, timeout=(30, 300)) as response:
        response.raise_for_status()
        release = response.headers.get("X-UniProt-Release")
        if not release:
            raise RuntimeError("UniProt response did not identify its release")
        with destination.open("wb") as output:
            for chunk in response.iter_content(1024 * 1024):
                if chunk:
                    output.write(chunk)
    if destination.stat().st_size < 1000:
        raise RuntimeError("UniProt database download is unexpectedly small")
    return release


def ensure_database(directory, diamond):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    db = directory / "viridiplantae_reviewed.dmnd"
    tsv = directory / "viridiplantae_reviewed.tsv.gz"
    manifest = directory / "viridiplantae_reviewed_manifest.json"
    with (directory / ".go_database.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        cached = valid_snapshot(db, tsv, manifest)
        if cached is not None:
            return cached
        with tempfile.TemporaryDirectory(prefix="go_reference_", dir=directory) as temp:
            staging = Path(temp)
            fasta_gz = staging / "proteins.fasta.gz"
            tsv_gz = staging / "metadata.tsv.gz"
            with requests.Session() as session:
                session.headers["User-Agent"] = "BILBO/GO-homology"
                release_fasta = download(session, fasta_gz, "fasta")
                release_tsv = download(session, tsv_gz, "tsv", FIELDS)
            if release_fasta != release_tsv:
                raise RuntimeError("UniProt release changed during database download")
            fasta = staging / "proteins.fasta"
            with gzip.open(fasta_gz, "rb") as source, fasta.open("wb") as target:
                shutil.copyfileobj(source, target)
            staged_db = staging / "viridiplantae_reviewed.dmnd"
            subprocess.run([str(diamond), "makedb", "--in", str(fasta),
                            "--db", str(staged_db)], check=True,
                           stdout=subprocess.DEVNULL)
            with gzip.open(tsv_gz, "rt", encoding="utf-8") as table:
                header = table.readline().strip().split("\t")
                if not {"Entry", "Function [CC]", "Gene Ontology (biological process)",
                        "Gene Ontology (molecular function)",
                        "Gene Ontology (cellular component)"}.issubset(header):
                    raise RuntimeError("UniProt metadata columns are incomplete")
            info = {"database": "UniProtKB/Swiss-Prot Viridiplantae",
                    "query": QUERY, "fields": FIELDS, "release": release_fasta, "source": BASE,
                    "database_sha256": sha256(staged_db),
                    "metadata_sha256": sha256(tsv_gz)}
            staged_db.replace(db)
            tsv_gz.replace(tsv)
            manifest.write_text(json.dumps(info, indent=2), encoding="utf-8")
            return info


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("diamond", type=Path)
    args = parser.parse_args()
    print(json.dumps(ensure_database(args.directory, args.diamond)))
