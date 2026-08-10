from __future__ import annotations

import fcntl
import json
import logging
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_OLLAMA_HOST = "http://ollama:11434"
DEFAULT_EMBEDDING_MODEL = "bge-m3:latest"
DEFAULT_LLM_MODEL = "gemma3:4b"

LOCK_FILE = Path(
    os.getenv(
        "OLLAMA_MODEL_LOCK_FILE",
        "/rag/.ollama-model-bootstrap.lock",
    )
)


def _enabled() -> bool:
    value = os.getenv(
        "OLLAMA_AUTO_PULL_MODELS",
        "true",
    )

    return value.strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _ollama_host() -> str:
    return os.getenv(
        "OLLAMA_HOST",
        DEFAULT_OLLAMA_HOST,
    ).rstrip("/")


def required_models() -> list[str]:
    configured = [
        os.getenv(
            "RAG_EMBEDDING_MODEL",
            DEFAULT_EMBEDDING_MODEL,
        ),
        os.getenv(
            "RAG_LLM_MODEL",
            DEFAULT_LLM_MODEL,
        ),
        os.getenv(
            "CLUSTER_INTERPRETATION_MODEL",
            DEFAULT_LLM_MODEL,
        ),
    ]

    models: list[str] = []

    for model in configured:
        model = str(model or "").strip()

        if model and model not in models:
            models.append(model)

    return models


def _aliases(model: str) -> set[str]:
    model = model.strip()

    aliases = {model}

    if model.endswith(":latest"):
        aliases.add(model[:-7])
    elif ":" not in model:
        aliases.add(f"{model}:latest")

    return aliases


def _request_json(
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    url = _ollama_host() + path

    data = None
    method = "GET"

    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        method = "POST"

    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
        },
        method=method,
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout,
        ) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        try:
            detail = error.read().decode(
                "utf-8",
                errors="replace",
            )
        except Exception:
            detail = ""

        raise RuntimeError(
            f"Ollama respondeu HTTP {error.code} "
            f"em {path}: {detail[:500]}"
        ) from error
    except urllib.error.URLError as error:
        raise RuntimeError(
            f"Ollama indisponível em {_ollama_host()}: "
            f"{error}"
        ) from error


def installed_models() -> set[str]:
    response = _request_json(
        "/api/tags",
        timeout=15,
    )

    models: set[str] = set()

    for item in response.get("models", []):
        name = str(item.get("name") or "").strip()

        if name:
            models.update(_aliases(name))

    return models


def missing_models() -> list[str]:
    installed = installed_models()

    return [
        model
        for model in required_models()
        if not (_aliases(model) & installed)
    ]


def _pull_model(model: str) -> None:
    url = _ollama_host() + "/api/pull"

    payload = json.dumps({
        "model": model,
        "stream": True,
    }).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
        },
        method="POST",
    )

    logger.warning(
        "Ollama: iniciando download automático de %s.",
        model,
    )

    last_reported = -10
    started = time.monotonic()

    try:
        with urllib.request.urlopen(
            request,
            timeout=1800,
        ) as response:
            for raw_line in response:
                raw_line = raw_line.strip()

                if not raw_line:
                    continue

                event = json.loads(
                    raw_line.decode(
                        "utf-8",
                        errors="replace",
                    )
                )

                if event.get("error"):
                    raise RuntimeError(
                        str(event["error"])
                    )

                completed = event.get("completed")
                total = event.get("total")

                if (
                    isinstance(completed, int)
                    and isinstance(total, int)
                    and total > 0
                ):
                    percent = int(
                        completed * 100 / total
                    )

                    if (
                        percent >= last_reported + 10
                        or percent == 100
                    ):
                        last_reported = percent

                        logger.warning(
                            "Ollama: download de %s em %d%%.",
                            model,
                            percent,
                        )

                status = str(
                    event.get("status") or ""
                ).lower()

                if status == "success":
                    break

    except urllib.error.HTTPError as error:
        try:
            detail = error.read().decode(
                "utf-8",
                errors="replace",
            )
        except Exception:
            detail = ""

        raise RuntimeError(
            f"Falha HTTP ao baixar {model}: "
            f"{error.code} {detail[:500]}"
        ) from error
    except urllib.error.URLError as error:
        raise RuntimeError(
            f"Falha de conexão ao baixar {model}: "
            f"{error}"
        ) from error

    elapsed = int(time.monotonic() - started)

    logger.warning(
        "Ollama: modelo %s disponível após %d s.",
        model,
        elapsed,
    )


def ensure_required_ollama_models() -> dict[str, Any]:
    models = required_models()

    if not _enabled():
        logger.info(
            "Download automático de modelos Ollama "
            "está desativado."
        )

        return {
            "enabled": False,
            "required": models,
            "downloaded": [],
            "missing": missing_models(),
        }

    LOCK_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    downloaded: list[str] = []

    with LOCK_FILE.open("a+", encoding="utf-8") as lock:
        logger.info(
            "Ollama: aguardando trava global de modelos."
        )

        fcntl.flock(
            lock.fileno(),
            fcntl.LOCK_EX,
        )

        try:
            missing = missing_models()

            if not missing:
                logger.info(
                    "Ollama: todos os modelos requeridos "
                    "já estão disponíveis: %s",
                    ", ".join(models),
                )
            else:
                logger.warning(
                    "Ollama: modelos ausentes: %s",
                    ", ".join(missing),
                )

                for model in missing:
                    _pull_model(model)
                    downloaded.append(model)

            remaining = missing_models()

            if remaining:
                raise RuntimeError(
                    "Modelos ainda ausentes após bootstrap: "
                    + ", ".join(remaining)
                )

            return {
                "enabled": True,
                "required": models,
                "downloaded": downloaded,
                "missing": [],
            }
        finally:
            fcntl.flock(
                lock.fileno(),
                fcntl.LOCK_UN,
            )
