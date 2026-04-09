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

2. Open UI:

   ```text
   http://127.0.0.1:8011/ui
   ```

3. Follow **[docs/DEMO.md](docs/DEMO.md)** for API samples and end-to-end walkthrough.

**Browse:** `GET /api/v1/config`, `GET /api/v1/library/videos` (scan under `--input-root`), `GET /api/v1/jobs?limit=20`.

UI: open `http://127.0.0.1:8011/ui` to view recent jobs, create job, filter by status, and run Douyin upload prepare/confirm (manual-confirm flow).
`DOUYIN_UPLOAD_MODE=auto` (optional) attempts Playwright-based upload prepare with persistent session; otherwise it falls back to manual browser flow.
`DOUYIN_UPLOAD_STRICT=1` (optional) disables manual fallback on prepare failure and returns structured `prepare_failed` state.

`POST /api/v1/jobs` returns **202** and runs the pipeline in a **background thread**; poll **`GET /api/v1/jobs/{id}`** for `queued` → `running` → `succeeded` or `failed`. Optional **`video_relative_path`** (under `--input-root`) triggers **ffmpeg** **`douyin_vertical`** in `artifacts`. **`words_relative_path`** is path-safe under `input_root`.

## Douyin upload Playwright PoC

Spike script (for selector/session validation before full adapter hardening):

```powershell
python "src/spikes/douyin_upload_playwright_poc.py" --video "D:\path\to\douyin_vertical.mp4"
```

If Playwright is missing:

```powershell
pip install playwright
playwright install chromium
```

## Current demo capabilities

- Lyrics ingest + confirmed-lyrics update (`PUT/PATCH /api/v1/library/videos/{id}/lyrics*`)
- Minimal tags API for videos (`GET/PATCH /api/v1/library/videos/{id}/tags`) + list filter (`GET /api/v1/library/videos?tag=...`)
- Auto lyrics bootstrap from video (`POST /api/v1/library/videos/{id}/lyrics/auto-generate`)
- Auto subtitles concurrency guard (`429 AUTO_SUBTITLES_BUSY` when in-flight ASR limit reached)
- Auto subtitles best-effort cancellation by `request_id` (`/lyrics/auto-generate/cancel`)
- Auto-segments review helper (`GET /api/v1/library/videos/{id}/lyrics/auto-segments`) with `needs_review` hints
- Subtitle review rules config (`GET/PUT /api/v1/config/subtitles-review`)
- Async jobs (`POST /api/v1/jobs` returns `202`, then poll `GET /api/v1/jobs/{id}`)
- Vertical export path (`video_relative_path`) with 9:16 burn-in artifact (`douyin_vertical`)
- Job logs and cancel (`GET /api/v1/jobs/{id}/logs`, `POST /api/v1/jobs/{id}/cancel`)
- Douyin publish prepare/confirm flow with structured failure states/details
- UI operations: tags load/save + job-tag filter, auto-generate lyrics (quality/model/language), retry/cancel auto-generate, request_id display, minimal subtitle review/save, auto metrics display, create job, auto-refresh, status filter, error detail expand/copy, workspace config panel

## One-pass demo order

1. Start API server (`src/api/server.py`) and open `/ui`.
2. In UI, confirm `input_root/data_root` values in the top config panel.
3. Create a job in the Create form (`video_asset_id`, `words_relative_path`, optional `video_relative_path`).
4. Watch job transitions with auto-refresh; use filter (`running` / `failed` / `succeeded`) as needed.
5. On succeeded job, open/download `douyin_vertical` artifact from the row.
6. Run publish flow: `Prepare upload` then `Confirm publish` (optional `platform_post_id` / `published_url`).
7. If failure appears, expand details and copy JSON with the row buttons for debugging.

## Minimal vertical slice (one command)

Given a local video, official lyrics, and word-level ASR JSON (see `tests/fixtures/spike/`), this runs **lyrics align → trim master → shift SRT → 1080×1920 burn-in** into `export/douyin_vertical.mp4`:

```powershell
python "src/video_pipeline.py" vertical-slice --video "D:\path\to\clip.mp4" --lyrics "tests/fixtures/spike/official_lyrics.txt" --words "tests/fixtures/spike/transcript_words.json" --output ".local-data\jobs-run\demo-vs-001"
```

Artifacts land under `--output`: `artifacts/` (`subtitles.srt`, `subtitles_burnin.srt`), `edited/` (`edited_master.mp4`), `export/`, `logs/`.

## Tests

Automated regression (starts its own server on ephemeral ports):

```powershell
python "tests/api_smoke_test.py"
python "tests/api_failure_test.py"
python "tests/api_auto_subtitles_test.py"
python "tests/vertical_slice_test.py"
```

## Documentation

- [docs/PRD.md](docs/PRD.md) — MVP scope and acceptance
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — components and data shapes
- [docs/DEMO.md](docs/DEMO.md) — runbook, sample requests, HTTP status reference
- [docs/RELEASE_NOTES_v0.6.0.md](docs/RELEASE_NOTES_v0.6.0.md) — v0.6.0 release notes
- [docs/RELEASE_NOTES_v0.6.1.md](docs/RELEASE_NOTES_v0.6.1.md) — v0.6.1 publish timeline and UI troubleshooting
- [docs/DEMO_SCRIPT_v0.6.0.md](docs/DEMO_SCRIPT_v0.6.0.md) — live demo checklist/script (ASR / subtitles)
- [docs/DEMO_SCRIPT_v0.6.1.md](docs/DEMO_SCRIPT_v0.6.1.md) — publish timeline and troubleshoot UI
