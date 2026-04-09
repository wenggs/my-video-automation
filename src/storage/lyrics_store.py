from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from common.errors import AppError
from pipeline.lyrics_flow import normalize_lyrics_lines


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class LyricsStore:
    data_root: Path
    input_root: Path

    def _video_dir(self, video_id: str) -> Path:
        p = self.data_root / "library" / "videos" / video_id
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _state_file(self, video_id: str) -> Path:
        return self._video_dir(video_id) / "lyrics_state.json"

    def _tags_file(self, video_id: str) -> Path:
        return self._video_dir(video_id) / "tags_state.json"

    def _validate_mode_payload(self, payload: Dict[str, Any]) -> None:
        mode = payload.get("mode")
        if mode not in {"pasted", "sidecar_file", "convention"}:
            raise AppError("INVALID_MODE", "mode must be pasted|sidecar_file|convention")
        if mode == "pasted" and not payload.get("text"):
            raise AppError("MISSING_TEXT", "text is required when mode=pasted")
        if mode == "sidecar_file" and not payload.get("sidecar_relative_path"):
            raise AppError(
                "MISSING_SIDECAR_PATH",
                "sidecar_relative_path is required when mode=sidecar_file",
            )

    def _load_lines_from_mode(self, payload: Dict[str, Any]) -> List[str]:
        mode = payload["mode"]
        if mode == "pasted":
            return normalize_lyrics_lines(str(payload["text"]))

        if mode == "sidecar_file":
            rel = str(payload["sidecar_relative_path"])
            path = self.input_root / rel
            if not path.exists():
                raise AppError(
                    "LYRICS_SIDECAR_NOT_FOUND",
                    "lyrics sidecar file not found",
                    {"sidecar_relative_path": rel},
                )
            return normalize_lyrics_lines(path.read_text(encoding="utf-8"))

        # convention mode: "<video_id>.lyrics.txt" under input_root
        video_id = str(payload.get("video_id_for_convention", ""))
        filename = f"{video_id}.lyrics.txt"
        path = self.input_root / filename
        if not path.exists():
            raise AppError(
                "LYRICS_CONVENTION_NOT_FOUND",
                "convention lyrics file not found",
                {"expected_file": str(path)},
            )
        return normalize_lyrics_lines(path.read_text(encoding="utf-8"))

    def put_lyrics(self, video_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        self._validate_mode_payload(payload)
        payload = dict(payload)
        payload["video_id_for_convention"] = video_id
        lines = self._load_lines_from_mode(payload)
        preserve = bool(payload.get("preserve_confirmed", False))

        sf = self._state_file(video_id)
        old: Dict[str, Any] = {}
        if sf.exists():
            old = json.loads(sf.read_text(encoding="utf-8"))

        source = {
            "mode": payload["mode"],
            "sidecar_relative_path": payload.get("sidecar_relative_path"),
            "imported_at": _utc_now(),
        }
        import_block = {"lines": lines}
        if preserve and old.get("confirmed", {}).get("lines"):
            confirmed_lines = old["confirmed"]["lines"]
            changed = confirmed_lines != lines
        else:
            confirmed_lines = lines
            changed = False
        confirmed_block = {"lines": confirmed_lines, "changed": changed}

        state = {
            "video_asset_id": video_id,
            "source": source,
            "import": import_block,
            "confirmed": confirmed_block,
        }
        sf.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        return state

    def patch_confirmed(self, video_id: str, lines: List[str]) -> Dict[str, Any]:
        sf = self._state_file(video_id)
        if not sf.exists():
            raise AppError(
                "LYRICS_STATE_NOT_FOUND",
                "import lyrics first via PUT /lyrics before confirming edits",
            )
        confirmed_lines = normalize_lyrics_lines("\n".join(lines))
        state = json.loads(sf.read_text(encoding="utf-8"))
        state["confirmed"] = {
            "lines": confirmed_lines,
            "changed": confirmed_lines != state.get("import", {}).get("lines", []),
        }
        sf.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"video_asset_id": video_id, "confirmed": state["confirmed"]}

    def get_lyrics(self, video_id: str) -> Dict[str, Any]:
        sf = self._state_file(video_id)
        if not sf.exists():
            raise AppError(
                "LYRICS_STATE_NOT_FOUND",
                "lyrics state not found for video",
                {"video_asset_id": video_id},
            )
        return json.loads(sf.read_text(encoding="utf-8"))

    def get_tags(self, video_id: str) -> Dict[str, Any]:
        tf = self._tags_file(video_id)
        if not tf.exists():
            return {
                "video_asset_id": video_id,
                "tags_confirmed": [],
                "tags_suggested": [],
                "updated_at": None,
            }
        payload = json.loads(tf.read_text(encoding="utf-8"))
        tags_confirmed = payload.get("tags_confirmed")
        if not isinstance(tags_confirmed, list):
            tags_confirmed = []
        tags_suggested = payload.get("tags_suggested")
        if not isinstance(tags_suggested, list):
            tags_suggested = []
        return {
            "video_asset_id": video_id,
            "tags_confirmed": [str(x).strip() for x in tags_confirmed if str(x).strip()],
            "tags_suggested": [str(x).strip() for x in tags_suggested if str(x).strip()],
            "updated_at": payload.get("updated_at"),
        }

    def patch_tags(self, video_id: str, tags: List[str]) -> Dict[str, Any]:
        normalized: List[str] = []
        for x in tags:
            t = str(x).strip()
            if not t:
                continue
            if t not in normalized:
                normalized.append(t)
        current = self.get_tags(video_id)
        state = {
            "video_asset_id": video_id,
            "tags_confirmed": normalized,
            "tags_suggested": current.get("tags_suggested", []),
            "updated_at": _utc_now(),
        }
        self._tags_file(video_id).write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return state

    def patch_suggested_tags(self, video_id: str, tags: List[str]) -> Dict[str, Any]:
        normalized: List[str] = []
        for x in tags:
            t = str(x).strip()
            if not t:
                continue
            if t not in normalized:
                normalized.append(t)
        current = self.get_tags(video_id)
        state = {
            "video_asset_id": video_id,
            "tags_confirmed": current.get("tags_confirmed", []),
            "tags_suggested": normalized,
            "updated_at": _utc_now(),
        }
        self._tags_file(video_id).write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return state
