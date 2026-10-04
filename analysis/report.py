"""Claude API で週次/月次の日本語レポートを書く。ANTHROPIC_API_KEY が必要。

    python -m analysis.report weekly
    python -m analysis.report monthly
出力: data/reports/2026-W40.md / 2026-10.md(画面の「予測」タブに表示される)
"""
import json
import os
import sys

import anthropic

from collectors.common import DATA, REPORTS, read_json, today

MODEL = os.environ.get("MUSIC_RADAR_MODEL", "claude-opus-5-5")

SYSTEM = """あなたは音楽市場のアナリストです。読み手は、中古のレコード/CD/カセットを仕入れて販売し、
SNSや短尺動画でも発信している個人事業者です。商売の軸は中古なので、中古の需要(used_demand_discogs)を主に、
新品の生産統計は「世の中の流れ」と「数年後の中古流通量」を読む材料として扱ってください。渡されたデータ(自動収集の集計結果)だけを根拠に、
iPhoneで読む日本語レポートを書いてください。

書き方:
- 冒頭に「今回の結論」を3点、箇条書きで。忙しい人はここだけ読みます。
- 数字を挙げるときはデータにある値をそのまま使い、データに無い数字や出来事を作らない。
- 「なぜそう読めるか」を必ず添える。根拠が弱いもの(1つの指標だけ、過去検証のずれが大きい等)は弱いと明記する。
- 予想はあくまで推定。断定せず、外れるとしたら何が原因になりそうかも書く。
- 見出しは「## 」、箇条書きは「- 」、強調は「**」だけを使う。表・リンク・コードは使わない。
- 専門用語や略語は使わず、ふだんの言葉で書く。「前年比」「品薄」程度はよいが、統計用語(中央値、z値など)は避ける。
- 新品の数字は this_year_so_far(今年の途中経過)を優先して読む。年次の数字だけで判断しない。"""

WEEKLY = """今週の週次レポートを書いてください(800〜1200字)。構成:
## 今回の結論
## 伸びているアーティスト(なぜ伸びているか、仕入れ・発信でどう使えるか)
## ジャンルの動き
## レコード・CD・カセットの動き(中古の需要と、新品の今年の途中経過)
## 仕入れのヒント(品薄なジャンル・盤)
## 今週のネタ(SNS・動画向けに3つ、切り口つき)
## 来週見るべき点"""

MONTHLY = """今月の月次レポートを書いてください(1500〜2200字)。年単位の見通しを中心に。構成:
## 今回の結論
## レコード・CD・カセットの今後(今年の着地見込みと数年先、レコードとCDのバランス、日本と海外の違い)
## 中古の需要と仕入れへの示唆(媒体×ジャンルで、増やす/様子見/絞る)
## 伸びるジャンル・縮むジャンル(年次の予想線から)
## 今月の注目アーティスト
## 予想が外れるとしたら(リスク要因)と、過去検証のずれから見た信頼度"""


def digest(d):
    """latest.json からレポートに必要な部分だけを抜き出す。"""
    def fc(s):
        f = s.get("forecast")
        return f and {"years": f["years"], "base": f["base"], "lo": f["lo"], "hi": f["hi"],
                      "next_year_growth_pct": f["growth_pct"], "backtest_error_pct": f.get("mape")}

    m = d["media"]
    dm = m["demand"]
    return {
        "date": d["date"], "days_collected": d["days_collected"],
        "sources": [{k: s[k] for k in ("name", "ok", "note")} for s in d["sources"]],
        "formats_now": m["now"],
        "new_production_official_stats": [
            {"region": s["region_label"], "format": s["label"], "metric": s["metric"], "unit": s["unit"],
             "years": s["years"], "values": s["values"], "this_year_so_far": s.get("ytd"), "forecast": fc(s)}
            for s in m["series"]],
        "vinyl_share_of_vinyl_plus_cd": m["balance"],
        "used_demand_discogs": {
            "explain": "ratio = 欲しい人 ÷ 持っている人(各区分で欲しい登録が多い上位50作品の合計)。1超は品薄",
            "by_format": dm["formats"], "by_genre": dm["by_genre"],
            "scarce_releases": {f: [{k: w.get(k) for k in ("title", "style", "country", "year", "want", "have",
                                                            "ratio", "lowest_jpy")} for w in rows[:8]]
                                for f, rows in dm["picks"].items()},
            "scarce_japanese_releases": {f: [{k: w.get(k) for k in ("title", "style", "year", "ratio")}
                                             for w in rows[:6]] for f, rows in dm["picks_japan"].items()}},
        "format_news_last_14_days": {f: [n["title"] for n in rows[:20]] for f, rows in d["ideas"]["by_format"].items()},
        "artists_top": [{k: a.get(k) for k in ("name", "score", "delta", "genre", "regions", "reasons", "frontier")}
                        for a in d["artists"][:40]],
        "up_and_coming": [{k: a.get(k) for k in ("name", "score", "genre", "reasons")} for a in d["frontier"][:20]],
        "genres": [{"name": g["name"], "score": g["score"], "reasons": g["reasons"],
                    "share_of_new_releases": g.get("discogs") and {"years": g["discogs"]["years"][-6:],
                                                                   "values": g["discogs"]["values"][-6:],
                                                                   "forecast": fc(g["discogs"])}}
                   for g in d["genres"]["tracked"]],
        "chart_genres": {r: v[:6] for r, v in d["genres"]["charts"].items() if r in ("all", "jp", "us", "gb", "kr")},
        "music_news": [{"title": n["title"], "source": n["source"]} for n in d["ideas"]["news"][:60]],
        "reddit": [{"title": p["title"], "sub": p["sub"], "score": p["score"]} for p in d["ideas"]["reddit"][:25]],
    }


def write(kind):
    d = read_json(DATA / "latest.json")
    if not d:
        raise SystemExit("data/latest.json がありません。先に python -m analysis.build を実行してください。")
    client = anthropic.Anthropic()
    prompt = (WEEKLY if kind == "weekly" else MONTHLY) + "\n\n<data>\n" + \
        json.dumps(digest(d), ensure_ascii=False) + "\n</data>"
    with client.messages.stream(
        model=MODEL, max_tokens=16000, system=SYSTEM,
        thinking={"type": "adaptive"}, output_config={"effort": "medium"},
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        msg = stream.get_final_message()
    if msg.stop_reason == "refusal":
        raise SystemExit("モデルが回答を控えました。レポートは更新しません。")
    text = "".join(b.text for b in msg.content if b.type == "text").strip()
    if not text:
        raise SystemExit(f"本文が空でした(stop_reason={msg.stop_reason})")
    t = today()
    name = f"{t.isocalendar().year}-W{t.isocalendar().week:02d}" if kind == "weekly" else t.strftime("%Y-%m")
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / f"{name}.md").write_text(text + "\n", encoding="utf-8")
    print(f"wrote {name}.md ({len(text)}字, in={msg.usage.input_tokens} out={msg.usage.output_tokens})")


if __name__ == "__main__":
    kind = sys.argv[1] if len(sys.argv) > 1 else "weekly"
    if kind not in ("weekly", "monthly"):
        raise SystemExit("weekly か monthly を指定してください")
    write(kind)
