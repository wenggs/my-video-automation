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

### 2.3 Create job

Optional **`video_relative_path`**: relative to `--input-root`. When set, after lyrics alignment the server runs **ffmpeg** 9:16 burn-in and adds artifact **`douyin_vertical`** (`export/douyin_vertical.mp4` under the job output root). Requires **ffmpeg** on the server `PATH`.

```powershell
$jobs='http://127.0.0.1:8011/api/v1/jobs'
$body=@{ video_asset_id='demo-video-001'; words_relative_path='transcript_words.json'; video_relative_path='your-clip.mp4' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri $jobs -ContentType 'application/json' -Body $body
```

### 2.4 Get job result

```powershell
Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:8011/api/v1/jobs/<job-id>'
```

## 3. Minimal vertical slice (CLI, requires ffmpeg)

From repo root, with a real `--video` path and the same fixture lyrics/words as §2.1–2.3:

```powershell
python "src/video_pipeline.py" vertical-slice --video "D:\path\to\your.mp4" --lyrics "tests/fixtures/spike/official_lyrics.txt" --words "tests/fixtures/spike/transcript_words.json" --output ".local-data\jobs-run\demo-vertical"
```

Expect `artifacts/subtitles.srt` and `export/douyin_vertical.mp4` under `--output`. Regression: `python "tests/vertical_slice_test.py"`.

## 4. One-command smoke test

```powershell
python "tests/api_smoke_test.py"
python "tests/api_failure_test.py"
```

Expected output:

```text
API smoke test passed.
API failure regression passed.
```

## 5. Demo artifacts

After a succeeded job:
- `official_lyrics.json`
- `lyrics_confirmed.json`
- `subtitles.srt`
- `logs/job.log`
- `export/douyin_vertical.mp4` (when `video_relative_path` was sent and export succeeded)

Paths are returned in the job response under `artifacts`.

## 6. HTTP status reference (MVP)

These codes are returned for `AppError` flows handled by the API. Other validation issues may still map to **400**.

| HTTP | Typical `error.code` | When |
|------|----------------------|------|
| **404** | `JOB_NOT_FOUND`, `LYRICS_STATE_NOT_FOUND` | Unknown job id; lyrics never imported for that `video_asset_id`; route not found |
| **422** | `WORDS_FILE_NOT_FOUND`, `LYRICS_FILE_NOT_FOUND`, `LYRICS_INPUT_MISSING`, `LYRICS_FLOW_UNEXPECTED`, `VIDEO_FILE_NOT_FOUND`, plus export-related codes when used (`FFMPEG_NOT_FOUND`, `VIDEO_EXPORT_FAILED`, `SUBTITLES_FILE_NOT_FOUND`, …) | Job record is created; pipeline step fails (response body includes job `id` and `status`: `failed`) |
| **400** | e.g. `INVALID_JSON`, `MISSING_VIDEO_ID`, `RELATIVE_PATH_INVALID`, other client/input errors | Bad JSON, missing fields, or `video_relative_path` escapes `input_root` |

Regression coverage: `tests/api_failure_test.py`.
