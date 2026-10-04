"""スナップショットと年次データから、画面用の site/data/latest.json を作る。

    python -m analysis.build
"""
import csv
import datetime as dt
import math
import re
import shutil
from collections import defaultdict

from collectors.common import DATA, HISTORY, REPORTS, ROOT, SNAPSHOTS, config, read_json, today, write_json

from . import score
from .forecast import forecast_series

SITE_DATA = ROOT / "site" / "data"
KEEP_DAYS = 90
REGION_LABEL = {"jp": "日本", "us": "米国"}
SOURCE_LABEL = {"charts": "各国チャート(iTunes・Deezer)", "youtube": "YouTube急上昇", "lastfm": "Last.fm",
                "reddit": "Reddit掲示板", "rss": "音楽ニュース(RSS・Googleニュース)", "riaj": "日本レコード協会 月次統計", "wikipedia": "Wikipedia閲覧数",
                "discogs": "Discogs", "trends": "Googleトレンド", "x": "X(公式API)"}


def load_snapshots():
    paths = sorted(SNAPSHOTS.glob("*.json"))
    for old in paths[:-KEEP_DAYS]:  # リポジトリが膨らまないよう古い生データは消す(集計済みの履歴は残る)
        old.unlink()
    paths = paths[-KEEP_DAYS:]
    if not paths:
        raise SystemExit("スナップショットがありません。先に python -m collectors.run を実行してください。")
    snap = read_json(paths[-1])
    # 欠けているソースは直近で成功した日のものを借りる(一時的な失敗で画面が空にならないように)
    for p in reversed(paths[:-1][-7:]):
        old = read_json(p)
        for name, src in old["sources"].items():
            if src.get("ok") and not snap["sources"].get(name, {}).get("ok"):
                snap["sources"][name] = {**src, "note": f"{old['date']}の値を表示"}
    target = dt.date.fromisoformat(snap["date"]) - dt.timedelta(days=7)
    older = [p for p in paths[:-1] if dt.date.fromisoformat(p.stem) <= target]
    prev = read_json(older[-1]) if older else (read_json(paths[0]) if len(paths) > 1 else None)
    return snap, prev, len(paths)


def official_series():
    """data/history/formats.csv → {(region, format, metric): {...}}"""
    series = defaultdict(lambda: {"years": [], "values": [], "sources": set()})
    with open(HISTORY / "formats.csv", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            s = series[(r["region"], r["format"], r["metric"])]
            s["years"].append(int(r["year"]))
            s["values"].append(float(r["value"]))
            s["unit"] = r["unit"]
            s["sources"].add(r["source"])
    return series


def clip(x, lim):
    return max(-lim, min(lim, x))


def ytd_table(snap):
    """今年の途中経過(累計と前年同期)。日本は月次で自動取得、米国は半期レポートを CSV に手入力。"""
    out = {}
    with open(HISTORY / "formats_ytd.csv", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out[(r["region"], r["format"], r["metric"])] = {
                "year": int(r["year"]), "months": int(r["months"]), "period": r["period"],
                "value": float(r["value"]), "prev": float(r["prev"]), "source": r["source"]}
    for it in score.items(snap, "riaj", "ytd"):
        out[(it["region"], it["format"], it["metric"])] = it
    return out


def trend_word(growth_pct):
    if growth_pct is None:
        return "データなし"
    for limit, word in ((10, "大きく伸びている"), (3, "伸びている"), (-3, "横ばい"), (-10, "減っている")):
        if growth_pct >= limit:
            return word
    return "大きく減っている"


def used_demand(cfg, snap):
    """中古需要(Discogs)。欲しい人の数 ÷ 持っている人の数 が高いほど品薄。"""
    wanted = score.items(snap, "discogs", "wanted")
    cells = {}
    for w in wanted:
        c = cells.setdefault((w.get("scope", "all"), w["format"]), {"want": 0, "have": 0})
        c["want"] += w["want"]
        c["have"] += w["have"]

    # 「欲しい」登録の合計を日ごとに残し、1週間以上前と比べる
    hist = read_json(HISTORY / "demand.json", {})
    if cells:
        hist[snap["date"]] = {f"{scope}|{fid}": c["want"] for (scope, fid), c in cells.items()}
        hist = dict(sorted(hist.items())[-120:])
        write_json(HISTORY / "demand.json", hist)
    target = (dt.date.fromisoformat(snap["date"]) - dt.timedelta(days=7)).isoformat()
    older = [d for d in hist if d <= target]
    base = hist[older[-1]] if older else {}

    def cell(scope, fid):
        c = cells.get((scope, fid))
        if not c or not c["have"]:
            return None
        out = {"want": c["want"], "have": c["have"], "ratio": round(c["want"] / c["have"], 2)}
        before = base.get(f"{scope}|{fid}")
        if before:
            out["want_change_pct"] = round(100 * (c["want"] / before - 1), 1)
        return out

    formats = {fid: cell("all", fid) for fid in cfg["formats"]}
    by_genre = []
    for g in cfg["genres"]:
        row = {"genre": g["name"], **{fid: cell(g["name"], fid) for fid in cfg["formats"]}}
        if any(row[fid] for fid in cfg["formats"]):
            by_genre.append(row)

    def picks(rows, n):
        seen, out = set(), []
        for w in sorted((w for w in rows if w["have"] >= 30), key=lambda w: -w["want"] / w["have"]):
            work = re.sub(r"\s*=.*|\*|\s*\(\d+\)", "", w["title"].split(" - ")[0]).casefold().strip()  # 1アーティスト1枚
            if work not in seen:
                seen.add(work)
                out.append({**w, "ratio": round(w["want"] / w["have"], 2)})
        return out[:n]

    return {
        "formats": formats, "by_genre": by_genre, "since": older[-1] if older else None,
        "picks": {fid: picks([w for w in wanted if w["format"] == fid], 12) for fid in cfg["formats"]},
        "picks_japan": {fid: picks([w for w in wanted if w["format"] == fid and w.get("scope") == "japan"], 8)
                        for fid in cfg["formats"]},
    }


def media(cfg, snap):
    year = today().year
    ytd = ytd_table(snap)
    horizon = cfg["forecast"]["horizon"]

    out_series = []
    for (region, fid, metric), s in sorted(official_series().items()):
        if fid not in cfg["formats"]:
            continue
        item = {"id": f"{region}_{fid}_{metric}", "region": region, "region_label": REGION_LABEL.get(region, region),
                "format": fid, "label": cfg["formats"][fid]["label"], "metric": metric, "unit": s["unit"],
                "years": s["years"], "values": s["values"], "sources": sorted(s["sources"])}
        y = ytd.get((region, fid, metric))
        if y and y["prev"]:
            item["ytd"] = {"year": y["year"], "period": y["period"], "value": y["value"], "prev": y["prev"],
                           "yoy_pct": round(100 * (y["value"] / y["prev"] - 1), 1), "source": y["source"]}
        if s["years"][-1] >= year - 2 and len(s["years"]) >= 6:
            fc = forecast_series(s["years"], s["values"], cfg)
            if fc and y and y["prev"] and y["year"] == s["years"][-1] + 1:
                # 今年の着地見込み = 去年の実績 × (今年の累計 ÷ 前年同期)。残りの月が多いほど幅を広く取る
                est = s["values"][-1] * y["value"] / y["prev"]
                rest = forecast_series(s["years"] + [y["year"]], s["values"] + [est], cfg) or fc
                spread = 0.25 * (1 - y["months"] / 12)
                fc = {**rest,
                      "years": [y["year"]] + rest["years"][:horizon - 1],
                      "base": [round(est, 3)] + rest["base"][:horizon - 1],
                      "lo": [round(est * math.exp(-spread), 3)] + rest["lo"][:horizon - 1],
                      "hi": [round(est * math.exp(spread), 3)] + rest["hi"][:horizon - 1],
                      "growth_pct": item["ytd"]["yoy_pct"], "nowcast": True, "mape": fc.get("mape")}
            item["forecast"] = fc
        out_series.append(item)

    # レコードとCDのバランス(実績+予想)。レコード ÷(レコード+CD)
    by_id = {s["id"]: s for s in out_series}
    balance = []
    for region in ("jp", "us"):
        for metric, mlabel in (("units", "枚数"), ("value", "金額")):
            v, c = by_id.get(f"{region}_vinyl_{metric}"), by_id.get(f"{region}_cd_{metric}")
            if not (v and c and v.get("forecast") and c.get("forecast")):
                continue
            ys = v["years"] + v["forecast"]["years"]
            vv, cc = v["values"] + v["forecast"]["base"], c["values"] + c["forecast"]["base"]
            pct = [round(100 * a / (a + b), 1) for a, b in zip(vv, cc)]
            balance.append({"region": region, "region_label": REGION_LABEL[region], "metric": mlabel, "years": ys,
                            "vinyl_pct": pct, "actual_until": v["years"][-1]})

    demand = used_demand(cfg, snap)
    gnews = score.items(snap, "rss", "gnews")

    # 媒体ごとの「いま」を一言で
    now = []
    for fid, f in cfg["formats"].items():
        lines, growths = [], []
        for region in ("jp", "us"):
            s = by_id.get(f"{region}_{fid}_units")
            if s and s.get("ytd"):
                y = s["ytd"]
                growths.append(y["yoy_pct"])
                lines.append(f"{REGION_LABEL[region]}の新品: {y['year']}年{y['period']}の枚数は前年より {y['yoy_pct']:+.0f}%")
        d = demand["formats"].get(fid)
        if d:
            txt = (f"中古: 人気盤は品薄(欲しい人が、持っている人の {d['ratio']}倍)" if d["ratio"] >= 1 else
                   f"中古: 人気盤は出回っている(欲しい人は、持っている人の {d['ratio']}倍)")
            if d.get("want_change_pct") is not None:
                txt += f"。欲しい人は前回より {d['want_change_pct']:+.1f}%"
            lines.append(txt)
        n = sum(1 for g in gnews if g["format"] == fid)
        if n:
            lines.append(f"この2週間の関連ニュース: {n}本")
        g = round(sum(growths) / len(growths), 1) if growths else None
        now.append({"format": fid, "label": f["label"], "verdict": trend_word(g), "growth_pct": g, "lines": lines})

    return {"series": out_series, "balance": balance, "demand": demand, "now": now,
            "signals": score.format_signals(snap, cfg)}


def genres(cfg, snap, prev):
    year = today().year
    discogs = read_json(HISTORY / "discogs.json", {"format_year": {}, "style_year": {}})
    fy = discogs["format_year"]
    wiki = {i["name"]: i for i in score.items(snap, "wikipedia", "wiki_genre")}
    tags = {i["name"]: i for i in score.items(snap, "lastfm", "lastfm_tag")}
    total_en = score.wiki_totals(snap).get("en")
    out = []
    for g in cfg["genres"]:
        row = {"name": g["name"], "reasons": []}
        sy = discogs["style_year"].get(g["name"])
        if sy and fy:
            # 直近年は登録が追いついていないので、同じ年の全体(3フォーマット計)に対する割合で見る
            years = sorted(int(y) for y in sy if int(y) < year)
            vals = [round(1000 * sy[str(y)] / max(sum(fy[f].get(str(y), 0) for f in fy), 1), 2) for y in years]
            if any(vals):
                row["discogs"] = {"years": years, "values": vals, "forecast": forecast_series(years, vals, cfg)}
                if len(vals) >= 4 and vals[-4] > 0:
                    ch = vals[-1] / vals[-4]
                    row["discogs_3y"] = round(ch, 2)
                    row["reasons"].append(f"新しく出る作品に占める割合が3年で {score.pct(ch)}")
        w = wiki.get(g["name"])
        if w:
            months = score.relative(w["months"], total_en)
            years, vals = score.yearly(months, year)
            vals = [round(v, 1) for v in vals]
            if len(years) >= 4:
                row["wiki"] = {"years": years, "values": vals, "forecast": forecast_series(years, vals, cfg)}
            yoy = score.yoy_recent(months)
            if yoy:
                row["wiki_yoy"] = round(yoy, 2)
                row["reasons"].append(f"Wikipediaで調べる人が1年前より {score.pct(yoy)}")
        if g["name"] in tags:
            row["lastfm_reach"] = tags[g["name"]]["reach"]
        # 勢い: 直近の関心(Wikipedia)とリリース比率の伸びを半々で
        parts = [math.log(x) for x in (row.get("wiki_yoy"), row.get("discogs_3y")) if x]
        row["score"] = round(50 + 50 * clip(sum(parts) / len(parts), 1)) if parts else None
        out.append(row)
    out.sort(key=lambda r: -(r["score"] or 0))
    return {"tracked": out, "charts": score.chart_genres(snap, prev)}


def ideas(snap, cfg):
    news = score.items(snap, "rss", "news")
    for n in news:
        n["formats"] = [fid for fid, f in cfg["formats"].items() if score.mentions(n["title"], f["keywords"])]
    news.sort(key=lambda n: n["date"], reverse=True)
    posts = sorted(score.items(snap, "reddit", "reddit_post"), key=lambda p: -p["score"])[:40]
    gnews = sorted(score.items(snap, "rss", "gnews"), key=lambda n: n["date"], reverse=True)
    by_format = {fid: [n for n in gnews if n["format"] == fid][:25] for fid in cfg["formats"]}
    return {"news": news[:80], "reddit": posts, "by_format": by_format}


def latest_reports():
    out = {}
    for kind, pattern in (("weekly", "*-W*.md"), ("monthly", "[0-9][0-9][0-9][0-9]-[0-9][0-9].md")):
        files = sorted(REPORTS.glob(pattern))
        if files:
            out[kind] = {"name": files[-1].stem, "md": files[-1].read_text(encoding="utf-8")}
    return out


def build():
    cfg = config()
    snap, prev, days = load_snapshots()
    arts = score.artists(snap, prev)

    # 順位の推移を残す(前回比の表示と、後から当たり外れを振り返るため)
    hist = read_json(HISTORY / "scores.json", {})
    hist[snap["date"]] = {a["name"]: a["score"] for a in arts[:150]}
    hist = dict(sorted(hist.items())[-120:])
    write_json(HISTORY / "scores.json", hist)
    dates = sorted(d for d in hist if d < snap["date"])
    if dates:
        last = hist[dates[-1]]
        for a in arts:
            if a["name"] in last:
                a["delta"] = a["score"] - last[a["name"]]

    latest = {
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
        "date": snap["date"], "days_collected": days, "compared_with": prev["date"] if prev else None,
        "sources": [{"name": SOURCE_LABEL.get(n, n), "ok": s.get("ok", False), "skipped": s.get("skipped", False),
                     "note": s.get("note", ""), "count": len(s.get("items", []))}
                    for n, s in snap["sources"].items()],
        "artists": arts[:120],
        "frontier": [a for a in arts if a["frontier"]][:40],
        "genres": genres(cfg, snap, prev),
        "media": media(cfg, snap),
        "ideas": ideas(snap, cfg),
        "reports": latest_reports(),
    }
    write_json(DATA / "latest.json", latest)
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    shutil.copy(DATA / "latest.json", SITE_DATA / "latest.json")
    print(f"built latest.json: artists={len(arts)} frontier={len(latest['frontier'])} "
          f"series={len(latest['media']['series'])}")
    return latest


if __name__ == "__main__":
    build()
