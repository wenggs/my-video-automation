from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORT = 8014
BASE = f"http://127.0.0.1:{PORT}"


def http_json(method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
    url = BASE + path
    data = None
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url=url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        parsed = json.loads(body) if body else {}
        return e.code, parsed


def wait_health(max_wait_sec: float = 10.0) -> None:
    started = time.time()
    while time.time() - started < max_wait_sec:
        try:
            status, payload = http_json("GET", "/health")
            if status == 200 and payload.get("status") == "ok":
                return
        except Exception:
            pass
        time.sleep(0.2)
    raise RuntimeError("API did not become healthy in time")


def run() -> None:
    data_root = ROOT / ".local-data-failure"
    data_root.mkdir(parents=True, exist_ok=True)

    server_cmd = [
        sys.executable,
        str(ROOT / "src" / "api" / "server.py"),
        "--host",
        "127.0.0.1",
        "--port",
        str(PORT),
        "--input-root",
        str(ROOT / "tests" / "fixtures" / "spike"),
        "--data-root",
        str(data_root),
    ]
    server = subprocess.Popen(server_cmd, cwd=str(ROOT))
    try:
        wait_health()

        # GET job unknown -> 404
        status, payload = http_json("GET", f"/api/v1/jobs/{uuid.uuid4()}")
        assert status == 404, payload
        assert payload.get("error", {}).get("code") == "JOB_NOT_FOUND"

        # GET lyrics unknown -> 404
        status, payload = http_json("GET", "/api/v1/library/videos/no-such-video/lyrics")
        assert status == 404, payload
        assert payload.get("error", {}).get("code") == "LYRICS_STATE_NOT_FOUND"

        # POST job without importing lyrics first -> 404 (no job row)
        status, payload = http_json(
            "POST",
            "/api/v1/jobs",
            {"video_asset_id": "never-imported-001", "words_relative_path": "transcript_words.json"},
        )
        assert status == 404, payload
        assert payload.get("error", {}).get("code") == "LYRICS_STATE_NOT_FOUND"
        assert "id" not in payload

        # POST job with bad words path -> job created then pipeline fails -> 422
        vid = "failure-video-001"
        status, _ = http_json(
            "PUT",
            f"/api/v1/library/videos/{vid}/lyrics",
            {
                "mode": "sidecar_file",
                "sidecar_relative_path": "official_lyrics.txt",
                "preserve_confirmed": False,
            },
        )
        assert status == 200

        status, payload = http_json(
            "POST",
            "/api/v1/jobs",
            {"video_asset_id": vid, "words_relative_path": "missing_words.json"},
        )
        assert status == 422, payload
        assert payload.get("status") == "failed"
        assert payload.get("error", {}).get("code") == "WORDS_FILE_NOT_FOUND"
        job_id = payload.get("id")
        assert job_id

        # GET failed job still retrievable
        status, payload = http_json("GET", f"/api/v1/jobs/{job_id}")
        assert status == 200
        assert payload.get("status") == "failed"

        # POST job with missing video file -> 422 after lyrics step succeeds
        status, payload = http_json(
            "POST",
            "/api/v1/jobs",
            {
                "video_asset_id": vid,
                "words_relative_path": "transcript_words.json",
                "video_relative_path": "this_video_does_not_exist.mp4",
            },
        )
        assert status == 422, payload
        assert payload.get("status") == "failed"
        assert payload.get("error", {}).get("code") == "VIDEO_FILE_NOT_FOUND"

        # Path escapes input_root -> 400, job failed
        status, payload = http_json(
            "POST",
            "/api/v1/jobs",
            {
                "video_asset_id": vid,
                "words_relative_path": "transcript_words.json",
                "video_relative_path": "..\\official_lyrics.txt",
            },
        )
        assert status == 400, payload
        assert payload.get("status") == "failed"
        assert payload.get("error", {}).get("code") == "RELATIVE_PATH_INVALID"

        # words_relative_path escapes input_root -> 400
        status, payload = http_json(
            "POST",
            "/api/v1/jobs",
            {
                "video_asset_id": vid,
                "words_relative_path": "..\\..\\README.md",
            },
        )
        assert status == 400, payload
        assert payload.get("status") == "failed"
        assert payload.get("error", {}).get("code") == "RELATIVE_PATH_INVALID"

        print("API failure regression passed.")
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == "__main__":
    run()
