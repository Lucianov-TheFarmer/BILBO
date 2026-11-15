"""Create a private configuration and start the BILBO Docker Compose stack."""

from __future__ import annotations

import argparse
import os
import secrets
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
EXAMPLE_FILE = ROOT / ".env.example"
GENERATED_SECRETS = ("POSTGRES_PASSWORD", "SECRET_KEY", "SSH_USER_PASSWORD", "PGADMIN_DEFAULT_PASSWORD")
HOST_PORTS = (
    "BILBO_HOST_PORT", "POSTGRES_HOST_PORT", "REDIS_HOST_PORT",
    "QDRANT_HOST_PORT", "QDRANT_GRPC_HOST_PORT", "OLLAMA_HOST_PORT",
    "SSH_HOST_PORT", "PGADMIN_HOST_PORT",
)


def read_env(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def prepare_env() -> dict[str, str]:
    if not EXAMPLE_FILE.is_file():
        raise RuntimeError("Arquivo .env.example não encontrado no repositório.")
    if not ENV_FILE.exists():
        ENV_FILE.write_text(EXAMPLE_FILE.read_text(encoding="utf-8"), encoding="utf-8")
        print("Arquivo .env criado a partir de .env.example.")
    text = ENV_FILE.read_text(encoding="utf-8")
    values = read_env(ENV_FILE)
    for key in GENERATED_SECRETS:
        if not values.get(key):
            value = secrets.token_urlsafe(36)
            if any(line.startswith(f"{key}=") for line in text.splitlines()):
                text = "\n".join(
                    f"{key}={value}" if line.startswith(f"{key}=") else line
                    for line in text.splitlines()
                ) + "\n"
            else:
                text += f"\n{key}={value}\n"
            values[key] = value
    ENV_FILE.write_text(text, encoding="utf-8")
    if os.name != "nt":
        ENV_FILE.chmod(0o600)
    return read_env(ENV_FILE)


def validate_env(values: dict[str, str]) -> None:
    used = {}
    for key in HOST_PORTS:
        try:
            port = int(values[key])
        except (KeyError, ValueError) as exc:
            raise RuntimeError(f"Porta inválida em {key} no .env.") from exc
        if not 1 <= port <= 65535:
            raise RuntimeError(f"Porta fora do intervalo em {key}: {port}.")
        if port in used:
            raise RuntimeError(f"Porta {port} repetida em {used[port]} e {key} no .env.")
        used[port] = key
    if values.get("BILBO_BIND_ADDRESS") not in {"127.0.0.1", "0.0.0.0"}:
        raise RuntimeError("Use BILBO_BIND_ADDRESS=127.0.0.1 ou 0.0.0.0 no .env.")
    for key in GENERATED_SECRETS:
        if not values.get(key):
            raise RuntimeError(f"{key} está vazio no .env.")
    configured = [values.get(key, "") for key in (
        "GOOGLE_DRIVE_CLIENT_ID", "GOOGLE_DRIVE_CLIENT_SECRET",
        "GOOGLE_DRIVE_API_KEY", "GOOGLE_DRIVE_APP_ID",
    )]
    if any(configured) and not all(configured):
        raise RuntimeError("Configure as quatro credenciais GOOGLE_DRIVE_* ou deixe todas vazias.")


def docker(*args: str) -> None:
    subprocess.run(["docker", *args], cwd=ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Instala e inicia o BILBO.")
    parser.add_argument("--check", action="store_true", help="Valida .env e Docker Compose sem iniciar.")
    parser.add_argument("--no-build", action="store_true", help="Inicia com a imagem existente.")
    parser.add_argument("--skip-rag-bootstrap", action="store_true", help="Adia o índice RAG para o primeiro uso.")
    args = parser.parse_args()
    try:
        values = prepare_env()
        validate_env(values)
        docker("compose", "version")
        docker("info", "--format", "{{.ServerVersion}}")
        docker("compose", "config", "--quiet")
        if args.check:
            print("Configuração válida. Nenhum container foi iniciado.")
            return 0
        command = ["compose", "up", "-d"]
        if not args.no_build:
            command.append("--build")
        docker(*command)
        if not args.skip_rag_bootstrap:
            docker("compose", "--profile", "bootstrap", "up", "-d", "rag-bootstrap")
        base = values.get("BILBO_PUBLIC_BASE_URL") or f"http://localhost:{values['BILBO_HOST_PORT']}"
        print(f"BILBO iniciando: {base.rstrip('/')}/frontend")
        print("Imagens, modelos Ollama e índice RAG podem continuar baixando em segundo plano.")
        print("Progresso: docker compose logs -f bioinfo ollama rag-bootstrap")
        print("Para alterar portas ou credenciais: edite .env e execute python3 init.py --no-build")
        return 0
    except FileNotFoundError as exc:
        print(f"Falha: programa não encontrado: {exc.filename}. Instale Docker com Compose.", file=sys.stderr)
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Falha: {exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
