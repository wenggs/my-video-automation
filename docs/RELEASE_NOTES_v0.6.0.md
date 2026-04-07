# Release Notes v0.6.0

Date: 2026-04-07
Status: Final

## Highlights

- Added automatic subtitle generation for videos without official lyrics.
- Added ASR quality presets and retry flow in UI.
- Added ASR request concurrency guard and best-effort cancellation.
- Improved observability for auto-subtitle runs (model/segments/elapsed/beam).
- Added minimal subtitle review workflow and configurable review thresholds.

## New Capabilities

- API: `POST /api/v1/library/videos/{id}/lyrics/auto-generate`
  - Bootstraps lyrics from video via ASR (faster-whisper by default).
  - Supports parameters:
    - `video_relative_path` (required)
    - `model` (default: `small`)
    - `language` (default: `zh`)
    - `beam_size` (default: `5`)
    - `vad_filter` (default: `true`)
    - `request_id` (optional; enables cancellation tracking)
  - Response includes:
    - updated lyrics state (`import` / `confirmed`)
    - `auto_generate.srt_path`
    - `auto_generate.details` (`engine/model/language/segments/beam_size/vad_filter/elapsed_sec`)
    - `auto_generate.request_id`

- API: `POST /api/v1/library/videos/{id}/lyrics/auto-generate/cancel`
  - Cancels in-flight ASR request by `request_id` (best-effort).
  - Returns `200` with `state: cancelling` if request exists.

- API: `GET /api/v1/library/videos/{id}/lyrics/auto-segments`
  - Returns auto ASR segments with review hints:
    - `needs_review`
    - `review_reasons`
    - `needs_review_count`

- API: `GET/PUT /api/v1/config/subtitles-review`
  - Configures subtitle review/preflight rules:
    - `min_lines`
    - `max_line_chars`
    - `min_line_chars`
    - `flag_question_mark`

- UI (`/ui`)
  - ASR quality presets: `fast / standard / high`.
  - Manual ASR params: `model`, `language`.
  - One-click auto-generate, retry, and cancel.
  - Displays current ASR `request_id`.
  - Displays ASR run metrics (`model/segments/elapsed/beam`).
  - Provides minimal subtitle review editor:
    - load auto-segments
    - filter by `needs_review`
    - save reviewed lines to confirmed lyrics
  - Provides subtitle review rules editor (load/save).

## Reliability and Guardrails

- ASR in-flight concurrency limit added:
  - returns `429 AUTO_SUBTITLES_BUSY` when saturated.
- Path safety enforced for `video_relative_path` (must stay under `input_root`).
- Structured error responses for ASR failure states, including:
  - `VIDEO_RELATIVE_PATH_REQUIRED`
  - `RELATIVE_PATH_INVALID`
  - `VIDEO_FILE_NOT_FOUND`
  - `AUTO_SUBTITLES_ENGINE_NOT_AVAILABLE`
  - `AUTO_SUBTITLES_CANCELLED`
  - `AUTO_SUBTITLES_BUSY`
  - `AUTO_SEGMENTS_NOT_FOUND`

## Compatibility Notes

- Existing lyrics/job/publish APIs remain compatible.
- `POST /api/v1/jobs` behavior remains asynchronous (`202 Accepted` + polling).
- UI changes are additive; existing flows remain available.

## Test Coverage (Executed)

- `tests/api_auto_subtitles_test.py`
  - happy path
  - invalid input paths/params
  - concurrency saturation (`429`)
  - cancellation flow (`cancel` + `409 AUTO_SUBTITLES_CANCELLED`)
  - auto-segments read and reviewed-lines save
  - subtitle review rules config roundtrip (`GET/PUT /api/v1/config/subtitles-review`)
- `tests/api_smoke_test.py`
  - end-to-end regression unaffected by ASR enhancements

## Operational Notes

- For deterministic local tests/demo:
  - `AUTO_SUBTITLES_FAKE=1`
  - optional `AUTO_SUBTITLES_FAKE_SLEEP_MS=<ms>` for concurrency/cancel scenarios
- For real ASR:
  - install `faster-whisper`
  - keep model choice aligned with machine capacity (start with `small`)

## Suggested Tag

- `v0.6.0-asr-workflow`

## Demo Script

- See `docs/DEMO_SCRIPT_v0.6.0.md` for step-by-step demo flow and checkpoints.

