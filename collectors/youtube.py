"""YouTube Data API: 各国の音楽カテゴリ急上昇動画と再生数。YOUTUBE_API_KEY が必要(無料)。"""
import datetime as dt
import re

from .common import env, get_json

SUFFIX = re.compile(r"\s*(- Topic|VEVO|Official( YouTube)?( Channel)?|公式(チャンネル)?)\s*$", re.I)


def collect(cfg, ctx):
    key = env("YOUTUBE_API_KEY")
    now = dt.datetime.now(dt.timezone.utc)
    items, errors = [], []
    for cc in cfg["regions"]:
        try:
            data = get_json("https://www.googleapis.com/youtube/v3/videos", params={
                "part": "snippet,statistics", "chart": "mostPopular", "videoCategoryId": "10",
                "regionCode": cc.upper(), "maxResults": 50, "key": key})
        except Exception as e:
            errors.append(f"{cc}: {str(e).replace(key, '***')}")
            continue
        for pos, v in enumerate(data.get("items", []), 1):
            sn, st = v["snippet"], v.get("statistics", {})
            published = dt.datetime.fromisoformat(sn["publishedAt"].replace("Z", "+00:00"))
            views = int(st.get("viewCount", 0))
            days = max((now - published).total_seconds() / 86400, 0.5)
            items.append({"kind": "yt_video", "region": cc, "pos": pos, "id": v["id"], "title": sn["title"],
                          "artist": SUFFIX.sub("", sn["channelTitle"]), "views": views,
                          "likes": int(st.get("likeCount", 0)), "comments": int(st.get("commentCount", 0)),
                          "views_per_day": round(views / days), "age_days": round(days, 1)})
    if not items:
        raise RuntimeError("; ".join(errors[:3]) or "結果なし")
    return {"items": items, "note": f"{len(errors)}か国失敗" if errors else ""}
