"""
Phase 1 Spike: official lyrics -> aligned SRT (minimal PoC).

Purpose:
- Validate the core data flow before full implementation.
- Input confirmed lyrics text + ASR word timestamps.
- Output time-aligned subtitle file (SRT) with official lyrics wording.

This PoC intentionally keeps alignment logic simple:
1) Normalize lyric lines.
2) Match each lyric line to an earliest fitting word window in transcript words.
3) Emit SRT intervals using matched word timestamps.
"""

from __future__ import annotations

import argparse
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


def normalize_text_safe(s: str) -> str:
    # Python stdlib re doesn't support \p classes.
    s = s.strip().lower()
    s = re.sub(r"[\s`~!@#$%^&*()\-_=+\[\]{}\\|;:'\",<.>/?，。！？、；：（）“”‘’《》【】…]+", "", s)
    return s


def load_lyrics(path: Path) -> List[str]:
    lines = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        lines.append(raw)
    if not lines:
        raise ValueError("lyrics file is empty after trimming.")
    return lines


def load_words(path: Path) -> List[WordTs]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("transcript words JSON must be a list.")
    words: List[WordTs] = []
    for item in payload:
        words.append(
            WordTs(
                text=str(item["word"]),
                start=float(item["start"]),
                end=float(item["end"]),
            )
        )
    if not words:
        raise ValueError("transcript words list is empty.")
    return words


def words_window_text(words: List[WordTs], i: int, j: int) -> str:
    return normalize_text_safe("".join(w.text for w in words[i:j]))


def match_line(
    line: str, words: List[WordTs], cursor: int, max_window: int = 60
) -> Tuple[int, int]:
    """
    Return [start_idx, end_idx_exclusive] for best match after cursor.
    Strategy:
    - Use fuzzy containment against normalized strings.
    - Pick earliest window that contains most characters of target.
    """
    target = normalize_text_safe(line)
    if not target:
        raise ValueError("empty normalized lyric line")

    best = None  # (score, i, j)
    n = len(words)
    for i in range(cursor, n):
        upper = min(n, i + max_window)
        for j in range(i + 1, upper + 1):
            candidate = words_window_text(words, i, j)
            if not candidate:
                continue
            # score by LCS-ish proxy: count unique char overlaps
            overlap = sum(1 for ch in set(target) if ch in candidate)
            score = overlap / max(1, len(set(target)))
            if target in candidate:
                score += 0.5
            if best is None or score > best[0]:
                best = (score, i, j)
            if score >= 0.98:
                return i, j
    if best is None:
        # fallback to a tiny window if no signal
        return cursor, min(cursor + 2, len(words))
    return best[1], best[2]


def format_ts(seconds: float) -> str:
    ms = int(round(max(0.0, seconds) * 1000))
    hh = ms // 3_600_000
    mm = (ms % 3_600_000) // 60_000
    ss = (ms % 60_000) // 1000
    mss = ms % 1000
    return f"{hh:02d}:{mm:02d}:{ss:02d},{mss:03d}"


def build_srt(lyrics: List[str], words: List[WordTs]) -> str:
    entries = []
    cursor = 0
    n = len(words)
    for idx, line in enumerate(lyrics, start=1):
        if cursor >= n:
            break
        i, j = match_line(line, words, cursor)
        start = words[i].start
        end = words[max(i, j - 1)].end
        if end <= start:
            end = start + 0.4
        entries.append((idx, start, end, line))
        cursor = max(cursor + 1, j)
    blocks = []
    for idx, start, end, line in entries:
        blocks.append(f"{idx}\n{format_ts(start)} --> {format_ts(end)}\n{line}\n")
    return "\n".join(blocks)


def run(lyrics_file: Path, words_file: Path, out_file: Path) -> None:
    lyrics = load_lyrics(lyrics_file)
    words = load_words(words_file)
    srt = build_srt(lyrics, words)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(srt, encoding="utf-8")
    print(f"Aligned SRT written: {out_file}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Official lyrics alignment PoC")
    parser.add_argument("--lyrics", required=True, type=Path, help="lyrics txt path")
    parser.add_argument(
        "--words",
        required=True,
        type=Path,
        help="ASR word timestamp json path",
    )
    parser.add_argument("--out", required=True, type=Path, help="output srt path")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(args.lyrics, args.words, args.out)
