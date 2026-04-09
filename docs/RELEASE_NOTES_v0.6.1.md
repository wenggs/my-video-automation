# Release Notes v0.6.1

Date: 2026-04-09  
Status: Final

## Highlights

- **Douyin publish observability:** bounded `publish.douyin.history` timeline for prepare/confirm outcomes.
- **Safer confirm:** duplicate `confirm` after `published` returns **409** `PUBLISH_ALREADY_CONFIRMED`.
- **UI publish troubleshooting:** timeline display, filters, shareable URLs, and one-click copy for the current view.

## API and Job Record Changes

- **`publish.douyin.history`** (array, last 20 events)
  - Each item: `{ "at": "<ISO8601>", "event": "<string>", "details"?: { ... } }`
  - Typical events: `prepare_succeeded`, `prepare_failed`, `confirm_published`
- **Confirm idempotency**
  - If `publish.douyin.state` is already `published`, `POST .../publish/douyin/confirm` returns **409** with `PUBLISH_ALREADY_CONFIRMED` (no state mutation).

## UI (`/ui`) — Publish Timeline and Debugging

| Area | Behavior |
|------|----------|
| Timeline | Shows recent publish events; **latest first** in the expanded list; failure-style events are visually emphasized. |
| Copy JSON | **Copy publish history JSON** copies the (filtered) history array for handoff. |
| Filters | **publish timeline** type (`all` / `failed only` / `confirm only`), **timeline keyword**, **latest failed chain**; preferences persisted in `localStorage`. |
| Chips | Active filter summary as chips; **Clear timeline filters** resets timeline-related controls. |
| URL | Filter state synced to query params: `status`, `timelineType`, `timelineKeyword`, `timelineLatestFailChain` (refresh-safe, shareable). |
| Link | **Copy troubleshoot link** copies the current page URL (after syncing params). |
| Published jobs | When already published, **Confirm publish** stays disabled with an explicit hint. |

## Compatibility Notes

- No breaking changes to existing lyrics or job enqueue APIs.
- Job JSON may include `publish.douyin.history` when publish actions ran; clients that ignore unknown fields are unaffected.
- Repeating **confirm** after success now fails fast with **409** instead of silently re-writing fields (intentional guard).

## Test Coverage (Executed)

- `tests/api_upload_stub_test.py` — prepare/confirm, history events, duplicate confirm **409**
- `tests/api_upload_failure_test.py` — strict prepare failure, history `prepare_failed`
- `tests/api_smoke_test.py` — end-to-end pipeline regression

## Operational Notes

- Share a reproducible troubleshooting view: set filters in `/ui`, then use **Copy troubleshoot link** or copy the address bar after filters apply.
- URL parameters mirror the UI controls; empty/default values are omitted from the query string.

## Suggested Tag

- `v0.6.1-publish-debug`

## Related Documentation

- [docs/DEMO.md](DEMO.md) — UI walkthrough including publish timeline and URL sharing
- [docs/RELEASE_NOTES_v0.6.0.md](RELEASE_NOTES_v0.6.0.md) — prior ASR/subtitle-review release
