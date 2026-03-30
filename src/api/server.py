from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Tuple

# Ensure `src/` is importable when launching this file directly.
sys.path.append(str(Path(__file__).resolve().parents[1]))

from common.errors import AppError, http_status_for_app_error
from common.paths import resolve_safe_under_root
from services.lyrics_service import run_lyrics_flow_service
from services.video_export_service import export_douyin_vertical_burn_in
from storage.job_store import JobStore
from storage.lyrics_store import LyricsStore


class ApiHandler(BaseHTTPRequestHandler):
    store: LyricsStore
    job_store: JobStore
    input_root: Path
    data_root: Path

    def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            raise AppError("INVALID_JSON", "request body must be valid JSON", {"error": str(e)})
        if not isinstance(parsed, dict):
            raise AppError("INVALID_JSON_TYPE", "request body must be a JSON object")
        return parsed

    def _match_video_route(self) -> Tuple[str, str] | None:
        # /api/v1/library/videos/{id}/lyrics
        # /api/v1/library/videos/{id}/lyrics/confirmed
        m = re.match(r"^/api/v1/library/videos/([^/]+)/lyrics(?:/(confirmed))?$", self.path)
        if not m:
            return None
        return m.group(1), (m.group(2) or "")

    def _match_jobs_route(self) -> Tuple[str, str] | None:
        if self.path == "/api/v1/jobs":
            return "", "collection"
        m = re.match(r"^/api/v1/jobs/([^/]+)$", self.path)
        if not m:
            return None
        return m.group(1), "item"

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._send_json(HTTPStatus.OK, {"status": "ok"})
            return
        jobs_match = self._match_jobs_route()
        if jobs_match:
            job_id, kind = jobs_match
            if kind == "collection":
                self._send_json(HTTPStatus.NOT_FOUND, {"error": {"code": "NOT_FOUND", "message": "route not found"}})
                return
            try:
                self._send_json(HTTPStatus.OK, self.job_store.get(job_id))
            except AppError as e:
                self._send_json(http_status_for_app_error(e.code), e.to_dict())
            return
        matched = self._match_video_route()
        if not matched:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": {"code": "NOT_FOUND", "message": "route not found"}})
            return
        video_id, suffix = matched
        if suffix:
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {"error": {"code": "NOT_FOUND", "message": "route not found"}},
            )
            return
        try:
            result = self.store.get_lyrics(video_id)
            self._send_json(HTTPStatus.OK, result)
        except AppError as e:
            self._send_json(http_status_for_app_error(e.code), e.to_dict())

    def do_PUT(self) -> None:  # noqa: N802
        matched = self._match_video_route()
        if not matched:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": {"code": "NOT_FOUND", "message": "route not found"}})
            return
        video_id, suffix = matched
        if suffix:
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {"error": {"code": "NOT_FOUND", "message": "route not found"}},
            )
            return
        try:
            payload = self._read_json()
            result = self.store.put_lyrics(video_id, payload)
            self._send_json(HTTPStatus.OK, result)
        except AppError as e:
            self._send_json(http_status_for_app_error(e.code), e.to_dict())

    def do_POST(self) -> None:  # noqa: N802
        jobs_match = self._match_jobs_route()
        if not jobs_match:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": {"code": "NOT_FOUND", "message": "route not found"}})
            return
        _, kind = jobs_match
        if kind != "collection":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": {"code": "NOT_FOUND", "message": "route not found"}})
            return
        try:
            payload = self._read_json()
            video_id = str(payload.get("video_asset_id", "")).strip()
            if not video_id:
                raise AppError("MISSING_VIDEO_ID", "video_asset_id is required")
            words_relative_path = str(payload.get("words_relative_path", "transcript_words.json"))
            video_rel_raw = payload.get("video_relative_path")
            video_rel = str(video_rel_raw).strip() if video_rel_raw is not None else ""

            try:
                lyrics_state = self.store.get_lyrics(video_id)
            except AppError as e:
                self._send_json(http_status_for_app_error(e.code), e.to_dict())
                return
            import_lines = lyrics_state.get("import", {}).get("lines", [])
            confirmed_lines = lyrics_state.get("confirmed", {}).get("lines", import_lines)
            source = lyrics_state.get("source", {})

            job_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc).isoformat()
            output_root = self.data_root / "jobs-run" / job_id
            job_record = {
                "id": job_id,
                "video_asset_id": video_id,
                "status": "running",
                "current_step": "discover_validate",
                "created_at": now,
                "updated_at": now,
                "output_root": str(output_root),
                "error": None,
            }
            self.job_store.create(job_record)

            words_file = self.input_root / words_relative_path
            video_file: Path | None = None
            try:
                if video_rel:
                    video_file = resolve_safe_under_root(self.input_root, video_rel)
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
                updated = self.job_store.update(
                    job_id,
                    {
                        "status": "succeeded",
                        "current_step": "completed",
                        "artifacts": artifacts,
                    },
                )
                self._send_json(HTTPStatus.OK, updated)
            except AppError as e:
                updated = self.job_store.update(
                    job_id,
                    {
                        "status": "failed",
                        "current_step": "failed",
                        "error": {"code": e.code, "message": e.message, "details": e.details},
                    },
                )
                self._send_json(http_status_for_app_error(e.code), updated)
        except AppError as e:
            self._send_json(http_status_for_app_error(e.code), e.to_dict())

    def do_PATCH(self) -> None:  # noqa: N802
        matched = self._match_video_route()
        if not matched:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": {"code": "NOT_FOUND", "message": "route not found"}})
            return
        video_id, suffix = matched
        if suffix != "confirmed":
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {"error": {"code": "NOT_FOUND", "message": "route not found"}},
            )
            return
        try:
            payload = self._read_json()
            lines = payload.get("lines")
            if not isinstance(lines, list):
                raise AppError("INVALID_LINES", "lines must be string[]")
            result = self.store.patch_confirmed(video_id, [str(x) for x in lines])
            self._send_json(HTTPStatus.OK, result)
        except AppError as e:
            self._send_json(http_status_for_app_error(e.code), e.to_dict())


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Local API server (MVP lyrics routes)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", default=8000, type=int)
    p.add_argument("--input-root", default="tests/fixtures/spike", type=Path)
    p.add_argument("--data-root", default=".local-data", type=Path)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    ApiHandler.store = LyricsStore(data_root=args.data_root, input_root=args.input_root)
    ApiHandler.job_store = JobStore(data_root=args.data_root)
    ApiHandler.input_root = args.input_root
    ApiHandler.data_root = args.data_root
    server = ThreadingHTTPServer((args.host, args.port), ApiHandler)
    print(f"API listening on http://{args.host}:{args.port}")
    print(f"input_root={args.input_root}")
    print(f"data_root={args.data_root}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
