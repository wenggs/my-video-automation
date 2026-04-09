# Demo Script v0.6.1

This script is for a live walkthrough of **Douyin publish timeline**, **confirm idempotency**, and **UI troubleshooting** (filters, URL sharing, copy link).

Prerequisite: a job with `artifacts.douyin_vertical` (run a successful export with `video_relative_path` first, or follow [DEMO_SCRIPT_v0.6.0.md](DEMO_SCRIPT_v0.6.0.md) steps 1–6 to produce one).

## 1) Start service

```powershell
python "src/api/server.py" --host 127.0.0.1 --port 8011 --input-root "tests/fixtures/spike" --data-root ".local-data"
```

Open:

```text
http://127.0.0.1:8011/ui
```

## 2) Prepare a succeeded job row

- Use **Create job** with a valid `video_asset_id`, `words_relative_path`, and `video_relative_path` (e.g. `_smoke_sample.mp4`).
- Wait until **status** is `succeeded` and the row shows `douyin_vertical: yes`.

## 3) Publish flow and timeline

- Click **Prepare upload** — observe `publish.douyin.state` and **publish timeline** (expand if needed).
- Click **Confirm publish** — enter optional `platform_post_id` / `published URL` in prompts.
- Expand **publish timeline** — confirm events such as `prepare_succeeded` and `confirm_published` (latest first).
- Note **already published; confirm is disabled** under actions when state is `published`.

## 4) Duplicate confirm (API or UI retry)

- Click **Confirm publish** again (if still enabled in an edge case) or call API:
  - Expect **409** `PUBLISH_ALREADY_CONFIRMED` — explain this protects against double-confirm.

## 5) Timeline filters and chips

- Use top **publish timeline** dropdown: `failed only` / `confirm only` / `all`.
- Enter **timeline keyword** (e.g. `prepare_failed` or part of an error code in details).
- Toggle **latest failed chain** when debugging after a failure.
- Observe **timeline filter chips** update; click **Clear timeline filters** to reset.

## 6) URL sync and shareable view

- Change filters and keyword — notice the browser **URL query** updates (`status`, `timelineType`, `timelineKeyword`, `timelineLatestFailChain`).
- Refresh the page — filters should **restore** from the URL.
- Click **Copy troubleshoot link** — paste into another tab; same filter context should load.

## 7) Copy JSON for handoff

- Expand timeline on a row with history.
- Click **Copy publish history JSON** — paste into a ticket or chat for structured handoff.

## 8) Regression confidence

```powershell
python "tests/api_upload_stub_test.py"
python "tests/api_upload_failure_test.py"
python "tests/api_smoke_test.py"
```

Expected: all three complete without assertion failures (upload tests require **ffmpeg** on `PATH` where applicable).

## See also

- [RELEASE_NOTES_v0.6.1.md](RELEASE_NOTES_v0.6.1.md)
- [DEMO.md](DEMO.md) §4 UI walkthrough
