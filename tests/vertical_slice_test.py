from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
FIXTURES = ROOT / "tests" / "fixtures" / "spike"


def _require_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        print("SKIP: ffmpeg not on PATH", file=sys.stderr)
        sys.exit(0)
    return exe


def _make_sample_mp4(ffmpeg: str, dest: Path) -> None:
    """Short 1280x720 clip with tone audio; longer than fixture word timestamps."""
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc=size=1280x720:rate=30:duration=8",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:sample_rate=48000:duration=8",
        "-pix_fmt",
        "yuv420p",
        "-shortest",
        str(dest),
    ]
    subprocess.run(cmd, check=True)


def run() -> None:
    ffmpeg = _require_ffmpeg()
    sys.path.insert(0, str(SRC))
    from services.lyrics_service import run_lyrics_flow_service  # noqa: PLC0415
    from services.video_edit_service import run_trim_and_shift_for_burnin  # noqa: PLC0415
    from services.video_export_service import export_douyin_vertical_burn_in  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        video = tmp / "sample.mp4"
        out_root = tmp / "job"
        export_path = out_root / "export" / "douyin_vertical.mp4"
        _make_sample_mp4(ffmpeg, video)

        lyrics = FIXTURES / "official_lyrics.txt"
        words = FIXTURES / "transcript_words.json"

        lyrics_result = run_lyrics_flow_service(
            lyrics_file=lyrics,
            words_file=words,
            output_root=out_root,
        )
        trimmed_master, burnin_srt, _trim_start = run_trim_and_shift_for_burnin(
            input_video=video,
            words_file=words,
            aligned_subtitles_srt=lyrics_result.subtitles_path,
            output_root=out_root,
        )
        export_douyin_vertical_burn_in(
            input_video=trimmed_master,
            subtitles_srt=burnin_srt,
            output_video=export_path,
        )

        assert export_path.is_file(), export_path
        assert export_path.stat().st_size > 10_000, "export file unexpectedly small"
        assert trimmed_master.is_file()
        assert burnin_srt.is_file()

    print("Vertical slice test passed.")


if __name__ == "__main__":
    run()
