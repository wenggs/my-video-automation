# MVP Demo Guide

This guide is for the current MVP scope:
- lyrics ingest/confirm APIs
- jobs API invoking lyrics alignment flow

## 1. Run API server

```powershell
python "src/api/server.py" --host 127.0.0.1 --port 8011 --input-root "tests/fixtures/spike" --data-root ".local-data"
```

## 2. Demo API calls

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

```powershell
$jobs='http://127.0.0.1:8011/api/v1/jobs'
$body=@{ video_asset_id='demo-video-001'; words_relative_path='transcript_words.json' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri $jobs -ContentType 'application/json' -Body $body
```

### 2.4 Get job result

```powershell
Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:8011/api/v1/jobs/<job-id>'
```

## 3. One-command smoke test

```powershell
python "tests/api_smoke_test.py"
python "tests/api_failure_test.py"
```

Expected output:

```text
API smoke test passed.
API failure regression passed.
```

## 4. Demo artifacts

After a succeeded job:
- `official_lyrics.json`
- `lyrics_confirmed.json`
- `subtitles.srt`
- `logs/job.log`

Paths are returned in the job response under `artifacts`.

## 5. HTTP status reference (MVP)

These codes are returned for `AppError` flows handled by the API. Other validation issues may still map to **400**.

| HTTP | Typical `error.code` | When |
|------|----------------------|------|
| **404** | `JOB_NOT_FOUND`, `LYRICS_STATE_NOT_FOUND` | Unknown job id; lyrics never imported for that `video_asset_id`; route not found |
| **422** | `WORDS_FILE_NOT_FOUND`, `LYRICS_FILE_NOT_FOUND`, `LYRICS_INPUT_MISSING`, `LYRICS_FLOW_UNEXPECTED` | Job record is created; pipeline step fails (response body includes job `id` and `status`: `failed`) |
| **400** | e.g. `INVALID_JSON`, `MISSING_VIDEO_ID`, other client/input errors | Bad JSON or missing required fields |

Regression coverage: `tests/api_failure_test.py`.
