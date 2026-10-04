"""日本レコード協会の月次生産実績(キー不要)。今年の累計と前年同期を取り、年の途中でも動きを掴む。"""
from .common import get_json

BASE = "https://www.riaj.or.jp/z/data/json/sj/"
ROWS = {"cd": "CD_ALL", "vinyl": "AD", "cassette": "CAS"}
PAGE = "https://www.riaj.or.jp/data/monthly/"


def collect(cfg, ctx):
    latest = get_json(BASE + "monthly_info.json")["year_months"][0]  # 例 "2026-08"
    year, month = int(latest[:4]), int(latest[5:])
    audio = get_json(f"{BASE}monthly_{latest.replace('-', '')}.json")["results"]["audio"]
    items = []
    for fid, row in ROWS.items():
        t = audio[row]["TOTAL"]
        for metric, key in (("units", "qty"), ("value", "amt")):
            items.append({"kind": "ytd", "region": "jp", "format": fid, "metric": metric, "year": year,
                          "months": month, "period": f"1〜{month}月",
                          "value": t[f"ruikei_{key}"], "prev": t[f"ruikei_prev_{key}"],
                          "month_value": t[f"tangetsu_{key}"], "month_prev": t[f"tangetsu_prev_{key}"],
                          "source": PAGE})
    return {"items": items}
