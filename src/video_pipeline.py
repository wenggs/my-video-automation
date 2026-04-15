from __future__ import annotations

import argparse
from pathlib import Path

from common.errors import AppError
from services.lyrics_service import run_lyrics_flow_service
from services.video_edit_service import run_trim_and_shift_for_burnin
from services.video_export_service import export_douyin_vertical_burn_in


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

    v = sub.add_parser(
        "vertical-slice",
        help="lyrics align + 9:16 burn-in export (minimal Douyin-shaped demo)",
    )
    v.add_argument("--video", required=True, type=Path, help="source video file")
    v.add_argument("--lyrics", required=True, type=Path, help="official lyrics txt path")
    v.add_argument("--words", required=True, type=Path, help="ASR words json path")
    v.add_argument("--output", required=True, type=Path, help="job output root (artifacts + export/)")
    v.add_argument(
        "--export-name",
        default="douyin_vertical.mp4",
        help="filename under output/export/",
    )
    v.add_argument(
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
    elif args.cmd == "vertical-slice":
        try:
            lyrics_result = run_lyrics_flow_service(
                lyrics_file=args.lyrics,
                words_file=args.words,
                output_root=args.output,
                preserve_confirmed=args.preserve_confirmed,
            )
            trimmed_master, burnin_srt, _trim_start, trim_diag = run_trim_and_shift_for_burnin(
                input_video=args.video,
                words_file=args.words,
                aligned_subtitles_srt=lyrics_result.subtitles_path,
                output_root=args.output,
            )
            export_path = args.output / "export" / args.export_name
            export_douyin_vertical_burn_in(
                input_video=trimmed_master,
                subtitles_srt=burnin_srt,
                output_video=export_path,
            )
            print(f"official lyrics artifact: {lyrics_result.official_lyrics_path}")
            print(f"confirmed lyrics artifact: {lyrics_result.confirmed_lyrics_path}")
            print(f"aligned subtitles: {lyrics_result.subtitles_path}")
            print(f"trimmed master: {trimmed_master}")
            print(f"trim selection diagnostics: {trim_diag}")
            print(f"vertical export (9:16 burn-in): {export_path}")
            print(f"job log: {lyrics_result.log_path}")
        except AppError as e:
            print(e.to_dict())
            raise SystemExit(1)


