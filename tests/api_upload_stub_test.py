from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPIKE = ROOT / "tests" / "fixtures" / "spike"
PORT = 8016
BASE = f"http://127.0.0.1:{PORT}"
VIDEO_ID = "upload-stub-video-001"


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
    clip = SPIKE / "_smoke_sample.mp4"
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


def wait_job(job_id: str, *, timeout_sec: float = 120.0, poll_sec: float = 0.15) -> dict:
    deadline = time.time() + timeout_sec
    last: dict = {}
    while time.time() < deadline:
        status, payload = http_json("GET", f"/api/v1/jobs/{job_id}")
        assert status == 200, payload
        last = payload
        st = payload.get("status")
        if st in ("succeeded", "failed", "cancelled"):
            if st != "succeeded":
                raise AssertionError(f"job failed: {payload}")
            return payload
        time.sleep(poll_sec)
    raise AssertionError(f"job did not finish in {timeout_sec}s: {last}")


def run() -> None:
    if not shutil.which("ffmpeg"):
        print("SKIP: ffmpeg not on PATH (upload stub test requires export video)")
        return

    data_root = ROOT / ".local-data-upload-stub"
    if data_root.exists():
        shutil.rmtree(data_root)
    data_root.mkdir(parents=True, exist_ok=True)

    server_cmd = [
        sys.executable,
        str(ROOT / "src" / "api" / "server.py"),
        "--host",
        "127.0.0.1",
        "--port",
        str(PORT),
        "--input-root",
        str(SPIKE),
        "--data-root",
        str(data_root),
    ]
    server = subprocess.Popen(server_cmd, cwd=str(ROOT))
    try:
        wait_health()

        # 1) PUT lyrics import
        status, payload = http_json(
            "PUT",
            f"/api/v1/library/videos/{VIDEO_ID}/lyrics",
            {"mode": "sidecar_file", "sidecar_relative_path": "official_lyrics.txt", "preserve_confirmed": False},
        )
        assert status == 200, payload

        # 2) PATCH confirmed micro-tuning
        status, payload = http_json(
            "PATCH",
            f"/api/v1/library/videos/{VIDEO_ID}/lyrics/confirmed",
            {"lines": ["你说风吹过我们的夏天（冒烟测试）", "人潮里我听见你的名字", "这一刻全场都在合唱"]},
        )
        assert status == 200, payload

        clip_rel = ensure_smoke_clip_relative_path()
        assert clip_rel

        # 3) POST job
        status, payload = http_json(
            "POST",
            "/api/v1/jobs",
            {"video_asset_id": VIDEO_ID, "words_relative_path": "transcript_words.json", "video_relative_path": clip_rel},
        )
        assert status == 202, payload
        job_id = payload.get("id")
        assert job_id

        job = wait_job(job_id)
        assert job.get("status") == "succeeded", job
        assert (job.get("artifacts") or {}).get("douyin_vertical"), job

        # 4) Prepare publish (stub)
        status, payload = http_json(
            "POST",
            f"/api/v1/jobs/{job_id}/publish/douyin/prepare",
            {},
            timeout_sec=90.0,
        )
        assert status == 200, payload
        publish = payload.get("publish", {}).get("douyin", {})
        assert publish.get("state") in ("upload_prepared", "upload_prepared_manual"), payload
        assert publish.get("draft_url"), payload

        # 5) Confirm publish (stub)
        status, payload = http_json(
            "POST",
            f"/api/v1/jobs/{job_id}/publish/douyin/confirm",
            {},
        )
        assert status == 200, payload
        publish = payload.get("publish", {}).get("douyin", {})
        assert publish.get("state") == "published", payload

        print("API upload stub test passed.")
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == "__main__":
    run()

