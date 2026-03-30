from __future__ import annotations

import argparse
import json
from pathlib import Path

DOUYIN_UPLOAD_URL = "https://creator.douyin.com/creator-micro/content/upload"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Douyin upload Playwright PoC (session reuse + selector probe)"
    )
    p.add_argument("--video", required=True, type=Path, help="local video file to upload")
    p.add_argument(
        "--session-dir",
        type=Path,
        default=Path(".local-data/platform_sessions/douyin"),
        help="persistent browser profile dir",
    )
    p.add_argument(
        "--headless",
        action="store_true",
        help="run browser in headless mode (default false for login/debug)",
    )
    p.add_argument(
        "--timeout-ms",
        type=int,
        default=60000,
        help="navigation timeout in milliseconds",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if not args.video.is_file():
        raise SystemExit(f"video file not found: {args.video}")

    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception as e:
        raise SystemExit(
            "playwright not available. install with:\n"
            "  pip install playwright\n"
            "  playwright install chromium\n"
            f"detail: {e}"
        )

    args.session_dir.mkdir(parents=True, exist_ok=True)

    result: dict[str, object] = {
        "ok": False,
        "mode": "playwright_poc",
        "upload_url": DOUYIN_UPLOAD_URL,
        "session_dir": str(args.session_dir.resolve()),
        "video_path": str(args.video.resolve()),
        "selected_probe": None,
        "error": None,
    }

    probes = [
        "input[type='file']",
        "input[type=file]",
    ]

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(args.session_dir),
            headless=args.headless,
        )
        try:
            page = context.new_page()
            page.goto(DOUYIN_UPLOAD_URL, wait_until="domcontentloaded", timeout=args.timeout_ms)

            # Give the page a moment to render async upload widgets.
            page.wait_for_timeout(1500)

            uploaded = False
            for sel in probes:
                try:
                    page.set_input_files(sel, str(args.video.resolve()))
                    result["selected_probe"] = sel
                    uploaded = True
                    break
                except Exception:
                    continue

            if uploaded:
                result["ok"] = True
                result["next_step"] = "verify thumbnail/progress in browser, then publish manually"
            else:
                result["ok"] = False
                result["error"] = "No known file input selector matched. Manual upload still possible in opened browser."
                result["next_step"] = "inspect upload page DOM and update selector probe list"

            print(json.dumps(result, ensure_ascii=False, indent=2))
        finally:
            context.close()


if __name__ == "__main__":
    main()

