from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from common.errors import AppError


def export_douyin_vertical_burn_in(
    *,
    input_video: Path,
    subtitles_srt: Path,
    output_video: Path,
    width: int = 1080,
    height: int = 1920,
) -> Path:
    if not input_video.is_file():
        raise AppError(
            "VIDEO_FILE_NOT_FOUND",
            "input video does not exist",
            {"video_file": str(input_video)},
        )
    if not subtitles_srt.is_file():
        raise AppError(
            "SUBTITLES_FILE_NOT_FOUND",
            "subtitles file does not exist",
            {"subtitles_file": str(subtitles_srt)},
        )
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise AppError(
            "FFMPEG_NOT_FOUND",
            "ffmpeg is not on PATH; install ffmpeg and retry",
            {},
        )

    output_video = output_video.resolve()
    output_video.parent.mkdir(parents=True, exist_ok=True)
    work_dir = output_video.parent
    staging_srt = work_dir / "_burn_subtitles.srt"
    shutil.copyfile(subtitles_srt, staging_srt)

    # Relative SRT name avoids Windows drive-letter escaping in the subtitles filter.
    style = (
        "FontName=Microsoft YaHei,FontSize=26,PrimaryColour=&HFFFFFF,"
        "OutlineColour=&H80000000,BorderStyle=1,Outline=2,Shadow=0,MarginV=140"
    )
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
        f"subtitles={staging_srt.name}:force_style='{style}'"
    )
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(input_video.resolve()),
        "-vf",
        vf,
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
    proc = subprocess.run(
        cmd,
        cwd=str(work_dir),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise AppError(
            "VIDEO_EXPORT_FAILED",
            "ffmpeg failed to produce vertical burn-in export",
            {
                "returncode": proc.returncode,
                "stderr": (proc.stderr or "")[-4000:],
            },
        )
    return output_video
