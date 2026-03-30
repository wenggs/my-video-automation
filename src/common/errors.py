from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

_NOT_FOUND_CODES = frozenset({"JOB_NOT_FOUND", "LYRICS_STATE_NOT_FOUND"})

_PIPELINE_FAILURE_CODES = frozenset(
    {
        "WORDS_FILE_NOT_FOUND",
        "LYRICS_FILE_NOT_FOUND",
        "LYRICS_INPUT_MISSING",
        "LYRICS_FLOW_UNEXPECTED",
        "VIDEO_FILE_NOT_FOUND",
        "SUBTITLES_FILE_NOT_FOUND",
        "FFMPEG_NOT_FOUND",
        "VIDEO_EXPORT_FAILED",
    }
)


def http_status_for_app_error(code: str) -> int:
    if code in _NOT_FOUND_CODES:
        return 404
    if code in _PIPELINE_FAILURE_CODES:
        return 422
    return 400


@dataclass
class AppError(Exception):
    code: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }
