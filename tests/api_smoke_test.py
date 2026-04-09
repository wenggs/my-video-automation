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
SMOKE_CLIP = SPIKE / "_smoke_sample.mp4"


def ensure_smoke_clip_relative_path() -> str | None:
    if not shutil.which("ffmpeg"):
        return None
    if not SMOKE_CLIP.is_file():
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
                str(SMOKE_CLIP),
            ],
            check=True,
        )
    return "_smoke_sample.mp4"


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


def http_status(method: str, path: str) -> int:
    url = BASE + path
    req = urllib.request.Request(url=url, method=method)
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            _ = resp.read()  # binary-safe endpoint support
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code


def wait_job(
    job_id: str,
    *,
    timeout_sec: float = 120.0,
    poll_sec: float = 0.15,
) -> tuple[str, dict]:
    deadline = time.time() + timeout_sec
    last: dict = {}
    while time.time() < deadline:
        status, payload = http_json("GET", f"/api/v1/jobs/{job_id}")
        assert status == 200, payload
        last = payload
        st = payload.get("status")
        if st in ("succeeded", "failed"):
            return str(st), payload
        time.sleep(poll_sec)
    raise AssertionError(f"job {job_id} did not finish in {timeout_sec}s: {last}")


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
        str(ROOT / "tests" / "fixtures" / "spike"),
        "--data-root",
        str(data_root),
    ]
    server = subprocess.Popen(server_cmd, cwd=str(ROOT))
    try:
        wait_health()

        status, payload = http_json("GET", "/api/v1/config")
        assert status == 200, payload
        assert Path(payload["input_root"]).exists()
        assert "data_root" in payload

        status, payload = http_json("GET", "/api/v1/library/videos")
        assert status == 200, payload
        assert isinstance(payload.get("items"), list)
        assert "count" in payload

        # 0.5) PATCH/GET tags
        status, payload = http_json(
            "PATCH",
            f"/api/v1/library/videos/{VIDEO_ID}/tags",
            {"tags": ["concert", "live", "concert"]},
        )
        assert status == 200, payload
        assert payload.get("tags_confirmed") == ["concert", "live"], payload
        status, payload = http_json("GET", f"/api/v1/library/videos/{VIDEO_ID}/tags")
        assert status == 200, payload
        assert payload.get("tags_confirmed") == ["concert", "live"], payload
        assert isinstance(payload.get("tags_suggested"), list), payload
        status, payload = http_json(
            "POST",
            f"/api/v1/library/videos/{VIDEO_ID}/tags/suggest",
            {"video_relative_path": "演唱会_live_clip.mp4", "hint_text": "official"},
        )
        assert status == 200, payload
        sug = payload.get("suggested_tags") or []
        assert "concert" in sug and "live" in sug, payload
        details = payload.get("suggested_details") or []
        assert any((x.get("tag") == "concert" and str(x.get("reason", "")).startswith("keyword:")) for x in details), payload
        status, payload = http_json("GET", f"/api/v1/library/videos/{VIDEO_ID}/tags")
        assert status == 200, payload
        assert any(x in (payload.get("tags_suggested") or []) for x in ("concert", "live")), payload
        status, payload = http_json(
            "PATCH",
            f"/api/v1/library/videos/{VIDEO_ID}/tags/suggested",
            {"tags": ["music"]},
        )
        assert status == 200, payload
        assert payload.get("tags_suggested") == ["music"], payload

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

        clip_rel = ensure_smoke_clip_relative_path()
        job_body: dict = {"video_asset_id": VIDEO_ID, "words_relative_path": "transcript_words.json"}
        if clip_rel:
            job_body["video_relative_path"] = clip_rel

        # 3) POST job (202 Accepted, worker runs in background)
        status, payload = http_json(
            "POST",
            "/api/v1/jobs",
            job_body,
        )
        assert status == 202, payload
        job_id = payload.get("id")
        assert job_id
        assert payload.get("status") in ("queued", "running", "succeeded"), payload

        final_st, payload = (
            (payload.get("status"), payload)
            if payload.get("status") in ("succeeded", "failed")
            else wait_job(job_id)
        )
        assert final_st == "succeeded", payload
        artifacts = payload.get("artifacts", {})
        for key in ("official_lyrics", "lyrics_confirmed", "aligned_subtitles", "job_log"):
            p = artifacts.get(key)
            assert p, f"missing artifact key={key}"
            assert Path(p).exists(), f"artifact file not found: {p}"
        if clip_rel:
            dv = artifacts.get("douyin_vertical")
            assert dv, "expected douyin_vertical artifact when video_relative_path is set"
            assert Path(str(dv)).exists(), dv
            status = http_status("GET", f"/api/v1/jobs/{job_id}/artifacts/douyin_vertical")
            assert status == 200

        # 4) GET job by id (same snapshot as terminal poll)
        status, snapshot = http_json("GET", f"/api/v1/jobs/{job_id}")
        assert status == 200, snapshot
        assert snapshot.get("status") == "succeeded"

        # 5) GET job logs (tail)
        status, logs_payload = http_json("GET", f"/api/v1/jobs/{job_id}/logs?tail=50")
        assert status == 200, logs_payload
        assert logs_payload.get("line_count", 0) > 0, logs_payload
        # First lines usually contain "start lyrics flow"
        assert any("start lyrics flow" in line for line in logs_payload.get("lines", [])), logs_payload

        status, job_list = http_json("GET", "/api/v1/jobs?limit=5")
        assert status == 200, job_list
        assert any(j.get("id") == job_id for j in job_list.get("items", [])), job_list

        print("API smoke test passed.")
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == "__main__":
    run()
