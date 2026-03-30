from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import List, Tuple

from common.errors import AppError
from pipeline.lyrics_flow import WordTs, load_words


def _srt_ts_to_seconds(ts: str) -> float:
    # "HH:MM:SS,mmm"
    m = re.match(r"^(\d{2}):(\d{2}):(\d{2}),(\d{3})$", ts.strip())
    if not m:
        raise AppError("SRT_TIMESTAMP_PARSE_FAILED", "invalid SRT timestamp", {"timestamp": ts})
    hh, mm, ss, mss = (int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)))
    return hh * 3600 + mm * 60 + ss + mss / 1000.0


def _seconds_to_srt_ts(seconds: float) -> str:
    ms = int(round(max(0.0, seconds) * 1000))
    hh = ms // 3_600_000
    mm = (ms % 3_600_000) // 60_000
    ss = (ms % 60_000) // 1000
    mss = ms % 1000
    return f"{hh:02d}:{mm:02d}:{ss:02d},{mss:03d}"


def choose_trim_interval_from_words(
    *,
    words: List[WordTs],
    target_min_sec: float,
    target_max_sec: float,
) -> Tuple[float, float]:
    if not words:
        raise AppError("WORDS_INPUT_MISSING", "words list is empty", {})

    start = max(0.0, float(words[0].start))
    end = float(words[-1].end)
    if end <= start:
        raise AppError("WORDS_INPUT_MISSING", "words end must be > start", {"start": start, "end": end})

    total = end - start
    if total <= target_max_sec:
        # Includes cases where total < target_min_sec: we keep full range (don't fail MVP).
        return start, end

    # total > target_max_sec: cut the first window with length = target_max_sec
    return start, start + float(target_max_sec)


def trim_video_mp4(
    *,
    input_video: Path,
    start_sec: float,
    end_sec: float,
    output_video: Path,
) -> Path:
    if not input_video.is_file():
        raise AppError("VIDEO_FILE_NOT_FOUND", "input video does not exist", {"video_file": str(input_video)})
    if end_sec <= start_sec:
        raise AppError("VIDEO_EDIT_FAILED", "invalid trim interval", {"start_sec": start_sec, "end_sec": end_sec})

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise AppError("FFMPEG_NOT_FOUND", "ffmpeg is not on PATH; install ffmpeg and retry", {})

    output_video = output_video.resolve()
    output_video.parent.mkdir(parents=True, exist_ok=True)

    duration = end_sec - start_sec
    # Reset timestamps so the trimmed clip starts at 0 (matches shifted SRT).
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        str(start_sec),
        "-i",
        str(input_video.resolve()),
        "-t",
        str(duration),
        "-reset_timestamps",
        "1",
        "-c:v",
        "libx264",
        "-crf",
        "23",
        "-preset",
        "veryfast",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(output_video),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise AppError(
            "VIDEO_EDIT_FAILED",
            "ffmpeg failed to produce trimmed master",
            {"returncode": proc.returncode, "stderr": (proc.stderr or "")[-4000:]},
        )
    return output_video


def shift_srt_timestamps(
    *,
    input_srt: Path,
    offset_sec: float,
    output_srt: Path,
) -> Path:
    if not input_srt.is_file():
        raise AppError("SUBTITLES_FILE_NOT_FOUND", "subtitles file does not exist", {"subtitles_file": str(input_srt)})
    output_srt = output_srt.resolve()
    output_srt.parent.mkdir(parents=True, exist_ok=True)

    srt_text = input_srt.read_text(encoding="utf-8")
    blocks = re.split(r"\n\s*\n", srt_text.strip())
    out_blocks: List[str] = []

    for block in blocks:
        lines = [ln.rstrip("\r") for ln in block.split("\n") if ln.strip() != ""]
        if len(lines) < 2:
            continue
        # Common structure: index line, timestamp line, then one or more text lines.
        # We keep index simple and re-number later by order.
        ts_line = lines[1]
        m = re.match(r"^(.+?)\s*-->\s*(.+?)$", ts_line)
        if not m:
            raise AppError("SRT_TIMESTAMP_PARSE_FAILED", "invalid SRT time range line", {"line": ts_line})

        start_s = _srt_ts_to_seconds(m.group(1))
        end_s = _srt_ts_to_seconds(m.group(2))

        # Shift into trimmed timeline: t' = t - offset
        new_start = start_s - offset_sec
        new_end = end_s - offset_sec

        # Drop cues fully before trim start.
        if new_end <= 0:
            continue
        if new_start < 0:
            new_start = 0.0
        if new_end <= new_start:
            new_end = new_start + 0.05

        text_lines = lines[2:]
        out_blocks.append("\n".join([f"{_seconds_to_srt_ts(new_start)} --> {_seconds_to_srt_ts(new_end)}", *text_lines]))

    # Re-number cues in output.
    renumbered_blocks: List[str] = []
    for i, block in enumerate(out_blocks, start=1):
        # block currently starts with timestamp line.
        renumbered_blocks.append(f"{i}\n{block}\n")

    output_srt.write_text("\n".join(renumbered_blocks).strip() + "\n", encoding="utf-8")
    return output_srt


def run_trim_and_shift_for_burnin(
    *,
    input_video: Path,
    words_file: Path,
    aligned_subtitles_srt: Path,
    output_root: Path,
    target_min_sec: float = 30.0,
    target_max_sec: float = 60.0,
) -> Tuple[Path, Path, float]:
    words = load_words(words_file)
    trim_start, trim_end = choose_trim_interval_from_words(
        words=words,
        target_min_sec=target_min_sec,
        target_max_sec=target_max_sec,
    )

    edit_dir = output_root / "edited"
    edited_master_path = edit_dir / "edited_master.mp4"
    shifted_srt_path = output_root / "artifacts" / "subtitles_burnin.srt"

    trimmed = trim_video_mp4(
        input_video=input_video,
        start_sec=trim_start,
        end_sec=trim_end,
        output_video=edited_master_path,
    )
    shifted = shift_srt_timestamps(
        input_srt=aligned_subtitles_srt,
        offset_sec=trim_start,
        output_srt=shifted_srt_path,
    )
    return trimmed, shifted, trim_start

