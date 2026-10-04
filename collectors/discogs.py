"""Discogs(キーなしでも動く。DISCOGS_TOKEN があると速く、相場も取れる)。

- フォーマット別・年別のリリース登録数(年次予想の材料)
- ジャンル×フォーマットの登録数
- 中古需要: 年を問わず「欲しい」登録が多い盤(媒体別、ジャンル×媒体別、日本盤)と want/have 比
過去年の数字はほぼ動かないので data/history/discogs.json にためて、月1回だけ取り直す。
"""
import os

from .common import HISTORY, get, read_json, today, write_json

API = "https://api.discogs.com"
CACHE = HISTORY / "discogs.json"


class Client:
    def __init__(self):
        self.token = os.environ.get("DISCOGS_TOKEN", "").strip()
        self.pause = 1.1 if self.token else 2.6  # 60回/分 or 25回/分

    def search(self, **params):
        headers = {"Authorization": f"Discogs token={self.token}"} if self.token else None
        return get(f"{API}/database/search", params=params, headers=headers, pause=self.pause).json()

    def count(self, **params):
        return self.search(per_page=1, **params)["pagination"]["items"]

    def price(self, release_id):
        headers = {"Authorization": f"Discogs token={self.token}"}
        return get(f"{API}/marketplace/stats/{release_id}", params={"curr_abbr": "JPY"}, headers=headers,
                   pause=self.pause).json()


def collect(cfg, ctx):
    c = Client()
    year = today().year
    first = cfg["forecast"]["history_from"]
    cache = read_json(CACHE, {"format_year": {}, "style_year": {}, "style_format": {}, "refreshed": ""})
    month = today().strftime("%Y-%m")
    full = cache.get("refreshed") != month  # 月が変わったら全部取り直す

    # フォーマット × 年
    for fid, f in cfg["formats"].items():
        row = cache["format_year"].setdefault(fid, {})
        for y in range(first, year + 1):
            if full or str(y) not in row or y >= year - 1:
                row[str(y)] = c.count(type="release", format=f["discogs"], year=y)

    # ジャンル × 年、ジャンル × フォーマット(直近2年)
    if full or not cache["style_year"]:
        for g in cfg["genres"]:
            row = cache["style_year"].setdefault(g["name"], {})
            for y in range(first, year + 1):
                if full and cache.get("refreshed") or str(y) not in row or y >= year - 1:
                    row[str(y)] = c.count(type="release", style=g["discogs"], year=y)
            cache["style_format"][g["name"]] = {
                fid: sum(c.count(type="release", style=g["discogs"], format=f["discogs"], year=y)
                         for y in (year - 1, year))
                for fid, f in cfg["formats"].items()}
            write_json(CACHE, cache)  # 途中で止まっても取得済み分は残す
        cache["refreshed"] = month
    write_json(CACHE, cache)

    # 中古需要: 年を問わず「欲しい」登録が多い盤を、媒体ごと・ジャンル×媒体ごとに取る
    items = []

    def wanted(scope, fid, **params):
        res = c.search(type="release", format=cfg["formats"][fid]["discogs"], sort="want", sort_order="desc",
                       per_page=50, **params)
        for r in res.get("results", []):
            com = r.get("community", {})
            items.append({"kind": "wanted", "scope": scope, "format": fid, "year": r.get("year", ""), "id": r["id"],
                          "title": r.get("title", ""), "style": (r.get("style") or r.get("genre") or [""])[0],
                          "country": r.get("country", ""), "want": com.get("want", 0), "have": com.get("have", 0),
                          "url": "https://www.discogs.com" + r.get("uri", "")})

    for fid in cfg["formats"]:
        wanted("all", fid)
        wanted("japan", fid, country="Japan")
        for g in cfg["genres"]:
            wanted(g["name"], fid, style=g["discogs"])
    if c.token:
        top = sorted(items, key=lambda i: -i["want"] / max(i["have"], 1))[:30]
        for it in top:
            try:
                s = c.price(it["id"])
                it["for_sale"] = s.get("num_for_sale")
                it["lowest_jpy"] = (s.get("lowest_price") or {}).get("value")
            except Exception:
                pass
    return {"items": items, "note": "" if c.token else "トークンなし(相場は未取得)"}
