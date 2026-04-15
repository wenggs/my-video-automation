from __future__ import annotations

from typing import List, Sequence


def _clean_tag(tag: str) -> str:
    t = str(tag or "").strip().lower().replace(" ", "")
    return t


def _dedup_keep_order(items: Sequence[str]) -> List[str]:
    out: List[str] = []
    for x in items:
        s = str(x or "").strip()
        if s and s not in out:
            out.append(s)
    return out


def suggest_metadata(
    *,
    video_asset_id: str,
    tags_confirmed: Sequence[str],
    tags_suggested: Sequence[str],
    platform: str = "douyin",
) -> dict:
    platform_name = str(platform or "douyin").strip().lower()
    tags = _dedup_keep_order([_clean_tag(x) for x in [*tags_confirmed, *tags_suggested]])
    # Keep hashtag format close to Douyin convention.
    hashtags = _dedup_keep_order([f"#{t}" for t in tags if t])
    if not hashtags:
        hashtags = ["#音乐", "#现场", "#翻唱"]

    topic = tags[0] if tags else "音乐现场"
    title = f"{video_asset_id} | {topic} 竖屏片段"
    description = (
        f"{video_asset_id} 竖屏剪辑片段，适合 {platform_name} 发布。"
        f" 已按目标时长自动剪辑并完成字幕烧录。"
    )
    return {
        "video_asset_id": str(video_asset_id),
        "platform": platform_name,
        "title": title,
        "description": description,
        "hashtags": hashtags,
    }

