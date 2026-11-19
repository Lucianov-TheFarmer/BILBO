"""Resumable Drive-to-server transfer for paired FASTQ files."""

from __future__ import annotations

import hashlib
import os
import shutil
import time
from pathlib import Path

import requests

from ..core.settings import settings
from ..db.database import SessionLocal
from ..db.models import PipelineJob, SampleStage
from ..schemas.common import PipelineStatus
from ..services.drive_service import DRIVE_API, access_token, file_metadata, redis_client
from ..services.job_service import append_job_event, set_job_finished, set_job_running
from ..utils_paths import safe_resolve_user_path
from .celery_app import celery_app


def _md5(path: Path) -> str:
    digest = hashlib.md5()  # noqa: S324 - Drive's integrity field is MD5.
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(session_id: str, file: dict, target: Path, job_id: str) -> None:
    metadata = file_metadata(session_id, file["id"])
    if metadata["name"] != file["name"] or int(metadata["size"]) != file["size"]:
        raise ValueError("Drive file changed after selection")
    expected_md5 = metadata["md5Checksum"]
    expected_size = int(metadata["size"])
    if target.exists():
        if target.stat().st_size == expected_size and _md5(target) == expected_md5:
            return
        raise ValueError(f"Existing file differs: {target.name}")
    partial = target.with_name(target.name + ".part")
    progress_key = f"bilbo:drive:job:{job_id}"
    progress_store = redis_client()
    for attempt in range(5):
        offset = partial.stat().st_size if partial.exists() else 0
        if offset > expected_size:
            partial.unlink()
            offset = 0
        if offset == expected_size and _md5(partial) == expected_md5:
            os.replace(partial, target)
            return
        headers = {"Authorization": f"Bearer {access_token(session_id)}"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        try:
            with requests.get(f"{DRIVE_API}/{file['id']}", params={"alt": "media"}, headers=headers, stream=True, timeout=(30, 120)) as response:
                response.raise_for_status()
                if offset and response.status_code != 206:
                    raise ValueError("Drive did not honor partial download")
                with partial.open("ab" if offset else "wb") as output:
                    downloaded = offset
                    for chunk in response.iter_content(8 * 1024 * 1024):
                        if chunk:
                            output.write(chunk)
                            downloaded += len(chunk)
                            progress_store.hset(progress_key, mapping={"file": target.name, "bytes": downloaded, "total": expected_size})
                            progress_store.expire(progress_key, 7 * 24 * 3600)
            if partial.stat().st_size != expected_size:
                raise IOError("Incomplete Drive download")
            if _md5(partial) != expected_md5:
                partial.unlink(missing_ok=True)
                raise ValueError("Drive checksum mismatch")
            os.replace(partial, target)
            return
        except (requests.RequestException, IOError):
            if attempt == 4:
                raise
            time.sleep(min(2**attempt, 16))
    raise IOError("Drive transfer failed")


@celery_app.task(name="drive.import_pair")
def import_drive_pair(job_id: str, session_id: str):
    db = SessionLocal()
    try:
        job = set_job_running(db, job_id)
        if job.status != PipelineStatus.RUNNING.value:
            return
        files = job.payload["files"]
        base = job.payload["base"]
        user_dir = safe_resolve_user_path(settings.users_root, job.user_id, "samples", base)
        user_dir.mkdir(parents=True, exist_ok=True)
        required = sum(int(f["size"]) for f in files)
        if shutil.disk_usage(user_dir).free < required + 10 * 1024**3:
            raise OSError("Insufficient disk space for selected FASTQ pair")
        outputs = []
        for file in files:
            target = user_dir / f"{base}_{file['mate']}.fastq.gz"
            append_job_event(job.user_id, job_id, f"Drive: iniciando {target.name} ({file['size']} bytes).")
            _download(session_id, file, target, job_id)
            append_job_event(job.user_id, job_id, f"Drive: {target.name} baixado e verificado.")
            outputs.append((file, target))
        for file, target in outputs:
            db.add(SampleStage(
                stage_id=1, name=target.name, sra_code=base,
                size=f"{target.stat().st_size / 1024**3:.2f} GB",
                status="COMPLETED", user_id=job.user_id,
            ))
        db.commit()
        set_job_finished(db, job_id, PipelineStatus.COMPLETED, result={"files": [p.name for _, p in outputs]})
    except Exception as exc:
        db.rollback()
        set_job_finished(db, job_id, PipelineStatus.FAILED, error_message=str(exc)[:500])
        raise
    finally:
        db.close()
