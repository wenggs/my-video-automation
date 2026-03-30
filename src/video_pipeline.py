from __future__ import annotations

import argparse
from pathlib import Path

from common.errors import AppError
from services.lyrics_service import run_lyrics_flow_service


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Video pipeline local runner")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("lyrics-flow", help="run lyrics ingest + align flow")
    p.add_argument("--lyrics", required=True, type=Path, help="official lyrics txt path")
    p.add_argument("--words", required=True, type=Path, help="ASR words json path")
    p.add_argument("--output", required=True, type=Path, help="job output root")
    p.add_argument(
        "--preserve-confirmed",
        action="store_true",
        help="keep existing confirmed snapshot if present",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.cmd == "lyrics-flow":
        try:
            result = run_lyrics_flow_service(
                lyrics_file=args.lyrics,
                words_file=args.words,
                output_root=args.output,
                preserve_confirmed=args.preserve_confirmed,
            )
            print(f"official lyrics artifact: {result.official_lyrics_path}")
            print(f"confirmed lyrics artifact: {result.confirmed_lyrics_path}")
            print(f"aligned subtitles: {result.subtitles_path}")
            print(f"job log: {result.log_path}")
        except AppError as e:
            print(e.to_dict())
            raise SystemExit(1)


