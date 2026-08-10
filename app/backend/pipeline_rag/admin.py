from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

from .common import BM25_METADATA_PATH, COLLECTION_NAME, QDRANT_API_KEY, QDRANT_URL

DEFAULT_EXPORT_DIR = Path("/rag/exports")
MANIFEST_NAME = "manifest.json"


def _headers() -> dict[str, str]:
    return {"api-key": QDRANT_API_KEY} if QDRANT_API_KEY else {}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _endpoint(path: str, qdrant_url: str = QDRANT_URL) -> str:
    return f"{qdrant_url.rstrip('/')}/{path.lstrip('/')}"


def _request_json(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
    response = requests.request(method, url, timeout=600, **kwargs)
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") not in (None, "ok"):
        raise RuntimeError(f"Qdrant retornou status inesperado: {payload}")
    return payload


def collection_point_count(collection_name: str, qdrant_url: str = QDRANT_URL) -> int:
    name = quote(collection_name, safe="")
    payload = _request_json(
        "POST",
        _endpoint(f"collections/{name}/points/count", qdrant_url),
        headers=_headers(),
        json={"exact": True},
    )
    return int(payload["result"]["count"])


def export_collection(
    destination: Path,
    collection_name: str = COLLECTION_NAME,
    qdrant_url: str = QDRANT_URL,
    bm25_path: Path = BM25_METADATA_PATH,
) -> Path:
    if not bm25_path.is_file():
        raise FileNotFoundError(f"Metadata BM25 nao encontrada: {bm25_path}")
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError(f"Diretorio de exportacao nao esta vazio: {destination}")
    destination.mkdir(parents=True, exist_ok=True)

    name = quote(collection_name, safe="")
    snapshot_result = _request_json(
        "POST",
        _endpoint(f"collections/{name}/snapshots", qdrant_url),
        headers=_headers(),
    )["result"]
    snapshot_name = str(snapshot_result["name"])
    snapshot_path = destination / snapshot_name
    with requests.get(
        _endpoint(f"collections/{name}/snapshots/{quote(snapshot_name, safe='')}", qdrant_url),
        headers=_headers(),
        timeout=600,
        stream=True,
    ) as response:
        response.raise_for_status()
        with snapshot_path.open("wb") as output:
            for block in response.iter_content(chunk_size=1024 * 1024):
                if block:
                    output.write(block)

    exported_bm25 = destination / "bm25_metadata.json"
    shutil.copy2(bm25_path, exported_bm25)
    bm25 = json.loads(exported_bm25.read_text(encoding="utf-8"))
    point_count = collection_point_count(collection_name, qdrant_url)
    if int(bm25["doc_count"]) != point_count:
        raise ValueError(
            f"Exportacao recusada: Qdrant tem {point_count} pontos, "
            f"mas BM25 declara {bm25['doc_count']} documentos."
        )

    manifest = {
        "format_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "collection_name": collection_name,
        "point_count": point_count,
        "snapshot": {"file": snapshot_path.name, "sha256": _sha256(snapshot_path)},
        "bm25": {"file": exported_bm25.name, "sha256": _sha256(exported_bm25)},
        "compatibility": {
            "qdrant_image": "qdrant/qdrant:v1.15.4",
            "note": "Restaure em Qdrant 1.15.x com patch igual ou superior ao da origem.",
        },
    }
    (destination / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return destination


def import_collection(
    source: Path,
    collection_name: str | None = None,
    qdrant_url: str = QDRANT_URL,
    bm25_path: Path = BM25_METADATA_PATH,
) -> str:
    manifest_path = source / MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if int(manifest.get("format_version", 0)) != 1:
        raise ValueError("Versao de exportacao nao suportada.")

    target = collection_name or str(manifest["collection_name"])
    snapshot_path = source / manifest["snapshot"]["file"]
    exported_bm25 = source / manifest["bm25"]["file"]
    for path, expected in (
        (snapshot_path, manifest["snapshot"]["sha256"]),
        (exported_bm25, manifest["bm25"]["sha256"]),
    ):
        if not path.is_file():
            raise FileNotFoundError(path)
        if _sha256(path) != expected:
            raise ValueError(f"Checksum invalido: {path}")

    name = quote(target, safe="")
    with snapshot_path.open("rb") as snapshot:
        response = requests.post(
            _endpoint(f"collections/{name}/snapshots/upload?priority=snapshot", qdrant_url),
            headers=_headers(),
            files={"snapshot": (snapshot_path.name, snapshot, "application/octet-stream")},
            timeout=1800,
        )
    response.raise_for_status()

    restored_count = collection_point_count(target, qdrant_url)
    expected_count = int(manifest["point_count"])
    if restored_count != expected_count:
        raise ValueError(f"Importacao incompleta: esperado={expected_count}, restaurado={restored_count}")
    bm25_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_bm25 = bm25_path.with_suffix(bm25_path.suffix + ".tmp")
    shutil.copy2(exported_bm25, temporary_bm25)
    temporary_bm25.replace(bm25_path)
    return target


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Exporta ou importa o indice de literatura do BILBO.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    export_parser = subparsers.add_parser("export", help="Cria e baixa snapshot + metadata BM25.")
    export_parser.add_argument("destination", type=Path)
    export_parser.add_argument("--collection", default=COLLECTION_NAME)
    import_parser = subparsers.add_parser("import", help="Restaura snapshot + metadata BM25.")
    import_parser.add_argument("source", type=Path)
    import_parser.add_argument("--collection", default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "export":
        result = export_collection(args.destination, collection_name=args.collection)
        print(f"Indice exportado para {result}")
    else:
        result = import_collection(args.source, collection_name=args.collection)
        print(f"Colecao {result} importada com sucesso")


if __name__ == "__main__":
    main()
