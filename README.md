# my-video-automation

Local-first pipeline MVP: lyrics ingest and confirmation, forced alignment to word-level timestamps, and a minimal HTTP API for jobs.

## Requirements

- **Python 3.10+** (stdlib for the API and most tests)
- **ffmpeg** on `PATH` for the **vertical-slice** export (9:16 + burn-in)

## Quick start

1. Start the API (pick free ports; default example uses `8011`):

   ```powershell
   python "src/api/server.py" --host 127.0.0.1 --port 8011 --input-root "tests/fixtures/spike" --data-root ".local-data"
   ```

2. Follow **[docs/DEMO.md](docs/DEMO.md)** for example `PUT` / `PATCH` / `POST` calls and expected artifacts.

**Browse:** `GET /api/v1/config`, `GET /api/v1/library/videos` (scan under `--input-root`), `GET /api/v1/jobs?limit=20`.

`POST /api/v1/jobs` accepts optional **`video_relative_path`** (under `--input-root`). With **ffmpeg** available, the job adds **`douyin_vertical`** in `artifacts` (1080×1920 burn-in). **`words_relative_path`** is also resolved under `input_root` (path-safe).

## Minimal vertical slice (one command)

Given a local video, official lyrics, and word-level ASR JSON (see `tests/fixtures/spike/`), this runs **lyrics align → `subtitles.srt` → 1080×1920 burn-in** into `export/douyin_vertical.mp4`:

```powershell
python "src/video_pipeline.py" vertical-slice --video "D:\path\to\clip.mp4" --lyrics "tests/fixtures/spike/official_lyrics.txt" --words "tests/fixtures/spike/transcript_words.json" --output ".local-data\jobs-run\demo-vs-001"
```

Artifacts land under `--output`: `artifacts/`, `export/`, `logs/`.

## Tests

Automated regression (starts its own server on ephemeral ports):

```powershell
python "tests/api_smoke_test.py"
python "tests/api_failure_test.py"
python "tests/vertical_slice_test.py"
```

## Documentation

- [docs/PRD.md](docs/PRD.md) — MVP scope and acceptance
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — components and data shapes
- [docs/DEMO.md](docs/DEMO.md) — runbook, sample requests, HTTP status reference
