from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from pipeline.lyrics_flow import WordTs  # noqa: E402
from services.video_edit_service import choose_trim_interval_from_words  # noqa: E402


def run() -> None:
    # Sparse intro words, denser cluster around 40~50s.
    words = [
        WordTs(text="a", start=0.0, end=0.2),
        WordTs(text="b", start=6.0, end=6.2),
        WordTs(text="c", start=12.0, end=12.2),
        WordTs(text="d", start=40.0, end=40.2),
        WordTs(text="e", start=41.0, end=41.2),
        WordTs(text="f", start=42.0, end=42.2),
        WordTs(text="g", start=43.0, end=43.2),
        WordTs(text="h", start=44.0, end=44.2),
        WordTs(text="i", start=45.0, end=45.2),
        WordTs(text="j", start=46.0, end=46.2),
        WordTs(text="k", start=47.0, end=47.2),
        WordTs(text="l", start=48.0, end=48.2),
        WordTs(text="m", start=49.0, end=49.2),
        WordTs(text="n", start=70.0, end=70.2),
    ]

    s, e = choose_trim_interval_from_words(words=words, target_min_sec=10.0, target_max_sec=20.0)
    assert abs((e - s) - 20.0) < 1e-6, (s, e)
    # Should not stay at the intro head; should move near dense region.
    assert s >= 30.0, (s, e)

    # When total duration is shorter than target max, keep full range.
    short_words = [
        WordTs(text="x", start=1.0, end=1.2),
        WordTs(text="y", start=8.0, end=8.2),
    ]
    s2, e2 = choose_trim_interval_from_words(words=short_words, target_min_sec=10.0, target_max_sec=60.0)
    assert abs(s2 - 1.0) < 1e-6, (s2, e2)
    assert abs(e2 - 8.2) < 1e-6, (s2, e2)

    print("Video edit selection test passed.")


if __name__ == "__main__":
    run()

