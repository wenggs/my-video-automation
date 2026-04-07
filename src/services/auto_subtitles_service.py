from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from common.errors import AppError


@dataclass
class AutoSubtitlesResult:
    lines: List[str]
    srt_path: Path
    details: Dict[str, Any]


def _format_srt_ts(seconds: float) -> str:
    total_ms = int(round(max(0.0, seconds) * 1000))
    hh = total_ms // 3_600_000
    mm = (total_ms % 3_600_000) // 60_000
    ss = (total_ms % 60_000) // 1000
    ms = total_ms % 1000
    return f"{hh:02d}:{mm:02d}:{ss:02d},{ms:03d}"


def _fake_result(video_path: Path, output_dir: Path) -> AutoSubtitlesResult:
    lines = [
        "这是自动字幕示例第一句",
        "这是自动字幕示例第二句",
        "这是自动字幕示例第三句",
    ]
    segments = [
        {"start": 0.0, "end": 2.0, "text": lines[0]},
        {"start": 2.0, "end": 4.0, "text": lines[1]},
        {"start": 4.0, "end": 6.0, "text": lines[2]},
    ]
    srt_path = output_dir / "subtitles_auto.srt"
    srt_blocks: List[str] = []
    for idx, seg in enumerate(segments, start=1):
        srt_blocks.append(
            f"{idx}\n{_format_srt_ts(float(seg['start']))} --> {_format_srt_ts(float(seg['end']))}\n{str(seg['text']).strip()}\n"
        )
    srt_path.write_text("\n".join(srt_blocks), encoding="utf-8")
    (output_dir / "segments_auto.json").write_text(json.dumps(segments, ensure_ascii=False, indent=2), encoding="utf-8")
    return AutoSubtitlesResult(
        lines=lines,
        srt_path=srt_path,
        details={"engine": "fake", "video_path": str(video_path), "segments": len(segments)},
    )


def auto_generate_subtitles_from_video(
    *,
    video_path: Path,
    output_dir: Path,
    model_name: str = "small",
    language: str = "zh",
) -> AutoSubtitlesResult:
    if not video_path.exists() or not video_path.is_file():
        raise AppError("VIDEO_FILE_NOT_FOUND", "video file not found", {"path": str(video_path)})
    output_dir.mkdir(parents=True, exist_ok=True)

    if os.getenv("AUTO_SUBTITLES_FAKE", "").strip().lower() in ("1", "true", "yes"):
        return _fake_result(video_path, output_dir)

    try:
        from faster_whisper import WhisperModel  # type: ignore
    except Exception as e:
        raise AppError(
            "AUTO_SUBTITLES_ENGINE_NOT_AVAILABLE",
            "faster-whisper is not available in current environment",
            {"hint": "pip install faster-whisper", "exception": str(e)},
        ) from e

    try:
        model = WhisperModel(model_name, device="cpu", compute_type="int8")
        segments, info = model.transcribe(str(video_path), language=language, vad_filter=True)
        segs = list(segments)
    except Exception as e:
        raise AppError("AUTO_SUBTITLES_FAILED", "automatic subtitles generation failed", {"exception": str(e)}) from e

    lines: List[str] = []
    srt_blocks: List[str] = []
    raw_segments: List[Dict[str, Any]] = []
    for idx, seg in enumerate(segs, start=1):
        text = str(getattr(seg, "text", "")).strip()
        if not text:
            continue
        start = float(getattr(seg, "start", 0.0))
        end = float(getattr(seg, "end", start + 0.5))
        if end <= start:
            end = start + 0.5
        lines.append(text)
        raw_segments.append({"start": start, "end": end, "text": text})
        srt_blocks.append(f"{idx}\n{_format_srt_ts(start)} --> {_format_srt_ts(end)}\n{text}\n")

    if not lines:
        raise AppError("AUTO_SUBTITLES_EMPTY", "ASR returned no usable subtitle lines", {"video_path": str(video_path)})

    srt_path = output_dir / "subtitles_auto.srt"
    srt_path.write_text("\n".join(srt_blocks), encoding="utf-8")
    (output_dir / "segments_auto.json").write_text(json.dumps(raw_segments, ensure_ascii=False, indent=2), encoding="utf-8")
    return AutoSubtitlesResult(
        lines=lines,
        srt_path=srt_path,
        details={
            "engine": "faster_whisper",
            "model": model_name,
            "language": language,
            "segments": len(raw_segments),
            "duration_sec": float(getattr(info, "duration", 0.0)),
        },
    )

