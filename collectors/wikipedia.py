"""Wikipedia の閲覧数(キー不要)。

- メディア・ジャンルの記事: 月次の閲覧数を過去分まとめて取得(年次予想の材料)
- チャートに出たアーティスト: 直近90日の日次閲覧数(急上昇の検知)
"""
import datetime as dt
import time
from urllib.parse import quote

from .common import get_json, today

PV = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/{proj}/all-access/user/{title}/{gran}/{start}/{end}"
MUSIC_WORDS = ("singer", "band", "rapper", "musician", "group", "duo", "songwriter", "dj", "producer",
               "composer", "idol", "vocalist", "guitarist", "pianist", "trio", "artist", "ensemble")
MAX_ARTISTS = 300
BUDGET_SEC = 300  # アーティスト分はこの時間で打ち切る


def _views(proj, title, gran, start, end):
    url = PV.format(proj=proj, title=quote(title.replace(" ", "_"), safe=""), gran=gran,
                    start=start.strftime("%Y%m%d00"), end=end.strftime("%Y%m%d00"))
    return [(i["timestamp"][:8], i["views"]) for i in get_json(url, pause=0.15, retries=1).get("items", [])]


def _resolve_artists(names):
    """名前 → 音楽関係と確認できた英語版記事名。"""
    out = {}
    for i in range(0, len(names), 40):
        chunk = names[i:i + 40]
        params = {"action": "query", "titles": "|".join(chunk), "redirects": 1, "prop": "description",
                  "format": "json"}
        pages, alias = {}, {}
        while True:  # 説明文は数回に分けて返ってくるので continue をたどる
            data = get_json("https://en.wikipedia.org/w/api.php", pause=0.1, params=params)
            q = data.get("query", {})
            alias.update({n["to"]: n["from"] for n in q.get("normalized", [])})
            for r in q.get("redirects", []):
                alias[r["to"]] = alias.get(r["from"], r["from"])
            for pid, page in q.get("pages", {}).items():
                pages.setdefault(pid, {}).update(page)
            if "continue" not in data:
                break
            params = {**params, **data["continue"]}
        for page in pages.values():
            desc = page.get("description", "").lower()
            if "missing" in page or not any(w in desc for w in MUSIC_WORDS):
                continue
            out[alias.get(page["title"], page["title"])] = page["title"]
    return out


def collect(cfg, ctx):
    items = []
    end = today() - dt.timedelta(days=1)
    month_start = dt.date(2015, 7, 1)

    topics = []
    for fid, f in cfg["formats"].items():
        for lang, titles in f["wiki"].items():
            topics += [("format", fid, lang, t) for t in titles]
    topics += [("genre", g["name"], "en", g["wiki"]) for g in cfg["genres"] if g.get("wiki")]
    for kind, name, lang, title in topics:
        try:
            series = _views(f"{lang}.wikipedia", title, "monthly", month_start, end)
        except Exception:
            continue
        items.append({"kind": f"wiki_{kind}", "name": name, "lang": lang, "title": title,
                      "months": [[d[:6], v] for d, v in series]})

    # サイト全体の閲覧数(Wikipedia自体の増減を差し引いて見るための基準)
    for lang in ("en", "ja"):
        try:
            url = (f"https://wikimedia.org/api/rest_v1/metrics/pageviews/aggregate/{lang}.wikipedia/all-access/user/"
                   f"monthly/{month_start:%Y%m%d}00/{end:%Y%m%d}00")
            items.append({"kind": "wiki_total", "lang": lang,
                          "months": [[i["timestamp"][:6], i["views"]] for i in get_json(url)["items"]]})
        except Exception:
            pass

    names = ctx.get("artist_candidates", [])[:MAX_ARTISTS]
    start = end - dt.timedelta(days=90)
    deadline = time.time() + BUDGET_SEC
    resolved = _resolve_artists(names)
    # 記事の有無を調べた名前(記事が無い = 世界的にはまだ無名、の判定に使う)
    items.append({"kind": "wiki_checked", "names": names})
    for name, title in resolved.items():
        if time.time() > deadline:
            break
        try:
            series = _views("en.wikipedia", title, "daily", start, end)
        except Exception:
            continue
        if len(series) >= 40:
            items.append({"kind": "wiki_artist", "name": name, "title": title, "daily": [v for _, v in series]})
    return {"items": items}
