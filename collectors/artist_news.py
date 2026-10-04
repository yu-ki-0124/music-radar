"""伸びているアーティストの「なぜ」を読むための日本語ニュース(Googleニュース)。
前回の集計で上位だったアーティストだけを対象に、見出しが日本語の記事を最大2本ずつ集める。"""
import datetime as dt
import re
from urllib.parse import quote

import feedparser

from .common import DATA, get, read_json

JA = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")
TOP, PER = 40, 2


def collect(cfg, ctx):
    prev = read_json(DATA / "latest.json", {})
    names = [a["name"] for a in prev.get("artists", [])[:25]] + [a["name"] for a in prev.get("frontier", [])[:15]]
    names = list(dict.fromkeys(names or ctx.get("artist_candidates", [])[:30]))[:TOP]
    items, errors = [], 0
    for name in names:
        try:
            q = '"' + name + '" 音楽 when:30d'
            url = f"https://news.google.com/rss/search?q={quote(q)}&hl=ja&gl=JP&ceid=JP:ja"
            parsed = feedparser.parse(get(url, pause=0.3).content)
        except Exception:
            errors += 1
            continue
        got, seen = 0, set()
        for e in parsed.entries:
            title, _, outlet = e.get("title", "").rpartition(" - ")
            if not title or not JA.search(title) or title in seen:
                continue
            seen.add(title)
            t = e.get("published_parsed")
            items.append({"kind": "artist_news", "name": name, "title": title, "source": outlet,
                          "link": e.get("link", ""), "date": dt.date(*t[:3]).isoformat() if t else ""})
            got += 1
            if got >= PER:
                break
    return {"items": items, "note": f"{len(names)}人中{len({i['name'] for i in items})}人に記事あり" + (f"、{errors}件失敗" if errors else "")}
