from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple


@dataclass
class WordTs:
    text: str
    start: float
    end: float


def normalize_lyrics_lines(raw_text: str) -> List[str]:
    lines: List[str] = []
    for raw in raw_text.splitlines():
        line = raw.strip()
        if line:
            lines.append(line)
    if not lines:
        raise ValueError("lyrics text is empty after normalization")
    return lines


def load_lyrics_from_file(path: Path) -> List[str]:
    return normalize_lyrics_lines(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_words(path: Path) -> List[WordTs]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("words json must be a list")
    out: List[WordTs] = []
    for item in payload:
        out.append(
            WordTs(
                text=str(item["word"]),
                start=float(item["start"]),
                end=float(item["end"]),
            )
        )
    if not out:
        raise ValueError("words json is empty")
    return out


def _normalize_text_for_match(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[\s`~!@#$%^&*()\-_=+\[\]{}\\|;:'\",<.>/?，。！？、；：（）“”‘’《》【】…]+", "", s)
    return s


def _window_text(words: List[WordTs], i: int, j: int) -> str:
    return _normalize_text_for_match("".join(w.text for w in words[i:j]))


def _match_line(line: str, words: List[WordTs], cursor: int, max_window: int = 60) -> Tuple[int, int]:
    target = _normalize_text_for_match(line)
    if not target:
        raise ValueError("empty normalized lyric line")
    best = None  # (score, i, j)
    n = len(words)
    for i in range(cursor, n):
        upper = min(n, i + max_window)
        for j in range(i + 1, upper + 1):
            candidate = _window_text(words, i, j)
            if not candidate:
                continue
            overlap = sum(1 for ch in set(target) if ch in candidate)
            score = overlap / max(1, len(set(target)))
            if target in candidate:
                score += 0.5
            if best is None or score > best[0]:
                best = (score, i, j)
            if score >= 0.98:
                return i, j
    if best is None:
        return cursor, min(cursor + 2, len(words))
    return best[1], best[2]


def _fmt_srt_ts(seconds: float) -> str:
    ms = int(round(max(0.0, seconds) * 1000))
    hh = ms // 3_600_000
    mm = (ms % 3_600_000) // 60_000
    ss = (ms % 60_000) // 1000
    mss = ms % 1000
    return f"{hh:02d}:{mm:02d}:{ss:02d},{mss:03d}"


def align_confirmed_lyrics_to_words(lines: List[str], words: List[WordTs]) -> str:
    entries = []
    cursor = 0
    for idx, line in enumerate(lines, start=1):
        if cursor >= len(words):
            break
        i, j = _match_line(line, words, cursor)
        start = words[i].start
        end = words[max(i, j - 1)].end
        if end <= start:
            end = start + 0.4
        entries.append((idx, start, end, line))
        cursor = max(cursor + 1, j)
    blocks = []
    for idx, start, end, line in entries:
        blocks.append(f"{idx}\n{_fmt_srt_ts(start)} --> {_fmt_srt_ts(end)}\n{line}\n")
    return "\n".join(blocks)
