from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx


RAG_ROOT = Path(os.getenv("RAG_ROOT", "/rag"))
QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333").rstrip("/")
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "banco_literatura_bio")
BM25_METADATA_PATH = Path(
    os.getenv("BM25_METADATA_PATH", str(RAG_ROOT / "bm25_metadata.json"))
)

SNAPSHOT_URL = os.getenv(
    "RAG_SNAPSHOT_URL",
    (
        "https://zenodo.org/api/records/21855338/files/"
        "QDrant_DB_BILBO_Plants.zip/content"
    ),
)
SNAPSHOT_ARCHIVE_MD5 = os.getenv(
    "RAG_SNAPSHOT_MD5",
    "b06fb3793956cf5809f6c4091b8d91db",
).lower()

EXPECTED_SNAPSHOT_SHA256 = os.getenv(
    "RAG_SNAPSHOT_SHA256",
    "a087b0601fcb14f7498b0cdb41573569f8584e47963d4aed4239725530790fa4",
).lower()

EXPECTED_BM25_SHA256 = os.getenv(
    "RAG_BM25_SHA256",
    "8b4085db8fe788cc63426a78450204c28a7dd37c5cb3d1d32e7dc34e99f72882",
).lower()

ARCHIVE_NAME = "QDrant_DB_BILBO_Plants.zip"
DOWNLOAD_DIR = RAG_ROOT / "downloads"
ARCHIVE_PATH = DOWNLOAD_DIR / ARCHIVE_NAME
PART_PATH = DOWNLOAD_DIR / f"{ARCHIVE_NAME}.part"
WORK_DIR = RAG_ROOT / "bootstrap_work"
STATUS_PATH = RAG_ROOT / "bootstrap_status.json"
LOCK_PATH = RAG_ROOT / ".bootstrap.lock"

EXPECTED_POINT_COUNT = 53037
MIN_FREE_BYTES = int(os.getenv("RAG_BOOTSTRAP_MIN_FREE_BYTES", str(1_300_000_000)))
KEEP_ARCHIVE = os.getenv("RAG_KEEP_ARCHIVE", "false").lower() in {
    "1",
    "true",
    "yes",
    "on",
}


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _write_status(
    state: str,
    message: str,
    *,
    downloaded: int | None = None,
    total: int | None = None,
    error: str | None = None,
) -> None:
    percent = None
    if downloaded is not None and total:
        percent = round(downloaded * 100 / total, 1)

    _atomic_json(
        STATUS_PATH,
        {
            "state": state,
            "message": message,
            "downloaded_bytes": downloaded,
            "total_bytes": total,
            "percent": percent,
            "error": error,
            "updated_at": time.time(),
        },
    )


def _read_status_file() -> dict[str, Any]:
    if not STATUS_PATH.exists():
        return {}
    try:
        value = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _collection_info() -> dict[str, Any]:
    url = f"{QDRANT_URL}/collections/{quote(COLLECTION_NAME, safe='')}"
    try:
        response = httpx.get(url, timeout=10)
        if response.status_code != 200:
            return {"exists": False, "points_count": None}

        result = response.json().get("result") or {}
        return {
            "exists": True,
            "points_count": result.get("points_count"),
            "vectors_count": result.get("vectors_count"),
            "status": result.get("status"),
        }
    except Exception as exc:
        return {
            "exists": False,
            "points_count": None,
            "connection_error": str(exc),
        }


def rag_status() -> dict[str, Any]:
    collection = _collection_info()
    metadata_ready = (
        BM25_METADATA_PATH.exists()
        and BM25_METADATA_PATH.is_file()
        and BM25_METADATA_PATH.stat().st_size > 0
    )
    ready = bool(collection.get("exists") and metadata_ready)

    persisted = _read_status_file()
    if ready:
        state = "ready"
        message = "Qdrant collection and BM25 metadata are available."
    elif persisted.get("state") in {
        "checking",
        "downloading",
        "validating",
        "extracting",
        "restoring",
    }:
        state = persisted["state"]
        message = persisted.get("message", "")
    else:
        state = "not_ready"
        message = "The shared RAG database has not been initialized."

    return {
        **persisted,
        "state": state,
        "message": message,
        "ready": ready,
        "collection": COLLECTION_NAME,
        "collection_exists": bool(collection.get("exists")),
        "points_count": collection.get("points_count"),
        "expected_points": EXPECTED_POINT_COUNT,
        "bm25_metadata_ready": metadata_ready,
        "bm25_metadata_path": str(BM25_METADATA_PATH),
        "snapshot_url": SNAPSHOT_URL,
        "qdrant": collection,
    }


def _hash_file(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().lower()


def _acquire_lock() -> bool:
    RAG_ROOT.mkdir(parents=True, exist_ok=True)

    if LOCK_PATH.exists():
        try:
            age = time.time() - LOCK_PATH.stat().st_mtime
            if age > 6 * 60 * 60:
                LOCK_PATH.unlink(missing_ok=True)
        except OSError:
            pass

    try:
        descriptor = os.open(
            LOCK_PATH,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "pid": os.getpid(),
                        "created_at": time.time(),
                    }
                )
            )
        return True
    except FileExistsError:
        return False


def _wait_for_other_initializer(timeout: int = 7200) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = rag_status()
        if status["ready"]:
            return status
        if not LOCK_PATH.exists():
            break
        time.sleep(5)
    raise TimeoutError("Timed out waiting for another RAG initialization job.")


def _download_archive() -> Path:
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    if ARCHIVE_PATH.exists():
        _write_status("validating", "Validating cached Zenodo archive.")
        if _hash_file(ARCHIVE_PATH, "md5") == SNAPSHOT_ARCHIVE_MD5:
            return ARCHIVE_PATH
        ARCHIVE_PATH.unlink(missing_ok=True)

    existing = PART_PATH.stat().st_size if PART_PATH.exists() else 0
    headers = {"User-Agent": "BILBO-RAG-bootstrap/1.0"}
    if existing:
        headers["Range"] = f"bytes={existing}-"

    timeout = httpx.Timeout(3600.0, connect=60.0)
    with httpx.Client(
        follow_redirects=True,
        timeout=timeout,
    ) as client:
        with client.stream("GET", SNAPSHOT_URL, headers=headers) as response:
            response.raise_for_status()

            append = existing > 0 and response.status_code == 206
            if not append:
                existing = 0

            content_range = response.headers.get("Content-Range", "")
            total = None
            if "/" in content_range:
                try:
                    total = int(content_range.rsplit("/", 1)[1])
                except ValueError:
                    total = None

            if total is None:
                content_length = int(response.headers.get("Content-Length", "0") or 0)
                total = existing + content_length if content_length else None

            mode = "ab" if append else "wb"
            downloaded = existing
            last_report = -1

            with PART_PATH.open(mode) as output:
                for chunk in response.iter_bytes(1024 * 1024):
                    output.write(chunk)
                    downloaded += len(chunk)

                    current_report = downloaded // (10 * 1024 * 1024)
                    if current_report != last_report:
                        _write_status(
                            "downloading",
                            "Downloading Qdrant snapshot from Zenodo.",
                            downloaded=downloaded,
                            total=total,
                        )
                        last_report = current_report

    os.replace(PART_PATH, ARCHIVE_PATH)
    return ARCHIVE_PATH


def _safe_extract(archive: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)
    destination_root = destination.resolve()

    with zipfile.ZipFile(archive) as compressed:
        for member in compressed.infolist():
            target = (destination / member.filename).resolve()
            try:
                target.relative_to(destination_root)
            except ValueError as exc:
                raise ValueError(
                    f"Unsafe path inside the RAG archive: {member.filename}"
                ) from exc
        compressed.extractall(destination)


def _locate_export(root: Path) -> tuple[Path, Path, dict[str, Any]]:
    manifests = list(root.rglob("manifest.json"))
    if not manifests:
        raise FileNotFoundError("manifest.json was not found in the Zenodo archive.")

    manifest_path = manifests[0]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    if manifest.get("collection_name") != COLLECTION_NAME:
        raise ValueError(
            "Snapshot collection mismatch: "
            f"{manifest.get('collection_name')} != {COLLECTION_NAME}"
        )

    snapshot_name = (manifest.get("snapshot") or {}).get("file")
    bm25_name = (manifest.get("bm25") or {}).get("file")
    if not snapshot_name or not bm25_name:
        raise ValueError("Snapshot or BM25 filename missing from manifest.json.")

    snapshot_path = manifest_path.parent / snapshot_name
    bm25_path = manifest_path.parent / bm25_name

    if not snapshot_path.exists():
        raise FileNotFoundError(f"Snapshot not found: {snapshot_path}")
    if not bm25_path.exists():
        raise FileNotFoundError(f"BM25 metadata not found: {bm25_path}")

    return snapshot_path, bm25_path, manifest


def _validate_export(
    snapshot_path: Path,
    bm25_path: Path,
    manifest: dict[str, Any],
) -> None:
    declared_snapshot_hash = (
        (manifest.get("snapshot") or {}).get("sha256")
        or EXPECTED_SNAPSHOT_SHA256
    ).lower()
    declared_bm25_hash = (
        (manifest.get("bm25") or {}).get("sha256")
        or EXPECTED_BM25_SHA256
    ).lower()

    snapshot_hash = _hash_file(snapshot_path, "sha256")
    if snapshot_hash != declared_snapshot_hash:
        raise ValueError(
            f"Invalid snapshot SHA-256: {snapshot_hash}"
        )

    bm25_hash = _hash_file(bm25_path, "sha256")
    if bm25_hash != declared_bm25_hash:
        raise ValueError(
            f"Invalid BM25 SHA-256: {bm25_hash}"
        )


def _restore_snapshot(snapshot_path: Path) -> None:
    collection = quote(COLLECTION_NAME, safe="")
    url = f"{QDRANT_URL}/collections/{collection}/snapshots/upload"

    timeout = httpx.Timeout(7200.0, connect=60.0)
    with snapshot_path.open("rb") as snapshot:
        response = httpx.post(
            url,
            params={"priority": "snapshot"},
            files={
                "snapshot": (
                    snapshot_path.name,
                    snapshot,
                    "application/octet-stream",
                )
            },
            timeout=timeout,
        )

    if response.status_code not in {200, 201, 202}:
        raise RuntimeError(
            "Qdrant snapshot restoration failed: "
            f"{response.status_code} {response.text[:2000]}"
        )


def _install_bm25_metadata(source: Path) -> None:
    BM25_METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = BM25_METADATA_PATH.with_suffix(".json.tmp")
    shutil.copyfile(source, temporary)
    os.replace(temporary, BM25_METADATA_PATH)


def ensure_rag_database() -> dict[str, Any]:
    initial = rag_status()
    if initial["ready"]:
        return initial

    if not _acquire_lock():
        return _wait_for_other_initializer()

    try:
        _write_status("checking", "Checking disk space and RAG prerequisites.")

        free_bytes = shutil.disk_usage(RAG_ROOT).free
        if free_bytes < MIN_FREE_BYTES:
            raise OSError(
                "Insufficient disk space for RAG bootstrap. "
                f"Available={free_bytes}, required={MIN_FREE_BYTES}."
            )

        archive = _download_archive()

        _write_status("validating", "Validating Zenodo archive checksum.")
        archive_md5 = _hash_file(archive, "md5")
        if archive_md5 != SNAPSHOT_ARCHIVE_MD5:
            raise ValueError(
                f"Invalid Zenodo archive MD5: {archive_md5}"
            )

        _write_status("extracting", "Extracting Qdrant snapshot and BM25 metadata.")
        _safe_extract(archive, WORK_DIR)
        snapshot_path, bm25_path, manifest = _locate_export(WORK_DIR)

        _write_status("validating", "Validating internal SHA-256 checksums.")
        _validate_export(snapshot_path, bm25_path, manifest)

        _write_status("restoring", "Restoring the shared Qdrant collection.")
        _restore_snapshot(snapshot_path)

        _write_status("restoring", "Installing BM25 metadata.")
        _install_bm25_metadata(bm25_path)

        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            final = rag_status()
            if final["ready"]:
                _write_status(
                    "ready",
                    "RAG database initialized successfully.",
                )
                return rag_status()
            time.sleep(3)

        raise RuntimeError(
            "Snapshot upload completed, but the RAG database did not become ready."
        )

    except Exception as exc:
        _write_status(
            "failed",
            "RAG database initialization failed.",
            error=str(exc),
        )
        raise
    finally:
        LOCK_PATH.unlink(missing_ok=True)
        if WORK_DIR.exists():
            shutil.rmtree(WORK_DIR, ignore_errors=True)
        if not KEEP_ARCHIVE:
            ARCHIVE_PATH.unlink(missing_ok=True)
            PART_PATH.unlink(missing_ok=True)

# BILBO_OLLAMA_BOOTSTRAP_WRAPPER
_original_ensure_rag_database = ensure_rag_database


def ensure_rag_database(*args, **kwargs):
    from .ollama_bootstrap import (
        ensure_required_ollama_models,
    )

    ensure_required_ollama_models()

    return _original_ensure_rag_database(
        *args,
        **kwargs,
    )
