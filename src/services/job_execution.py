from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from common.errors import AppError
from common.paths import resolve_safe_under_root
from services.lyrics_service import run_lyrics_flow_service
from services.video_export_service import export_douyin_vertical_burn_in
from storage.job_store import JobStore


def run_lyrics_export_job(
    *,
    job_store: JobStore,
    input_root: Path,
    data_root: Path,
    job_id: str,
    words_relative_path: str,
    video_rel: str,
    import_lines: List[str],
    confirmed_lines: List[str],
    source: Dict[str, Any],
) -> None:
    """Background worker: lyrics align, optional 9:16 burn-in. Updates job_store."""
    def is_cancelled() -> bool:
        # JobStore is file-based; treat each check as authoritative.
        try:
            return job_store.get(job_id).get("status") == "cancelled"
        except Exception:
            # If job JSON disappears/corrupts, don't block progress in the worker.
            return False

    output_root = data_root / "jobs-run" / job_id
    if is_cancelled():
        job_store.update(job_id, {"status": "cancelled", "current_step": "cancelled", "error": None})
        return

    job_store.update(job_id, {"status": "running", "current_step": "discover_validate"})
    video_file: Path | None = None
    try:
        words_file = resolve_safe_under_root(input_root, words_relative_path)
        if video_rel:
            video_file = resolve_safe_under_root(input_root, video_rel)
            if not video_file.is_file():
                raise AppError(
                    "VIDEO_FILE_NOT_FOUND",
                    "input video does not exist",
                    {"video_file": str(video_file)},
                )
        result = run_lyrics_flow_service(
            lyrics_file=None,
            words_file=words_file,
            output_root=output_root,
            preserve_confirmed=False,
            source_mode=str(source.get("mode", "sidecar_file")),
            source_sidecar_relative_path=source.get("sidecar_relative_path"),
            import_lines_override=import_lines,
            confirmed_lines_override=confirmed_lines,
        )
        if is_cancelled():
            job_store.update(job_id, {"status": "cancelled", "current_step": "cancelled", "error": None})
            return

        artifacts: Dict[str, str] = {
            "official_lyrics": str(result.official_lyrics_path),
            "lyrics_confirmed": str(result.confirmed_lyrics_path),
            "aligned_subtitles": str(result.subtitles_path),
            "job_log": str(result.log_path),
        }
        if video_file is not None:
            export_path = output_root / "export" / "douyin_vertical.mp4"
            export_douyin_vertical_burn_in(
                input_video=video_file,
                subtitles_srt=result.subtitles_path,
                output_video=export_path,
            )
            artifacts["douyin_vertical"] = str(export_path)

        if is_cancelled():
            job_store.update(job_id, {"status": "cancelled", "current_step": "cancelled", "error": None})
            return

        job_store.update(
            job_id,
            {
                "status": "succeeded",
                "current_step": "completed",
                "artifacts": artifacts,
            },
        )
    except AppError as e:
        if is_cancelled():
            job_store.update(job_id, {"status": "cancelled", "current_step": "cancelled", "error": None})
            return
        job_store.update(
            job_id,
            {
                "status": "failed",
                "current_step": "failed",
                "error": {"code": e.code, "message": e.message, "details": e.details},
            },
        )
    except Exception as e:  # pragma: no cover - last resort
        if is_cancelled():
            job_store.update(job_id, {"status": "cancelled", "current_step": "cancelled", "error": None})
            return
        job_store.update(
            job_id,
            {
                "status": "failed",
                "current_step": "failed",
                "error": {
                    "code": "JOB_WORKER_UNEXPECTED",
                    "message": "unexpected worker error",
                    "details": {"exception": str(e)},
                },
            },
        )
