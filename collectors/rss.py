"""音楽メディアの RSS と Googleニュース検索から直近の見出しを集める。"""
import calendar
import datetime as dt

from urllib.parse import quote

import feedparser

from .common import UA, get


def collect(cfg, ctx):
    items, errors = [], []
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=8)
    for feed in cfg["feeds"]:
        try:
            parsed = feedparser.parse(get(feed["url"], headers={"User-Agent": UA}).content)
            for e in parsed.entries[:40]:
                t = e.get("published_parsed") or e.get("updated_parsed")
                when = dt.datetime.fromtimestamp(calendar.timegm(t), dt.timezone.utc) if t else None
                if when and when < cutoff:
                    continue
                items.append({"kind": "news", "source": feed["name"], "lang": feed["lang"],
                              "title": e.get("title", "").strip(), "link": e.get("link", ""),
                              "date": when.date().isoformat() if when else ""})
        except Exception as e:
            errors.append(f"{feed['name']}: {e}")
    # Googleニュース検索(キー不要)。媒体ごとの話題量を見る
    locale = {"ja": "hl=ja&gl=JP&ceid=JP:ja", "en": "hl=en-US&gl=US&ceid=US:en"}
    for fid, langs in cfg.get("news_queries", {}).items():
        for lang, queries in langs.items():
            for q in queries:
                try:
                    url = f"https://news.google.com/rss/search?q={quote(q + ' when:14d')}&{locale[lang]}"
                    parsed = feedparser.parse(get(url).content)
                except Exception as e:
                    errors.append(f"gnews {fid}/{lang}: {e}")
                    continue
                for e in parsed.entries[:60]:
                    t = e.get("published_parsed")
                    title, _, outlet = e.get("title", "").rpartition(" - ")
                    items.append({"kind": "gnews", "format": fid, "lang": lang, "title": title or outlet,
                                  "source": outlet if title else "", "link": e.get("link", ""),
                                  "date": dt.date(*t[:3]).isoformat() if t else ""})
    if not items:
        raise RuntimeError("; ".join(errors[:3]) or "記事なし")
    return {"items": items, "note": f"{len(errors)}件失敗" if errors else ""}
