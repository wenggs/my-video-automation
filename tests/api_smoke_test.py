from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PORT = 8012
BASE = f"http://127.0.0.1:{PORT}"
VIDEO_ID = "smoke-video-001"


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
    data_root = ROOT / ".local-data-smoke"
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

        # 1) PUT lyrics import
        status, payload = http_json(
            "PUT",
            f"/api/v1/library/videos/{VIDEO_ID}/lyrics",
            {
                "mode": "sidecar_file",
                "sidecar_relative_path": "official_lyrics.txt",
                "preserve_confirmed": False,
            },
        )
        assert status == 200, payload
        assert payload.get("video_asset_id") == VIDEO_ID

        # 2) PATCH confirmed micro-tuning
        status, payload = http_json(
            "PATCH",
            f"/api/v1/library/videos/{VIDEO_ID}/lyrics/confirmed",
            {"lines": ["你说风吹过我们的夏天（冒烟测试）", "人潮里我听见你的名字", "这一刻全场都在合唱"]},
        )
        assert status == 200, payload
        assert payload.get("confirmed", {}).get("changed") is True

        # 3) POST job
        status, payload = http_json(
            "POST",
            "/api/v1/jobs",
            {"video_asset_id": VIDEO_ID, "words_relative_path": "transcript_words.json"},
        )
        assert status == 200, payload
        assert payload.get("status") == "succeeded", payload
        job_id = payload.get("id")
        assert job_id

        # 4) GET job by id
        status, payload = http_json("GET", f"/api/v1/jobs/{job_id}")
        assert status == 200, payload
        assert payload.get("status") == "succeeded", payload
        artifacts = payload.get("artifacts", {})
        for key in ("official_lyrics", "lyrics_confirmed", "aligned_subtitles", "job_log"):
            p = artifacts.get(key)
            assert p, f"missing artifact key={key}"
            assert Path(p).exists(), f"artifact file not found: {p}"

        print("API smoke test passed.")
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == "__main__":
    run()
