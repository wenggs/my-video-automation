# MVP Demo Guide

This guide is for the current MVP scope:
- lyrics ingest/confirm APIs
- jobs API invoking lyrics alignment flow

## 1. Run API server

```powershell
python "src/api/server.py" --host 127.0.0.1 --port 8011 --input-root "tests/fixtures/spike" --data-root ".local-data"
```

## 2. Demo API calls

### 2.0 Workspace, media scan, job list (GET)

- **`GET /api/v1/config`** — returns resolved **`input_root`** and **`data_root`** (server flags).
- **`GET /api/v1/library/videos`** — recursively lists video files under `input-root` (extensions: `mp4`, `mov`, `mkv`, `webm`, `m4v`, `avi`). Each item: `relative_path`, `size_bytes`.
- **`GET /api/v1/jobs?limit=20`** — recent jobs, newest first by `updated_at` (default `limit=100`, capped at 500).

```powershell
Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:8011/api/v1/config'
Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:8011/api/v1/library/videos'
Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:8011/api/v1/jobs?limit=10'
```

`words_relative_path` and `video_relative_path` on **`POST /api/v1/jobs`** must resolve **inside** `input_root` (no `..` traversal).

### 2.1 Import official lyrics

```powershell
$base='http://127.0.0.1:8011/api/v1/library/videos/demo-video-001/lyrics'
$body=@{ mode='sidecar_file'; sidecar_relative_path='official_lyrics.txt'; preserve_confirmed=$false } | ConvertTo-Json
Invoke-RestMethod -Method Put -Uri $base -ContentType 'application/json' -Body $body
```

### 2.2 Confirm lyrics (micro-tuning)

```powershell
$uri='http://127.0.0.1:8011/api/v1/library/videos/demo-video-001/lyrics/confirmed'
$body=@{ lines=@('你说风吹过我们的夏天（现场版）','人潮里我听见你的名字','这一刻全场都在合唱') } | ConvertTo-Json -Depth 5
Invoke-RestMethod -Method Patch -Uri $uri -ContentType 'application/json' -Body $body
```

### 2.3 Create job (asynchronous)

**`POST /api/v1/jobs`** returns **202 Accepted** with a job whose **`status`** starts as **`queued`**, then moves to **`running`**, then **`succeeded`** or **`failed`**. The HTTP handler does not wait for lyrics alignment or **ffmpeg**. Poll **`GET /api/v1/jobs/{id}`** until `status` is terminal.

Optional **`video_relative_path`**: relative to `--input-root`. When set, after lyrics alignment the worker runs **ffmpeg** 9:16 burn-in and adds **`douyin_vertical`**. Requires **ffmpeg** on the server `PATH`.

Pipeline errors (missing words file, bad video path, export failure, etc.) are reflected in the job record: **`status`** = `failed` and **`error`**: `{ code, message, details }`. **`GET /jobs/{id}`** stays **200** for an existing job so clients can always read the final state.

```powershell
$jobs='http://127.0.0.1:8011/api/v1/jobs'
$body=@{ video_asset_id='demo-video-001'; words_relative_path='transcript_words.json'; video_relative_path='your-clip.mp4' } | ConvertTo-Json
$r = Invoke-WebRequest -Method Post -Uri $jobs -ContentType 'application/json' -Body $body
# Expect status code 202; body is JSON with id, status: queued|running|...
```

### 2.4 Get job result (poll)

```powershell
Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:8011/api/v1/jobs/<job-id>'
```

PowerShell polling loop:

```powershell
$jobId = '<job-id>'
while ($true) {
  $j = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8011/api/v1/jobs/$jobId"
  if ($j.status -in @('succeeded','failed','cancelled')) { break }
  Start-Sleep -Milliseconds 300
}
Write-Host $j.status
```

### 2.5 Get job logs (tail)

```powershell
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8011/api/v1/jobs/<job-id>/logs?tail=200"
```

Response shape:
- `lines`: string[] (JSONL lines as strings), only last `tail` lines
- `line_count`: total lines in `logs/job.log`

### 2.6 Cancel job

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8011/api/v1/jobs/<job-id>/cancel"
```

If the job is still `queued` / `running`, it becomes `cancelled`. If it is already `succeeded/failed/cancelled`, the server returns **409**.

### 2.7 Douyin upload prepare/confirm

For MVP, the HTTP API supports a **manual publish confirmation flow** with an upload service adapter.

1. Prepare upload draft

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8011/api/v1/jobs/<job-id>/publish/douyin/prepare" -ContentType 'application/json' -Body (@{} | ConvertTo-Json)
```

2. Confirm publish (manual confirmation, with optional platform result fields)

```powershell
$body=@{ platform_post_id='douyin-post-001'; published_url='https://www.douyin.com/video/123' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8011/api/v1/jobs/<job-id>/publish/douyin/confirm" -ContentType 'application/json' -Body $body
```

If `artifacts.douyin_vertical` is missing, the server returns **422** (`ARTIFACT_MISSING`).

Notes:
- Default mode opens Douyin upload page in the local browser and returns `upload_prepared_manual` with instructions under `publish.douyin.prepare_details`.
- Set env `DOUYIN_UPLOAD_MODE=auto` to try Playwright persistent-session upload first (best effort). If Playwright is unavailable, it falls back to manual mode.
- If auto prepare succeeds, `publish.douyin.state` is `upload_prepared`.
- If fallback is used, `publish.douyin.state` is `upload_prepared_manual`, and fallback cause is available in `publish.douyin.prepare_details.fallback_error`.
- If strict mode is enabled (`DOUYIN_UPLOAD_STRICT=1`), auto prepare failures do not fallback; API returns error status and stores `publish.douyin.state = prepare_failed` with structured `publish.douyin.error`.
- Typical strict errors:
  - `DOUYIN_UPLOAD_PAGE_UNREACHABLE`
  - `DOUYIN_UPLOAD_SELECTOR_NOT_FOUND`
  - `DOUYIN_PLAYWRIGHT_NOT_AVAILABLE`

### 2.8 Auto-generate lyrics/subtitles from video (ASR)

When official lyrics are unavailable (for example, live/concert clips), you can bootstrap lyrics from ASR:

```powershell
$body=@{ video_relative_path='_smoke_sample.mp4'; model='small'; language='zh' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8011/api/v1/library/videos/demo-video-001/lyrics/auto-generate" -ContentType 'application/json' -Body $body
```

Quality preset examples:

```powershell
# fast
$body=@{ video_relative_path='_smoke_sample.mp4'; model='tiny'; language='zh'; beam_size=1; vad_filter=$true } | ConvertTo-Json

# standard
$body=@{ video_relative_path='_smoke_sample.mp4'; model='small'; language='zh'; beam_size=5; vad_filter=$true } | ConvertTo-Json

# high
$body=@{ video_relative_path='_smoke_sample.mp4'; model='medium'; language='zh'; beam_size=8; vad_filter=$true } | ConvertTo-Json
```

Response includes:
- regular lyrics state (`import` / `confirmed`)
- `auto_generate.srt_path` (generated SRT path)
- `auto_generate.details` (engine/model/language/segments/beam_size/vad_filter/elapsed_sec)

Notes:
- Path safety is enforced: `video_relative_path` must stay under `input_root`.
- Default engine is `faster-whisper` (`model=small`, `language=zh`).
- If engine is not installed, API returns `AUTO_SUBTITLES_ENGINE_NOT_AVAILABLE`.
- For deterministic local regression tests, `AUTO_SUBTITLES_FAKE=1` can be used.
- Missing `video_relative_path` returns `VIDEO_RELATIVE_PATH_REQUIRED`; path traversal returns `RELATIVE_PATH_INVALID`.
- Auto subtitles requests are concurrency-limited; when busy, API returns `429 AUTO_SUBTITLES_BUSY`.
- `request_id` can be provided for cancellation; call `POST /api/v1/library/videos/{id}/lyrics/auto-generate/cancel` with `{ "request_id": "..." }`.

## 3. Minimal vertical slice (CLI, requires ffmpeg)

From repo root, with a real `--video` path and the same fixture lyrics/words as §2.1–2.3:

```powershell
python "src/video_pipeline.py" vertical-slice --video "D:\path\to\your.mp4" --lyrics "tests/fixtures/spike/official_lyrics.txt" --words "tests/fixtures/spike/transcript_words.json" --output ".local-data\jobs-run\demo-vertical"
```

Expect:
- `artifacts/subtitles.srt` (original aligned subtitles, audit)
- `edited/edited_master.mp4` (trimmed master used for burn-in)
- `artifacts/subtitles_burnin.srt` (shifted subtitles for trimmed timeline)
- `export/douyin_vertical.mp4` under `--output`.

Regression: `python "tests/vertical_slice_test.py"`.

## 4. UI demo walkthrough (`/ui`)

Open:

```text
http://127.0.0.1:8011/ui
```

Recommended walkthrough:

1. Verify the top **Workspace config** card shows `input_root` and `data_root` from `GET /api/v1/config`.
2. In **Create job**, fill `video_asset_id`, `words_relative_path`, and optional `video_relative_path`.
3. Use **Auto-generate lyrics** (with quality/model/language), and if needed click **Retry auto lyrics**.
4. Check `auto details` line for model/segments/elapsed/beam.
5. Click **Create** to run full pipeline and keep **auto refresh (2s)** enabled for status transitions.
6. Use **Filter** (`running`, `failed`, `succeeded`, etc.) to focus on target jobs.
7. For failed jobs, expand **job error details** / **prepare error details**, then click:
   - `Copy job error JSON`
   - `Copy prepare error JSON`
8. For publish flow:
   - click **Prepare upload**
   - then **Confirm publish** (optionally input `platform_post_id` and `published_url`)

UI notes:
- Form/filter/auto-refresh preferences are persisted in browser `localStorage`.
- Successful export jobs provide `Open video` and `Download` links for `douyin_vertical`.
- Logs are available from each row via `logs` link.

## 5. One-command smoke test

```powershell
python "tests/api_smoke_test.py"
python "tests/api_failure_test.py"
```

Expected output:

```text
API smoke test passed.
API failure regression passed.
```

## 6. Demo artifacts

After a succeeded job:
- `official_lyrics.json`
- `lyrics_confirmed.json`
- `subtitles.srt`
- `edited_master.mp4` (trimmed master for the burn-in timeline; only when `video_relative_path` was provided)
- `subtitles_burnin.srt` (shifted subtitles for the trimmed timeline)
- `logs/job.log`
- `export/douyin_vertical.mp4` (when `video_relative_path` was sent and export succeeded)

Paths are returned in the job response under `artifacts`.

## 7. HTTP status reference (MVP)

These codes are returned for synchronous routes and for the **`POST /api/v1/jobs`** acceptance response. **Pipeline failures after enqueue** do not change the POST status code: use **`GET /api/v1/jobs/{id}`** and read **`status`** / **`error`**.

| HTTP | Typical `error.code` | When |
|------|----------------------|------|
| **202** | (job body, not `error` envelope) | **`POST /api/v1/jobs`** job enqueued; body includes `id`, `status`: `queued` (then poll) |
| **429** | `JOB_QUEUE_FULL` | Server inflight cap reached (too many `queued`/`running` jobs) |
| **404** | `JOB_NOT_FOUND`, `LYRICS_STATE_NOT_FOUND` | Unknown job id; lyrics never imported for that `video_asset_id` (**before** job create); route not found |
| **422** | (legacy) | Not used for **`POST /jobs`** completion; pipeline **`WORDS_FILE_NOT_FOUND`**, **`VIDEO_FILE_NOT_FOUND`**, etc. appear on the **job** JSON with **`status`: `failed`** |
| **400** | e.g. `INVALID_JSON`, `MISSING_VIDEO_ID`, … | Bad JSON or missing `video_asset_id` on **POST** (no job row). **`RELATIVE_PATH_INVALID`** after enqueue is stored on the job; **POST** still **202** |

Regression coverage: `tests/api_failure_test.py`.
