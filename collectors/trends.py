"""Googleトレンド(非公式ライブラリ pytrends。ブロックされやすいので取れたら使う程度)。"""
from .common import Skip


def collect(cfg, ctx):
    try:
        from pytrends.request import TrendReq
    except ImportError:
        raise Skip("pytrends 未インストール")
    py = TrendReq(hl="ja-JP", tz=-540, timeout=(10, 25))
    items = []
    for fid, words in cfg["keywords"].items():
        for w in words:
            py.build_payload([w], timeframe="today 5-y")
            df = py.interest_over_time()
            if df.empty:
                continue
            monthly = df[w].resample("MS").mean().round(1)
            items.append({"kind": "gtrend", "format": fid, "keyword": w,
                          "months": [[d.strftime("%Y%m"), float(v)] for d, v in monthly.items()]})
    if not items:
        raise RuntimeError("結果なし")
    return {"items": items}
