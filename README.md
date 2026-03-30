# my-video-automation

Local-first pipeline MVP: lyrics ingest and confirmation, forced alignment to word-level timestamps, and a minimal HTTP API for jobs.

## Requirements

- **Python 3.10+** (stdlib only for the current API and tests)

## Quick start

1. Start the API (pick free ports; default example uses `8011`):

   ```powershell
   python "src/api/server.py" --host 127.0.0.1 --port 8011 --input-root "tests/fixtures/spike" --data-root ".local-data"
   ```

2. Follow **[docs/DEMO.md](docs/DEMO.md)** for example `PUT` / `PATCH` / `POST` calls and expected artifacts.

## Tests

Automated regression (starts its own server on ephemeral ports):

```powershell
python "tests/api_smoke_test.py"
python "tests/api_failure_test.py"
```

## Documentation

- [docs/PRD.md](docs/PRD.md) — MVP scope and acceptance
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — components and data shapes
- [docs/DEMO.md](docs/DEMO.md) — runbook, sample requests, HTTP status reference
