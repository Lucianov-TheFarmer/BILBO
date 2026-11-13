"""Validate and prepare user supplied genomic references."""

from __future__ import annotations

import gzip
import ipaddress
import re
import shutil
import socket
import time
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlsplit

import requests


MAX_TRANSFER = 12 * 1024**3
MAX_UNPACKED = 24 * 1024**3
CHUNK = 8 * 1024**2
NUCLEOTIDES = set("ACGTNRYKMSWBDHVUacgtnrykmswbdhvu")
FASTA_SUFFIXES = (".fa", ".fasta", ".fna")
ANNOTATION_SUFFIXES = (".gff", ".gff3", ".gtf")


def source_format(filename: str, kind: str) -> tuple[str, str]:
    name = Path(filename).name.lower()
    if name != filename.lower():
        raise ValueError("Invalid reference filename")
    compression = ""
    for suffix in (".gz", ".zip"):
        if name.endswith(suffix):
            compression = suffix
            name = name[:-len(suffix)]
            break
    allowed = FASTA_SUFFIXES if kind == "fasta" else ANNOTATION_SUFFIXES
    extension = next((suffix for suffix in allowed if name.endswith(suffix)), None)
    if extension is None:
        raise ValueError(f"Unsupported {kind} file format")
    if kind == "fasta" and re.search(r"(?:^|[._-])(cdna|cds|transcript|protein|pep)(?:[._-]|$)", name):
        raise ValueError("Provide a genomic assembly FASTA, not cDNA, CDS or protein sequences")
    return extension, compression


def validate_public_url(url: str, kind: str) -> str:
    parsed = urlsplit(url.strip())
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError("Use a public HTTPS URL without credentials or a custom port")
    if parsed.fragment:
        raise ValueError("URL fragments are not supported")
    source_format(unquote(Path(parsed.path).name), kind)
    addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError("The URL must resolve only to public addresses")
    return url.strip()


def download_public_file(url: str, target: Path, kind: str, progress) -> None:
    validate_public_url(url, kind)
    with requests.Session() as session:
        session.trust_env = False
        for attempt in range(4):
            offset = target.stat().st_size if target.exists() else 0
            headers = {"Range": f"bytes={offset}-"} if offset else {}
            try:
                with session.get(url, headers=headers, stream=True, allow_redirects=False,
                                 timeout=(30, 120)) as response:
                    if 300 <= response.status_code < 400:
                        raise ValueError("Redirects are not accepted; use the final HTTPS file URL")
                    response.raise_for_status()
                    if offset and response.status_code == 206:
                        content_range = response.headers.get("Content-Range", "")
                        if not content_range.startswith(f"bytes {offset}-"):
                            raise ValueError("The server returned an unexpected byte range")
                    elif offset:
                        # A server may ignore Range. Restart rather than append duplicate data.
                        offset = 0
                    length = int(response.headers.get("Content-Length") or 0)
                    total = offset + length if length else 0
                    if total > MAX_TRANSFER:
                        raise ValueError("Reference file exceeds the 12 GiB transfer limit")
                    written = offset
                    with target.open("ab" if offset else "wb") as output:
                        for chunk in response.iter_content(CHUNK):
                            if not chunk:
                                continue
                            written += len(chunk)
                            if written > MAX_TRANSFER:
                                raise ValueError("Reference file exceeds the 12 GiB transfer limit")
                            output.write(chunk)
                            progress(kind, written, total)
                    if total and written != total:
                        raise requests.exceptions.ChunkedEncodingError("Incomplete reference download")
                    return
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout,
                    requests.exceptions.ChunkedEncodingError, requests.exceptions.HTTPError) as exc:
                retryable_http = (isinstance(exc, requests.exceptions.HTTPError)
                                  and exc.response is not None
                                  and exc.response.status_code in (429, 500, 502, 503, 504))
                if attempt == 3 or (isinstance(exc, requests.exceptions.HTTPError) and not retryable_http):
                    raise
                time.sleep(min(2 ** attempt, 4))


def materialize(source: Path, destination: Path, kind: str) -> str:
    extension, compression = source_format(source.name, kind)
    if compression == ".zip":
        with zipfile.ZipFile(source) as archive:
            members = []
            for info in archive.infolist():
                if info.is_dir() or Path(info.filename).name.startswith("."):
                    continue
                try:
                    inner_extension, inner_compression = source_format(Path(info.filename).name, kind)
                except ValueError:
                    continue  # README and archive metadata are not reference data.
                if inner_compression:
                    raise ValueError("ZIP must contain uncompressed reference files")
                if info.flag_bits & 1 or (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("Encrypted files and links are not accepted in reference ZIPs")
                members.append(info)
            if not members or (kind == "annotation" and len(members) != 1):
                raise ValueError("ZIP must contain reference FASTA or one annotation file")
            if sum(info.file_size for info in members) > MAX_UNPACKED:
                raise ValueError("Unpacked reference exceeds 24 GiB")
            with destination.open("wb") as output:
                for info in members:
                    with archive.open(info) as stream:
                        _copy_limited(stream, output)
                    if kind == "fasta":
                        output.write(b"\n")
            if kind == "annotation":
                extension = source_format(Path(members[0].filename).name, kind)[0]
    elif compression == ".gz":
        with gzip.open(source, "rb") as stream, destination.open("wb") as output:
            _copy_limited(stream, output)
    else:
        if source.stat().st_size > MAX_UNPACKED:
            raise ValueError("Reference file exceeds the 24 GiB unpacked limit")
        shutil.copyfile(source, destination)
    return extension


def _copy_limited(source, target) -> None:
    written = 0
    while True:
        chunk = source.read(CHUNK)
        if not chunk:
            return
        written += len(chunk)
        if written > MAX_UNPACKED:
            raise ValueError("Unpacked reference exceeds 24 GiB")
        target.write(chunk)


def validate_fasta(path: Path) -> set[str]:
    identifiers: set[str] = set()
    current = None
    seen_sequence = False
    with path.open("rt", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            if line.startswith(">"):
                if current is not None and not seen_sequence:
                    raise ValueError(f"FASTA sequence {current} is empty")
                current = line[1:].split()[0] if line[1:].split() else ""
                if not current or current in identifiers:
                    raise ValueError("FASTA sequence identifiers must be unique and nonempty")
                identifiers.add(current)
                seen_sequence = False
            else:
                if current is None or any(base not in NUCLEOTIDES for base in line):
                    raise ValueError("Invalid genomic FASTA sequence")
                seen_sequence = True
    if not identifiers or not seen_sequence:
        raise ValueError("Genomic FASTA is empty")
    return identifiers


def validate_annotation(path: Path, fasta_ids: set[str], extension: str) -> None:
    genes = transcripts = exons = 0
    with path.open("rt", encoding="utf-8") as handle:
        for raw in handle:
            if not raw.strip() or raw.startswith("#"):
                continue
            fields = raw.rstrip("\n\r").split("\t")
            if len(fields) != 9 or fields[0] not in fasta_ids:
                raise ValueError("Annotation must have nine columns and sequence IDs matching the FASTA")
            try:
                start, end = int(fields[3]), int(fields[4])
            except ValueError as exc:
                raise ValueError("Annotation coordinates must be integers") from exc
            if start < 1 or end < start:
                raise ValueError("Invalid annotation coordinates")
            if fields[2] == "gene":
                genes += 1
            elif fields[2] in ("mRNA", "transcript"):
                transcripts += 1
            elif fields[2] == "exon":
                exons += 1
                if extension == ".gtf" and not (re.search(r'gene_id\s+"[^"]+"', fields[8]) and re.search(r'transcript_id\s+"[^"]+"', fields[8])):
                    raise ValueError("GTF exons require gene_id and transcript_id")
    if not exons:
        raise ValueError("Annotation must contain exon features for STAR")
    if not genes and not transcripts and extension != ".gtf":
        raise ValueError("GFF3 annotation must contain gene or transcript features")


def gff3_to_star_gtf(source: Path, target: Path) -> None:
    transcripts: dict[str, str] = {}
    with source.open("rt", encoding="utf-8") as handle:
        for raw in handle:
            fields = raw.rstrip("\n\r").split("\t")
            if len(fields) != 9 or fields[2] not in ("mRNA", "transcript"):
                continue
            attrs = _gff_attributes(fields[8])
            if attrs.get("ID"):
                transcript_id = attrs["ID"]
                # Some valid GFF3 files, including Beauregard v1, omit gene rows.
                # Their transcript IDs carry the gene ID before the isoform suffix.
                gene_id = attrs.get("Parent", "").split(",")[0]
                transcripts[transcript_id] = gene_id or re.sub(r"\.\d+$", "", transcript_id)
    written = 0
    with source.open("rt", encoding="utf-8") as handle, target.open("wt", encoding="utf-8") as output:
        for raw in handle:
            fields = raw.rstrip("\n\r").split("\t")
            if len(fields) != 9 or fields[2] != "exon":
                continue
            attrs = _gff_attributes(fields[8])
            for transcript in attrs.get("Parent", "").split(","):
                gene = transcripts.get(transcript)
                if gene:
                    if any(char in gene + transcript for char in ('"', '\n', '\r', '\t', '\\')):
                        raise ValueError("Unsupported GFF3 gene or transcript identifier")
                    fields[8] = f'gene_id "{gene}"; transcript_id "{transcript}";'
                    output.write("\t".join(fields) + "\n")
                    written += 1
    if not written:
        raise ValueError("GFF3 exons must link to transcripts and genes through Parent attributes")


def _gff_attributes(value: str) -> dict[str, str]:
    return {key: unquote(item) for part in value.split(";") if "=" in part for key, item in [part.split("=", 1)]}
