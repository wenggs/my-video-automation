from __future__ import annotations

import re
from typing import Dict, List


_KEYWORD_TO_TAGS: Dict[str, List[str]] = {
    "live": ["live"],
    "concert": ["concert", "music"],
    "mv": ["mv"],
    "official": ["official"],
    "cover": ["cover"],
    "duet": ["duet"],
    "rehearsal": ["rehearsal"],
    "dance": ["dance"],
    "acoustic": ["acoustic"],
    "unplugged": ["acoustic"],
    "现场": ["live"],
    "演唱会": ["concert", "music"],
    "翻唱": ["cover"],
    "合唱": ["duet"],
    "彩排": ["rehearsal"],
    "舞蹈": ["dance"],
}


def suggest_tags(*, relative_path: str = "", hint_text: str = "") -> List[str]:
    raw = f"{relative_path}\n{hint_text}".strip().lower()
    if not raw:
        return []
    tokens = [x for x in re.split(r"[^a-z0-9\u4e00-\u9fff]+", raw) if x]
    out: List[str] = []
    for tk in tokens:
        tags = _KEYWORD_TO_TAGS.get(tk, [])
        for t in tags:
            if t not in out:
                out.append(t)
    return out[:8]

