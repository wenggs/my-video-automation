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
PORT = 8015
BASE = f"http://127.0.0.1:{PORT}"
VIDEO_ID = "cancel-video-001"

FIXTURES = ROOT / "tests" / "fixtures" / "spike"


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


def ensure_cancel_clip_relative_path() -> str | None:
    if not shutil.which("ffmpeg"):
        return None
    clip = FIXTURES / "_smoke_sample_cancel.mp4"
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
    return "_smoke_sample_cancel.mp4"


def run() -> None:
    if not shutil.which("ffmpeg"):
        print("SKIP: ffmpeg not on PATH")
        return

    data_root = ROOT / ".local-data-cancel"
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
        str(FIXTURES),
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

        clip_rel = ensure_cancel_clip_relative_path()
        assert clip_rel

        # 3) POST job (202 Accepted)
        status, payload = http_json(
            "POST",
            "/api/v1/jobs",
            {
                "video_asset_id": VIDEO_ID,
                "words_relative_path": "transcript_words.json",
                "video_relative_path": clip_rel,
            },
        )
        assert status == 202, payload
        job_id = payload.get("id")
        assert job_id

        # 4) Wait until worker actually starts ("running"), then cancel.
        deadline = time.time() + 30.0
        while time.time() < deadline:
            status, job = http_json("GET", f"/api/v1/jobs/{job_id}")
            assert status == 200, job
            st = job.get("status")
            if st == "running":
                break
            if st in ("succeeded", "failed", "cancelled"):
                raise AssertionError(f"too late: job already terminal={st}: {job}")
            time.sleep(0.1)
        else:
            raise AssertionError("job did not enter running state in time")

        cancel_status, cancel_payload = http_json("POST", f"/api/v1/jobs/{job_id}/cancel")
        assert cancel_status == 200, cancel_payload
        assert cancel_payload.get("status") == "cancelled", cancel_payload

        # 5) Poll until terminal cancelled
        deadline = time.time() + 60.0
        while time.time() < deadline:
            status, job = http_json("GET", f"/api/v1/jobs/{job_id}")
            assert status == 200, job
            if job.get("status") == "cancelled":
                break
            if job.get("status") in ("succeeded", "failed"):
                raise AssertionError(f"cancel did not win: status={job.get('status')}: {job}")
            time.sleep(0.15)

        status, job = http_json("GET", f"/api/v1/jobs/{job_id}")
        assert status == 200, job
        assert job.get("status") == "cancelled", job

        # 6) GET logs (tail) should exist
        logs_status, logs_payload = http_json("GET", f"/api/v1/jobs/{job_id}/logs?tail=30")
        assert logs_status == 200, logs_payload
        assert logs_payload.get("line_count", 0) > 0, logs_payload

        print("API cancel + logs test passed.")
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == "__main__":
    run()

