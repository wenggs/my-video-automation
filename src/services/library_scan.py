from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from common.errors import AppError

VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"})


def scan_video_files(input_root: Path) -> List[Dict[str, Any]]:
    root = input_root.resolve()
    if not root.is_dir():
        raise AppError(
            "INPUT_ROOT_INVALID",
            "input_root is not a directory",
            {"input_root": str(input_root)},
        )
    items: List[Dict[str, Any]] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in VIDEO_EXTENSIONS:
            continue
        rel = p.relative_to(root).as_posix()
        items.append({"relative_path": rel, "size_bytes": p.stat().st_size})
    items.sort(key=lambda x: x["relative_path"])
    return items
