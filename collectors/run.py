"""全ソースを順に収集して data/snapshots/日付.json に保存する。

    python -m collectors.run            全部
    python -m collectors.run rss charts 指定したものだけ
失敗・キー未設定のソースは飛ばして続行する。
"""
import sys
import traceback
from collections import Counter

from . import artist_news, charts, discogs, lastfm, reddit, riaj, rss, trends, wikipedia, x_api, youtube
from .common import SNAPSHOTS, Skip, config, read_json, today, write_json

# wikipedia はチャート類から候補アーティストを受け取るので後ろに置く
SOURCES = [("charts", charts), ("youtube", youtube), ("lastfm", lastfm), ("reddit", reddit), ("rss", rss),
           ("riaj", riaj), ("wikipedia", wikipedia), ("discogs", discogs), ("trends", trends), ("x", x_api),
           ("artist_news", artist_news)]


SKIP_NAMES = {"various artists", "ヴァリアス・アーティスト", "soundtrack", "original soundtrack"}


def candidates(sources):
    """チャート等に出てきたアーティスト名を、出現回数の多い順に。"""
    n = Counter()
    for src in sources.values():
        for it in src.get("items", []):
            if it.get("artist"):
                n[it["artist"]] += 1
    return [name for name, _ in n.most_common() if "|" not in name and name.lower() not in SKIP_NAMES]


def main(only):
    cfg = config()
    path = SNAPSHOTS / f"{today().isoformat()}.json"
    fresh = {"date": today().isoformat(), "sources": {}}
    for name, mod in SOURCES:
        if only and name not in only:
            continue
        ctx = {"artist_candidates": candidates(read_json(path, fresh)["sources"])}
        try:
            result = mod.collect(cfg, ctx)
            entry = {"ok": True, "note": result.get("note", ""), "items": result["items"]}
            print(f"[ok]   {name}: {len(result['items'])}件 {result.get('note', '')}")
        except Skip as e:
            entry = {"ok": False, "skipped": True, "note": str(e), "items": []}
            print(f"[skip] {name}: {e}")
        except Exception as e:
            traceback.print_exc()
            entry = {"ok": False, "note": f"{type(e).__name__}: {e}"[:200], "items": []}
            print(f"[fail] {name}: {e}")
        # 1ソース終わるごとに読み直して書く(途中で止まっても、別プロセスと並行しても他の結果を消さない)
        snap = read_json(path, fresh)
        snap["sources"][name] = entry
        write_json(path, snap)
    print(f"saved {path}")


if __name__ == "__main__":
    main(set(sys.argv[1:]))
