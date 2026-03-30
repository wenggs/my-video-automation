from __future__ import annotations

from pathlib import Path

from common.errors import AppError


def resolve_safe_under_root(root: Path, relative: str) -> Path:
    rel = relative.strip()
    if not rel:
        raise AppError("RELATIVE_PATH_INVALID", "relative path must be non-empty", {"path": relative})
    candidate = (root / rel).resolve()
    root_r = root.resolve()
    try:
        candidate.relative_to(root_r)
    except ValueError as e:
        raise AppError(
            "RELATIVE_PATH_INVALID",
            "path escapes input root",
            {"path": relative},
        ) from e
    return candidate
