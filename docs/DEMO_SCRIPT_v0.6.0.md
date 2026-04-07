# Demo Script v0.6.0

This script is for a live walkthrough of the ASR-first subtitle workflow.

## 1) Start service

```powershell
python "src/api/server.py" --host 127.0.0.1 --port 8011 --input-root "tests/fixtures/spike" --data-root ".local-data"
```

Open:

```text
http://127.0.0.1:8011/ui
```

## 2) Show workspace and rules

- Confirm `input_root` and `data_root` in UI top card.
- Open **Subtitle review rules** panel and explain thresholds:
  - `min_lines`
  - `max_line_chars`
  - `min_line_chars`
  - `flag question mark`
- (Optional) tweak one field and click **Save rules**.

## 3) Run auto subtitles

- Fill:
  - `video_asset_id`: `demo-video-001`
  - `video_relative_path`: `_smoke_sample.mp4`
- Pick ASR quality (`standard` recommended)
- Click **Auto-generate lyrics**
- Show returned:
  - current `request_id`
  - auto details (`model/segments/elapsed/beam`)

## 4) Demonstrate cancel (optional)

- Start auto-generate again
- Click **Cancel auto lyrics** while in-flight
- Explain behavior:
  - cancel endpoint returns `cancelling`
  - active request terminates with `AUTO_SUBTITLES_CANCELLED` (best-effort)

## 5) Subtitle review

- Click **Load auto segments**
- Enable **only needs review**
- Edit lines in text area
- Click **Save reviewed lines**
- Explain that lines are persisted to confirmed lyrics.

## 6) Create export job

- Click **Create**
- Watch status via auto-refresh: `queued -> running -> succeeded`
- Show preflight warnings on row (if any).
- Open/download `douyin_vertical` artifact.

## 7) Publish flow

- Click **Prepare upload**
- Click **Confirm publish**
- (Optional) input `platform_post_id` / `published_url`

## 8) Failure visibility

- Trigger a known bad input once (optional), then show:
  - row-level error fields
  - copy error JSON buttons

## 9) Regression confidence

Run:

```powershell
python "tests/api_auto_subtitles_test.py"
python "tests/api_smoke_test.py"
```

Expected:

```text
API auto subtitles test passed.
API smoke test passed.
```

