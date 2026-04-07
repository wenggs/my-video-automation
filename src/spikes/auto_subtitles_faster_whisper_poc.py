from __future__ import annotations

import argparse
from pathlib import Path

from services.auto_subtitles_service import auto_generate_subtitles_from_video


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="PoC: auto-generate subtitles from video via faster-whisper")
    p.add_argument("--video", required=True, type=Path, help="input video path")
    p.add_argument("--out-dir", required=True, type=Path, help="output directory for auto subtitles artifacts")
    p.add_argument("--model", default="small", type=str, help="faster-whisper model name")
    p.add_argument("--language", default="zh", type=str, help="language hint")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    result = auto_generate_subtitles_from_video(
        video_path=args.video,
        output_dir=args.out_dir,
        model_name=args.model,
        language=args.language,
    )
    print(f"srt={result.srt_path}")
    print(f"lines={len(result.lines)}")
    print(f"details={result.details}")


if __name__ == "__main__":
    main()

