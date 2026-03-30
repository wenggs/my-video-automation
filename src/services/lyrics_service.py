from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from common.errors import AppError
from pipeline.lyrics_flow import (
    align_confirmed_lyrics_to_words,
    load_lyrics_from_file,
    load_words,
    save_json,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobLogger:
    def __init__(self, log_file: Path) -> None:
        self.log_file = log_file
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, level: str, step: str, message: str, data: Dict[str, Any] | None = None) -> None:
        record = {
            "timestamp": _utc_now(),
            "level": level,
            "step": step,
            "message": message,
            "data": data or {},
        }
        with self.log_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


@dataclass
class LyricsFlowResult:
    official_lyrics_path: Path
    confirmed_lyrics_path: Path
    subtitles_path: Path
    log_path: Path


def run_lyrics_flow_service(
    *,
    lyrics_file: Path | None,
    words_file: Path,
    output_root: Path,
    preserve_confirmed: bool = False,
    source_mode: str = "sidecar_file",
    source_sidecar_relative_path: str | None = None,
    import_lines_override: List[str] | None = None,
    confirmed_lines_override: List[str] | None = None,
) -> LyricsFlowResult:
    artifacts_dir = output_root / "artifacts"
    logs_dir = output_root / "logs"
    log_file = logs_dir / "job.log"
    logger = JobLogger(log_file=log_file)
    output_root.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    logger.emit(
        "info",
        "discover_validate",
        "start lyrics flow",
        {
            "lyrics_file": str(lyrics_file) if lyrics_file else None,
            "words_file": str(words_file),
            "preserve_confirmed": preserve_confirmed,
        },
    )

    try:
        if import_lines_override is None:
            if lyrics_file is None:
                raise AppError(
                    code="LYRICS_INPUT_MISSING",
                    message="either lyrics_file or import_lines_override is required",
                )
            if not lyrics_file.exists():
                raise AppError(
                    code="LYRICS_FILE_NOT_FOUND",
                    message="lyrics file does not exist",
                    details={"lyrics_file": str(lyrics_file)},
                )
        if not words_file.exists():
            raise AppError(
                code="WORDS_FILE_NOT_FOUND",
                message="ASR words file does not exist",
                details={"words_file": str(words_file)},
            )

        logger.emit("info", "lyrics_ingest_validate", "loading official lyrics")
        imported_lines = import_lines_override if import_lines_override is not None else load_lyrics_from_file(lyrics_file)
        official_payload: Dict[str, Any] = {
            "version": 1,
            "source": {
                "mode": source_mode,
                "sidecar_relative_path": source_sidecar_relative_path
                if source_sidecar_relative_path is not None
                else (str(lyrics_file).replace("\\", "/") if lyrics_file else None),
                "imported_at": _utc_now(),
            },
            "lines": imported_lines,
        }
        official_path = artifacts_dir / "official_lyrics.json"
        save_json(official_path, official_payload)

        logger.emit(
            "info",
            "lyrics_ingest_validate",
            "official lyrics snapshot created",
            {"line_count": len(imported_lines)},
        )

        confirmed_path = artifacts_dir / "lyrics_confirmed.json"
        if confirmed_lines_override is not None:
            logger.emit("info", "lyrics_confirmed", "using confirmed lines override")
            confirmed_lines = confirmed_lines_override
            confirmed_payload = {
                "version": 1,
                "basis": {"imported_snapshot_id": None},
                "confirmed_at": _utc_now(),
                "lines": confirmed_lines,
            }
            save_json(confirmed_path, confirmed_payload)
        elif preserve_confirmed and confirmed_path.exists():
            logger.emit("info", "lyrics_confirmed", "reusing existing confirmed snapshot")
            confirmed_payload = json.loads(confirmed_path.read_text(encoding="utf-8"))
            confirmed_lines: List[str] = confirmed_payload.get("lines", imported_lines)
        else:
            logger.emit("info", "lyrics_confirmed", "creating confirmed snapshot from import")
            confirmed_lines = imported_lines
            confirmed_payload = {
                "version": 1,
                "basis": {"imported_snapshot_id": None},
                "confirmed_at": _utc_now(),
                "lines": confirmed_lines,
            }
            save_json(confirmed_path, confirmed_payload)

        logger.emit("info", "asr_transcribe", "loading words timestamps")
        words = load_words(words_file)

        logger.emit("info", "lyrics_force_align", "aligning confirmed lyrics to words")
        srt_text = align_confirmed_lyrics_to_words(confirmed_lines, words)
        subtitles_path = artifacts_dir / "subtitles.srt"
        subtitles_path.write_text(srt_text, encoding="utf-8")
        logger.emit(
            "info",
            "lyrics_force_align",
            "aligned subtitles generated",
            {"subtitles_path": str(subtitles_path)},
        )

        logger.emit("info", "completed", "lyrics flow completed")
        return LyricsFlowResult(
            official_lyrics_path=official_path,
            confirmed_lyrics_path=confirmed_path,
            subtitles_path=subtitles_path,
            log_path=log_file,
        )
    except AppError as e:
        logger.emit("error", "failed", e.message, {"code": e.code, **e.details})
        raise
    except Exception as e:  # pragma: no cover - fallback path
        wrapped = AppError(
            code="LYRICS_FLOW_UNEXPECTED",
            message="unexpected error in lyrics flow",
            details={"exception": str(e)},
        )
        logger.emit("error", "failed", wrapped.message, wrapped.details)
        raise wrapped
