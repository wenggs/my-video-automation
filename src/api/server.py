from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import uuid
import mimetypes
from datetime import datetime, timezone
from urllib.parse import parse_qs
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Tuple

# Ensure `src/` is importable when launching this file directly.
sys.path.append(str(Path(__file__).resolve().parents[1]))

from common.errors import AppError, http_status_for_app_error
from services.job_execution import run_lyrics_export_job
from services.library_scan import scan_video_files
from services.upload_douyin_service import prepare_douyin_upload
from storage.job_store import JobStore
from storage.lyrics_store import LyricsStore


class ApiHandler(BaseHTTPRequestHandler):
    store: LyricsStore
    job_store: JobStore
    input_root: Path
    data_root: Path

    # In-flight jobs = queued + running (best-effort based on latest 500 job records).
    MAX_INFLIGHT_JOBS = 5
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    _UI_DIR = _PROJECT_ROOT / "web" / "ui"

    def _path_only(self) -> str:
        return self.path.split("?", 1)[0]

    def _query_limit(self, default: int = 100, *, cap: int = 500) -> int:
        if "?" not in self.path:
            return default
        qs = parse_qs(self.path.split("?", 1)[1], keep_blank_values=False)
        raw = (qs.get("limit") or [None])[0]
        if raw is None:
            return default
        try:
            n = int(raw)
        except ValueError:
            return default
        return max(1, min(n, cap))

    def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, status: int, text: str, content_type: str = "text/plain; charset=utf-8") -> None:
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _try_send_ui_index(self) -> bool:
        po = self._path_only()
        if po not in ("/", "/ui", "/ui/"):
            return False
        index_path = self._UI_DIR / "index.html"
        if not index_path.exists():
            self._send_text(HTTPStatus.NOT_FOUND, "UI index.html not found", "text/plain; charset=utf-8")
            return True
        content = index_path.read_text(encoding="utf-8")
        self._send_text(HTTPStatus.OK, content, "text/html; charset=utf-8")
        return True

    def _try_send_ui_static(self) -> bool:
        po = self._path_only()
        if not po.startswith("/ui/"):
            return False
        rel = po[len("/ui/"):]
        if not rel or "/" in rel or "\\" in rel or ".." in rel:
            self._send_text(HTTPStatus.NOT_FOUND, "UI asset not found", "text/plain; charset=utf-8")
            return True
        fp = (self._UI_DIR / rel).resolve()
        try:
            fp.relative_to(self._UI_DIR.resolve())
        except ValueError:
            self._send_text(HTTPStatus.NOT_FOUND, "UI asset not found", "text/plain; charset=utf-8")
            return True
        if not fp.exists() or not fp.is_file():
            self._send_text(HTTPStatus.NOT_FOUND, "UI asset not found", "text/plain; charset=utf-8")
            return True
        data = fp.read_bytes()
        ctype = mimetypes.guess_type(str(fp))[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        return True

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

    def _match_video_route(self, path_only: str) -> Tuple[str, str] | None:
        # /api/v1/library/videos/{id}/lyrics
        # /api/v1/library/videos/{id}/lyrics/confirmed
        m = re.match(r"^/api/v1/library/videos/([^/]+)/lyrics(?:/(confirmed))?$", path_only)
        if not m:
            return None
        return m.group(1), (m.group(2) or "")

    def _match_jobs_route(self, path_only: str) -> Tuple[str, str] | None:
        if path_only == "/api/v1/jobs":
            return "", "collection"
        m = re.match(r"^/api/v1/jobs/([^/]+)$", path_only)
        if not m:
            return None
        return m.group(1), "item"

    def do_GET(self) -> None:  # noqa: N802
        if self._try_send_ui_index():
            return
        if self._try_send_ui_static():
            return
        if self._path_only() == "/health":
            self._send_json(HTTPStatus.OK, {"status": "ok"})
            return
        po = self._path_only()
        if po == "/api/v1/config":
            self._send_json(
                HTTPStatus.OK,
                {
                    "input_root": str(self.input_root.resolve()),
                    "data_root": str(self.data_root.resolve()),
                },
            )
            return
        if po == "/api/v1/library/videos":
            try:
                items = scan_video_files(self.input_root)
                self._send_json(HTTPStatus.OK, {"items": items, "count": len(items)})
            except AppError as e:
                self._send_json(http_status_for_app_error(e.code), e.to_dict())
            return

        # GET /api/v1/jobs/{id}/artifacts/{name}
        m_artifact = re.match(r"^/api/v1/jobs/([^/]+)/artifacts/([^/]+)$", po)
        if m_artifact:
            job_id, artifact_name = m_artifact.group(1), m_artifact.group(2)
            try:
                job = self.job_store.get(job_id)
                artifacts = job.get("artifacts") or {}
                ap = artifacts.get(artifact_name)
                if not ap:
                    raise AppError(
                        "JOB_ARTIFACT_NOT_FOUND",
                        "job artifact not found",
                        {"job_id": job_id, "artifact": artifact_name},
                    )
                fp = Path(str(ap))
                if not fp.exists() or not fp.is_file():
                    raise AppError(
                        "JOB_ARTIFACT_NOT_FOUND",
                        "artifact file not found on disk",
                        {"job_id": job_id, "artifact": artifact_name, "path": str(fp)},
                    )
                content = fp.read_bytes()
                ctype = mimetypes.guess_type(str(fp))[0] or "application/octet-stream"
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Content-Disposition", f"inline; filename=\"{fp.name}\"")
                self.end_headers()
                self.wfile.write(content)
            except AppError as e:
                self._send_json(http_status_for_app_error(e.code), e.to_dict())
            return

        # GET /api/v1/jobs/{id}/logs?tail=200
        m_logs = re.match(r"^/api/v1/jobs/([^/]+)/logs$", po)
        if m_logs:
            job_id = m_logs.group(1)
            tail = 200
            if "?" in self.path:
                qs = parse_qs(self.path.split("?", 1)[1], keep_blank_values=False)
                raw_tail = (qs.get("tail") or [None])[0]
                if raw_tail is not None:
                    try:
                        n = int(raw_tail)
                        tail = max(0, min(n, 2000))
                    except ValueError:
                        tail = 200
            try:
                job = self.job_store.get(job_id)
                output_root = Path(str(job.get("output_root", "")))
                log_path = output_root / "logs" / "job.log"
                if not log_path.exists():
                    raise AppError("JOB_LOG_NOT_FOUND", "job log not found", {"job_id": job_id})
                lines = log_path.read_text(encoding="utf-8").splitlines()
                tail_lines = lines[-tail:] if tail > 0 else []
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "job_id": job_id,
                        "tail": tail,
                        "line_count": len(lines),
                        "lines": tail_lines,
                    },
                )
            except AppError as e:
                self._send_json(http_status_for_app_error(e.code), e.to_dict())
            return

        jobs_match = self._match_jobs_route(po)
        if jobs_match:
            job_id, kind = jobs_match
            if kind == "collection":
                limit = self._query_limit(default=100)
                items = self.job_store.list_recent(limit=limit)
                self._send_json(HTTPStatus.OK, {"items": items, "count": len(items)})
                return
            try:
                self._send_json(HTTPStatus.OK, self.job_store.get(job_id))
            except AppError as e:
                self._send_json(http_status_for_app_error(e.code), e.to_dict())
            return
        matched = self._match_video_route(po)
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
        matched = self._match_video_route(self._path_only())
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
        po = self._path_only()

        # POST /api/v1/jobs/{id}/publish/{platform}/prepare
        m_prepare = re.match(r"^/api/v1/jobs/([^/]+)/publish/([^/]+)/prepare$", po)
        if m_prepare:
            job_id, platform = m_prepare.group(1), m_prepare.group(2)
            self._handle_publish(job_id=job_id, platform=platform, action="prepare")
            return

        # POST /api/v1/jobs/{id}/publish/{platform}/confirm
        m_confirm = re.match(r"^/api/v1/jobs/([^/]+)/publish/([^/]+)/confirm$", po)
        if m_confirm:
            job_id, platform = m_confirm.group(1), m_confirm.group(2)
            self._handle_publish(job_id=job_id, platform=platform, action="confirm")
            return

        # POST /api/v1/jobs/{id}/cancel
        m_cancel = re.match(r"^/api/v1/jobs/([^/]+)/cancel$", po)
        if m_cancel:
            job_id = m_cancel.group(1)
            try:
                job = self.job_store.get(job_id)
                st = str(job.get("status", ""))
                if st in ("succeeded", "failed", "cancelled"):
                    self._send_json(
                        HTTPStatus.CONFLICT,
                        {"error": {"code": "JOB_ALREADY_TERMINAL", "message": f"job status is {st}"}},
                    )
                    return
                updated = self.job_store.update(
                    job_id,
                    {"status": "cancelled", "current_step": "cancelled", "error": None},
                )
                self._send_json(HTTPStatus.OK, updated)
            except AppError as e:
                self._send_json(http_status_for_app_error(e.code), e.to_dict())
            return

        jobs_match = self._match_jobs_route(po)
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
            words_relative_path = str(payload.get("words_relative_path", "transcript_words.json")).strip()
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

            # Best-effort inflight cap to avoid runaway background tasks.
            recent_jobs = self.job_store.list_recent(limit=500)
            inflight = sum(1 for j in recent_jobs if j.get("status") in ("queued", "running"))
            if inflight >= self.MAX_INFLIGHT_JOBS:
                self._send_json(
                    HTTPStatus.TOO_MANY_REQUESTS,
                    {"error": {"code": "JOB_QUEUE_FULL", "message": "too many queued/running jobs"}},
                )
                return

            job_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc).isoformat()
            output_root = self.data_root / "jobs-run" / job_id
            job_record = {
                "id": job_id,
                "video_asset_id": video_id,
                "status": "queued",
                "current_step": "queued",
                "created_at": now,
                "updated_at": now,
                "output_root": str(output_root),
                "error": None,
            }
            self.job_store.create(job_record)

            job_store = self.job_store
            input_root = self.input_root
            data_root = self.data_root

            def worker() -> None:
                run_lyrics_export_job(
                    job_store=job_store,
                    input_root=input_root,
                    data_root=data_root,
                    job_id=job_id,
                    words_relative_path=words_relative_path,
                    video_rel=video_rel,
                    import_lines=import_lines,
                    confirmed_lines=confirmed_lines,
                    source=source,
                )

            threading.Thread(target=worker, daemon=True).start()
            self._send_json(HTTPStatus.ACCEPTED, self.job_store.get(job_id))
        except AppError as e:
            self._send_json(http_status_for_app_error(e.code), e.to_dict())

    def _handle_publish(self, *, job_id: str, platform: str, action: str) -> None:
        try:
            job = self.job_store.get(job_id)
        except AppError as e:
            self._send_json(http_status_for_app_error(e.code), e.to_dict())
            return

        if platform != "douyin":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": {"code": "NOT_FOUND", "message": "publish platform not supported"}})
            return

        if job.get("status") != "succeeded":
            self._send_json(
                HTTPStatus.CONFLICT,
                {"error": {"code": "JOB_NOT_SUCCEEDED", "message": "job must be succeeded before publish actions"}},
            )
            return

        artifacts = job.get("artifacts") or {}
        video_path = artifacts.get("douyin_vertical")
        if not video_path:
            self._send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                {"error": {"code": "ARTIFACT_MISSING", "message": "missing artifacts.douyin_vertical for douyin publish"}},
            )
            return

        now = datetime.now(timezone.utc).isoformat()
        publish = job.get("publish") or {}
        douyin = publish.get("douyin") or {}

        if action == "prepare":
            prep = prepare_douyin_upload(video_path=Path(str(video_path)), data_root=self.data_root)
            douyin = {
                "state": prep.state,
                "prepared_at": now,
                "draft_url": prep.details.get("upload_url"),
                "video_path": video_path,
                "manual_confirm_required": True,
                "prepare_details": prep.details,
            }
            publish["douyin"] = douyin
            updated = self.job_store.update(job_id, {"publish": publish})
            self._send_json(HTTPStatus.OK, updated)
            return

        if action == "confirm":
            st = str(douyin.get("state") or "")
            if st not in ("upload_prepared", "upload_prepared_manual"):
                self._send_json(
                    HTTPStatus.CONFLICT,
                    {"error": {"code": "PUBLISH_NOT_PREPARED", "message": "call prepare first"}},
                )
                return
            douyin["state"] = "published"
            douyin["published_at"] = now
            douyin["published_via"] = "ui_stub"
            publish["douyin"] = douyin
            updated = self.job_store.update(job_id, {"publish": publish})
            self._send_json(HTTPStatus.OK, updated)
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"error": {"code": "NOT_FOUND", "message": "unknown publish action"}})

    def do_PATCH(self) -> None:  # noqa: N802
        matched = self._match_video_route(self._path_only())
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
