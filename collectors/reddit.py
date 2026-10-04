"""Reddit: 掲示板の規模と盛り上がり、[FRESH] 新譜スレ。REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET が必要(無料)。"""
import re

import requests

from .common import UA, env, get_json

FRESH = re.compile(r"^\[fresh[^\]]*\]\s*(.+?)\s+[-–—]\s+(.+)$", re.I)


def collect(cfg, ctx):
    cid, secret = env("REDDIT_CLIENT_ID"), env("REDDIT_CLIENT_SECRET")
    r = requests.post("https://www.reddit.com/api/v1/access_token", auth=(cid, secret),
                      data={"grant_type": "client_credentials"}, headers={"User-Agent": UA}, timeout=25)
    r.raise_for_status()
    headers = {"Authorization": f"bearer {r.json()['access_token']}", "User-Agent": UA}

    items = []
    for sub in cfg["subreddits"]:
        name = sub["name"]
        try:
            about = get_json(f"https://oauth.reddit.com/r/{name}/about", headers=headers, pause=1)["data"]
            posts = get_json(f"https://oauth.reddit.com/r/{name}/top", params={"t": "week", "limit": 50},
                             headers=headers, pause=1)["data"]["children"]
        except Exception:
            continue
        posts = [p["data"] for p in posts]
        items.append({"kind": "reddit_sub", "name": name, "format": sub.get("format", ""),
                      "subscribers": about.get("subscribers", 0),
                      "week_score": sum(p["score"] for p in posts),
                      "week_comments": sum(p["num_comments"] for p in posts)})
        for p in posts[:15]:
            m = FRESH.match(p["title"])
            items.append({"kind": "reddit_post", "sub": name, "title": p["title"], "score": p["score"],
                          "comments": p["num_comments"], "link": "https://www.reddit.com" + p["permalink"],
                          "artist": m.group(1) if m else ""})
    if not items:
        raise RuntimeError("取得できず")
    return {"items": items}
