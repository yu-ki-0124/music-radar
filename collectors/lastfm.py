"""Last.fm: 世界・国別の人気アーティスト、タグ(ジャンル)の規模。LASTFM_API_KEY が必要(無料)。"""
from .common import env, get_json

API = "https://ws.audioscrobbler.com/2.0/"
COUNTRIES = {"jp": "Japan", "us": "United States", "gb": "United Kingdom", "kr": "Korea, Republic of",
             "de": "Germany", "fr": "France", "br": "Brazil", "mx": "Mexico", "in": "India", "ng": "Nigeria",
             "au": "Australia", "id": "Indonesia"}


def collect(cfg, ctx):
    key = env("LASTFM_API_KEY")

    def call(method, **params):
        return get_json(API, params={"method": method, "api_key": key, "format": "json", **params}, pause=0.25)

    items = []
    for pos, a in enumerate(call("chart.gettopartists", limit=200)["artists"]["artist"], 1):
        items.append({"kind": "lastfm_artist", "region": "global", "pos": pos, "artist": a["name"],
                      "listeners": int(a["listeners"]), "playcount": int(a["playcount"])})
    for cc in cfg["regions"]:
        if cc not in COUNTRIES:
            continue
        try:
            arts = call("geo.gettopartists", country=COUNTRIES[cc], limit=100)["topartists"]["artist"]
        except Exception:
            continue
        for pos, a in enumerate(arts, 1):
            items.append({"kind": "lastfm_artist", "region": cc, "pos": pos, "artist": a["name"],
                          "listeners": int(a["listeners"])})
    for g in cfg["genres"]:
        try:
            t = call("tag.getinfo", tag=g["lastfm"])["tag"]
            items.append({"kind": "lastfm_tag", "name": g["name"], "reach": int(t["reach"]), "total": int(t["total"])})
        except Exception:
            continue
    return {"items": items}
