from __future__ import annotations

import os
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from common.errors import AppError

DOUYIN_UPLOAD_URL = "https://creator.douyin.com/creator-micro/content/upload"
DOUYIN_FILE_INPUT_PROBES = (
    "input[type='file']",
    "input[type=file]",
)


@dataclass
class DouyinPrepareResult:
    state: str
    details: Dict[str, Any]


def _ensure_video(video_path: Path) -> None:
    if not video_path.is_file():
        raise AppError("ARTIFACT_MISSING", "missing artifacts.douyin_vertical for douyin publish", {"video_path": str(video_path)})


def _prepare_with_playwright(video_path: Path, session_dir: Path) -> DouyinPrepareResult:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception as e:
        raise AppError(
            "DOUYIN_PLAYWRIGHT_NOT_AVAILABLE",
            "playwright is not available in current environment",
            {"hint": "pip install playwright && playwright install chromium", "exception": str(e)},
        ) from e

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(session_dir),
            headless=False,
        )
        try:
            page = context.new_page()
            timeout_ms = int(os.getenv("DOUYIN_UPLOAD_TIMEOUT_MS", "60000"))
            page.goto(DOUYIN_UPLOAD_URL, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(1500)

            selected_probe = None
            for probe in DOUYIN_FILE_INPUT_PROBES:
                try:
                    page.set_input_files(probe, str(video_path))
                    selected_probe = probe
                    break
                except Exception:
                    continue

            if selected_probe:
                state = "upload_prepared"
                mode = "playwright_auto"
            else:
                state = "upload_prepared_manual"
                mode = "playwright_opened_manual_next"

            return DouyinPrepareResult(
                state=state,
                details={
                    "mode": mode,
                    "upload_url": DOUYIN_UPLOAD_URL,
                    "session_dir": str(session_dir),
                    "video_path": str(video_path),
                    "selected_probe": selected_probe,
                    "probes": list(DOUYIN_FILE_INPUT_PROBES),
                    "manual_confirm_required": True,
                },
            )
        finally:
            # Keep session persisted by closing context cleanly.
            context.close()


def prepare_douyin_upload(*, video_path: Path, data_root: Path) -> DouyinPrepareResult:
    _ensure_video(video_path)

    session_dir = data_root / "platform_sessions" / "douyin"
    session_dir.mkdir(parents=True, exist_ok=True)

    mode = os.getenv("DOUYIN_UPLOAD_MODE", "").strip().lower()
    # default: try playwright first then fallback; set manual/browser to force manual mode.
    auto_first = mode not in ("manual", "browser")
    if auto_first:
        try:
            return _prepare_with_playwright(video_path=video_path, session_dir=session_dir)
        except AppError:
            # Fall back to manual browser flow; API remains usable.
            pass

    # Manual browser fallback with persisted session directory path info.
    try:
        webbrowser.open(DOUYIN_UPLOAD_URL)
    except Exception:
        # Non-fatal: still provide URL for manual open.
        pass

    return DouyinPrepareResult(
        state="upload_prepared_manual",
        details={
            "mode": "manual_browser",
            "upload_url": DOUYIN_UPLOAD_URL,
            "session_dir": str(session_dir),
            "video_path": str(video_path),
            "manual_confirm_required": True,
            "next_step": "open upload_url, verify/upload video in browser, then call confirm endpoint",
        },
    )

