"""各国チャート(キー不要): iTunes 国別トップ曲/アルバム、Deezer 世界・ジャンル別。"""
from .common import get_json

DEEZER_GENRES = {0: "All", 132: "Pop", 116: "Rap/Hip Hop", 152: "Rock", 165: "R&B", 113: "Dance",
                 85: "Alternative", 106: "Electro", 129: "Jazz", 169: "Soul & Funk", 16: "Asian Music",
                 2: "African Music", 197: "Latin Music"}


def _itunes(cc, kind):
    url = f"https://itunes.apple.com/{cc}/rss/{kind}/limit=100/json"
    entries = get_json(url, pause=0.3).get("feed", {}).get("entry", [])
    if isinstance(entries, dict):
        entries = [entries]
    for pos, e in enumerate(entries, 1):
        yield {
            "kind": "chart", "chart": f"itunes_{kind}", "region": cc, "pos": pos,
            "artist": e["im:artist"]["label"], "title": e["im:name"]["label"],
            "genre": e.get("category", {}).get("attributes", {}).get("label", ""),
        }


def collect(cfg, ctx):
    items, errors = [], []
    for cc in cfg["regions"]:
        for kind in ("topsongs", "topalbums"):
            try:
                items.extend(_itunes(cc, kind))
            except Exception as e:
                errors.append(f"itunes {cc}/{kind}: {e}")
    for gid, gname in DEEZER_GENRES.items():
        try:
            data = get_json(f"https://api.deezer.com/chart/{gid}/artists", params={"limit": 50}, pause=0.2)
            for a in data.get("data", []):
                items.append({"kind": "chart", "chart": "deezer_artists", "region": "global", "pos": a["position"],
                              "artist": a["name"], "title": "", "genre": gname if gid else ""})
        except Exception as e:
            errors.append(f"deezer {gname}: {e}")
    if not items:
        raise RuntimeError("; ".join(errors[:3]))
    return {"items": items, "note": f"{len(errors)}件失敗" if errors else ""}
