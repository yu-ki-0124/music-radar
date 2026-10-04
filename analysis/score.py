"""収集データから「いまの勢い」を点数化する。"""
import math
import re
import statistics
from collections import Counter, defaultdict

REGION_JA = {"jp": "日本", "us": "米国", "gb": "英国", "kr": "韓国", "de": "ドイツ", "fr": "フランス", "br": "ブラジル",
             "mx": "メキシコ", "in": "インド", "ng": "ナイジェリア", "au": "豪州", "id": "インドネシア", "global": "世界"}


SKIP = {"various artists", "ヴァリアス アーティスト", "soundtrack", "original soundtrack"}


def key(name):
    return re.sub(r"[^\w]+", " ", name.casefold()).strip()


def mentions(title, keywords):
    """見出しがキーワードを含むか。英数字の語は単語単位で照合する("LCD" を "CD" と数えない)。"""
    t = title.lower()
    for kw in keywords:
        kw = kw.strip().lower()
        if kw.isascii():
            if re.search(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])", t):
                return True
        elif kw in t:
            return True
    return False


def items(snap, source, kind=None):
    out = (snap or {}).get("sources", {}).get(source, {}).get("items", [])
    return [i for i in out if kind is None or i.get("kind") == kind]


def mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def pct(x):
    return f"{(x - 1) * 100:+.0f}%"


def _chart_table(snap):
    """アーティスト → {(チャート, 国): 最高位}"""
    table = defaultdict(dict)
    names, genres = {}, defaultdict(Counter)
    for it in items(snap, "charts") + items(snap, "lastfm", "lastfm_artist"):
        k = key(it["artist"])
        if not k or k in SKIP:
            continue
        chart = it.get("chart", "lastfm")
        slot = (chart, it["region"])
        table[k][slot] = min(table[k].get(slot, 999), it["pos"])
        names.setdefault(k, it["artist"])
        if it.get("genre"):
            genres[k][it["genre"]] += 1
    return table, names, genres


def artists(snap, prev):
    table, names, genres = _chart_table(snap)
    prev_table = _chart_table(prev)[0] if prev else {}
    wiki = {key(i["name"]): i for i in items(snap, "wikipedia", "wiki_artist")}
    checked = {key(n) for i in items(snap, "wikipedia", "wiki_checked") for n in i["names"]}

    yt = defaultdict(lambda: {"vpd": 0, "regions": set(), "ids": set()})
    for v in items(snap, "youtube", "yt_video"):
        k = key(v["artist"])
        names.setdefault(k, v["artist"])
        if v["id"] not in yt[k]["ids"]:
            yt[k]["vpd"] += v["views_per_day"]
            yt[k]["ids"].add(v["id"])
        yt[k]["regions"].add(v["region"])
    yt_sorted = sorted(y["vpd"] for y in yt.values())

    fresh = Counter(key(p["artist"]) for p in items(snap, "reddit", "reddit_post") if p.get("artist"))

    out = []
    for k in set(table) | set(yt):
        slots = table.get(k, {})
        regions = sorted({r for _, r in slots} | yt[k]["regions"] if k in yt else {r for _, r in slots})
        parts, reasons = [], []  # parts: (重み, 0〜1の値)

        countries = [r for r in regions if r != "global"]
        breadth = len(regions)
        parts.append((25, min(breadth, 8) / 8))
        if breadth >= 2:
            reasons.append(f"{breadth}か国・地域でランクイン(" + "・".join(REGION_JA.get(r, r) for r in regions[:5])
                           + ("ほか" if breadth > 5 else "") + ")")
        best = min(slots.values()) if slots else None

        # 閲覧数の伸び: 横ばい=0、4倍=満点。データが無いアーティストは 0 扱い(広さだけで高得点にしない)
        w = wiki.get(k)
        growth = base = None
        momentum = 0.0
        if w:
            d = w["daily"]
            base, recent = mean(d[-35:-7]), mean(d[-7:])
            if base >= 20:
                growth = recent / base
                momentum = min(max(math.log2(max(growth, 0.01)), -1), 2) / 2
                if growth >= 1.15 or growth <= 0.85:
                    reasons.append(f"Wikipediaで調べる人が先月の{growth:.1f}倍" + ("" if growth > 1 else "に減少"))
        parts.append((40, momentum))

        is_new = None
        if prev_table:
            before = prev_table.get(k, {})
            is_new = not before
            gained = len(set(slots) - set(before))
            climbed = sum(1 for s, p in slots.items() if s in before and before[s] - p >= 10)
            parts.append((20, min((gained + climbed) / 4, 1)))
            if is_new:
                reasons.append("今週はじめてランクイン")
            elif gained:
                reasons.append(f"ランクインした国・チャートが{gained}件増えた")
            if climbed:
                reasons.append(f"{climbed}件のチャートで10位以上アップ")

        if yt_sorted:
            rank = sum(1 for x in yt_sorted if x <= yt[k]["vpd"]) / len(yt_sorted) if k in yt else 0
            parts.append((15, rank))
        if k in yt:
            reasons.append(f"YouTube急上昇 {len(yt[k]['regions'])}か国・1日あたり約{yt[k]['vpd']:,}再生")
        if fresh.get(k):
            parts.append((5, 1))
            reasons.append("海外掲示板の新譜スレで話題")

        score = round(100 * sum(wt * v for wt, v in parts) / sum(wt for wt, _ in parts))
        no_article = k in checked and k not in wiki
        frontier = bool((growth and growth >= 1.25 and base < 3000)
                        or (no_article and len(countries) >= 2))
        if no_article and len(countries) >= 2:
            reasons.append("英語版Wikipediaに記事がまだ無い(世界的にはこれから)")
        spark = [round(mean(w["daily"][i:i + 7])) for i in range(0, len(w["daily"]) - 6, 7)] if w else []
        out.append({"name": names[k], "score": max(score, 0), "frontier": frontier, "reasons": reasons,
                    "regions": regions, "best": best, "genre": (genres[k].most_common(1) or [("", 0)])[0][0],
                    "growth": round(growth, 2) if growth else None, "base": round(base) if base else None,
                    "new": bool(is_new), "spark": spark})
    out.sort(key=lambda a: (-a["score"], a["name"]))
    return out


def chart_genres(snap, prev):
    """チャート上のジャンル構成比(国別)。"""
    def shares(s):
        by = defaultdict(Counter)
        for it in items(s, "charts"):
            if it["chart"].startswith("itunes") and it.get("genre"):
                by[it["region"]][it["genre"]] += 1
                by["all"][it["genre"]] += 1
        return {r: {g: n / sum(c.values()) for g, n in c.items()} for r, c in by.items()}

    now, before = shares(snap), shares(prev) if prev else {}
    out = {}
    for region, sh in now.items():
        rows = []
        for g, s in sorted(sh.items(), key=lambda x: -x[1])[:10]:
            row = {"genre": g, "share": round(100 * s, 1)}
            if region in before:
                row["delta"] = round(100 * (s - before[region].get(g, 0)), 1)
            rows.append(row)
        out[region] = rows
    return out


def yoy_recent(months, n=3):
    """直近 n か月(当月を除く)と前年同月の比。季節要因を消すため前年同月と比べる。"""
    m = dict(months[:-1]) if months else {}
    keys = sorted(m)[-n:]
    now = sum(m[k] for k in keys)
    last = sum(m.get(f"{int(k[:4]) - 1}{k[4:]}", 0) for k in keys)
    return now / last if last else None


def wiki_totals(snap):
    """言語 → サイト全体の月次閲覧数。"""
    return {i["lang"]: dict(i["months"]) for i in items(snap, "wikipedia", "wiki_total")}


def relative(months, total):
    """記事の閲覧数を、サイト全体100万閲覧あたりに直す(Wikipedia自体の増減を差し引く)。"""
    return [[ym, 1e6 * v / total[ym]] for ym, v in months if total.get(ym)] if total else months


def yearly(months, this_year):
    """月次 → 完結した年の合計。"""
    tot, cnt = Counter(), Counter()
    for ym, v in months:
        tot[int(ym[:4])] += v
        cnt[int(ym[:4])] += 1
    years = sorted(y for y in tot if cnt[y] == 12 and y < this_year)
    return years, [tot[y] for y in years]


def format_signals(snap, cfg):
    """フォーマットごとの足もとの指標。"""
    out = {}
    news = items(snap, "rss", "news")
    totals = wiki_totals(snap)
    for fid, f in cfg["formats"].items():
        sig = {"label": f["label"], "wiki": {}, "notes": []}
        for lang in ("en", "ja"):
            merged = Counter()
            for it in items(snap, "wikipedia", "wiki_format"):
                if it["name"] == fid and it["lang"] == lang:
                    merged.update(dict(it["months"]))
            if merged:
                months = relative(sorted(merged.items()), totals.get(lang))
                sig["wiki"][lang] = {"yoy": yoy_recent(months), "months": [[ym, round(v, 2)] for ym, v in months[-36:]]}
        sig["news"] = sum(1 for n in news if mentions(n["title"], f["keywords"]))
        subs = [s for s in items(snap, "reddit", "reddit_sub") if s.get("format") == fid]
        if subs:
            sig["reddit"] = {"subscribers": sum(s["subscribers"] for s in subs),
                             "week_comments": sum(s["week_comments"] for s in subs)}
        out[fid] = sig
    return out
