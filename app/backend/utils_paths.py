from pathlib import Path

from fastapi import HTTPException

def _ensure_within(base: Path, candidate: Path) -> None:
    try:
        candidate.relative_to(base)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid path.")


def ensure_safe_component(value: str, field_name: str = "name") -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise HTTPException(status_code=400, detail=f"Invalid {field_name}.")
    if len(normalized) > 255:
        raise HTTPException(status_code=400, detail=f"Invalid {field_name}.")
    if any(ord(ch) < 32 for ch in normalized):
        raise HTTPException(status_code=400, detail=f"Invalid {field_name}.")
    if any(sep in normalized for sep in ["/", "\\", "\x00"]) or normalized in {".", ".."}:
        raise HTTPException(status_code=400, detail=f"Invalid {field_name}.")
    return normalized


def safe_resolve_user_path(users_root: str, user_id: int, *parts: str) -> Path:
    root = Path(users_root).resolve()
    base = (root / str(user_id)).resolve()
    candidate = base
    for part in parts:
        candidate = (candidate / part).resolve()

    _ensure_within(base, candidate)

    return candidate


def safe_join_under(path: Path, *parts: str) -> Path:
    base = path.resolve()
    candidate = base
    for part in parts:
        candidate = (candidate / part).resolve()
    _ensure_within(base, candidate)
    return candidate
