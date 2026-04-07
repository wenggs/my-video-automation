from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORT = 8018
BASE = f"http://127.0.0.1:{PORT}"
VIDEO_ID = "auto-subtitles-video-001"


def http_json(method: str, path: str, payload: dict | None = None, *, timeout_sec: float = 8.0) -> tuple[int, dict]:
    url = BASE + path
    data = None
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url=url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
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


def ensure_smoke_clip_relative_path() -> str | None:
    if not shutil.which("ffmpeg"):
        return None
    spike = ROOT / "tests" / "fixtures" / "spike"
    clip = spike / "_smoke_sample.mp4"
    if not clip.is_file():
        subprocess.run(
            [
                "ffmpeg",
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
                str(clip),
            ],
            check=True,
        )
    return "_smoke_sample.mp4"


def run() -> None:
    clip_rel = ensure_smoke_clip_relative_path()
    if not clip_rel:
        print("SKIP: ffmpeg not on PATH (auto subtitles test requires sample video)")
        return

    data_root = ROOT / ".local-data-auto-subtitles"
    if data_root.exists():
        shutil.rmtree(data_root)
    data_root.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    env["AUTO_SUBTITLES_FAKE"] = "1"
    env["AUTO_SUBTITLES_FAKE_SLEEP_MS"] = "1200"
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
    server = subprocess.Popen(server_cmd, cwd=str(ROOT), env=env)
    try:
        wait_health()
        # invalid: missing video_relative_path
        status, payload = http_json(
            "POST",
            f"/api/v1/library/videos/{VIDEO_ID}/lyrics/auto-generate",
            {"model": "small", "language": "zh"},
        )
        assert status == 400, payload
        assert payload.get("error", {}).get("code") == "VIDEO_RELATIVE_PATH_REQUIRED", payload

        # invalid: path traversal
        status, payload = http_json(
            "POST",
            f"/api/v1/library/videos/{VIDEO_ID}/lyrics/auto-generate",
            {"video_relative_path": "..\\..\\README.md", "model": "small", "language": "zh"},
        )
        assert status == 400, payload
        assert payload.get("error", {}).get("code") == "RELATIVE_PATH_INVALID", payload

        # invalid: video not found under input_root
        status, payload = http_json(
            "POST",
            f"/api/v1/library/videos/{VIDEO_ID}/lyrics/auto-generate",
            {"video_relative_path": "not_exists_demo.mp4", "model": "small", "language": "zh"},
        )
        assert status == 422, payload
        assert payload.get("error", {}).get("code") == "VIDEO_FILE_NOT_FOUND", payload

        # happy path
        status, payload = http_json(
            "POST",
            f"/api/v1/library/videos/{VIDEO_ID}/lyrics/auto-generate",
            {"video_relative_path": clip_rel, "model": "small", "language": "zh"},
        )
        assert status == 200, payload
        assert payload.get("video_asset_id") == VIDEO_ID, payload
        assert len(payload.get("import", {}).get("lines", [])) > 0, payload
        assert payload.get("source", {}).get("mode") == "pasted", payload
        srt_path = payload.get("auto_generate", {}).get("srt_path")
        assert srt_path and Path(str(srt_path)).exists(), payload
        assert payload.get("auto_generate", {}).get("details", {}).get("elapsed_sec") is not None, payload

        status, payload = http_json("GET", f"/api/v1/library/videos/{VIDEO_ID}/lyrics")
        assert status == 200, payload
        assert len(payload.get("confirmed", {}).get("lines", [])) > 0, payload

        # concurrency guard: second request should get 429 while first is running
        holder: dict = {}

        def long_req() -> None:
            st, pl = http_json(
                "POST",
                f"/api/v1/library/videos/{VIDEO_ID}/lyrics/auto-generate",
                {"video_relative_path": clip_rel, "model": "small", "language": "zh"},
                timeout_sec=10.0,
            )
            holder["status"] = st
            holder["payload"] = pl

        t = threading.Thread(target=long_req, daemon=True)
        t.start()
        time.sleep(0.15)
        status, payload = http_json(
            "POST",
            f"/api/v1/library/videos/{VIDEO_ID}/lyrics/auto-generate",
            {"video_relative_path": clip_rel, "model": "small", "language": "zh"},
        )
        assert status == 429, payload
        assert payload.get("error", {}).get("code") == "AUTO_SUBTITLES_BUSY", payload
        t.join(timeout=6.0)
        assert holder.get("status") == 200, holder.get("payload")

        print("API auto subtitles test passed.")
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == "__main__":
    run()

