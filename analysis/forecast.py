"""年単位の予想。

方法: 直近の年ごとの伸び率(対数)を新しい年ほど重く平均し、その伸びが毎年 damping 倍に弱まる
前提で先へ延ばす(伸びも落ち込みも永遠には続かないと仮定)。幅は過去の伸び率のばらつきから。
過去検証: 最後の3年を隠して同じ方法で予想し、実績とのずれ(平均%)を出す。
"""
import math
import statistics


def _growths(values):
    return [math.log(b / a) for a, b in zip(values, values[1:]) if a > 0 and b > 0]


def project(years, values, horizon=5, damping=0.8, nudge=0.0):
    g_all = _growths(values)
    if len(g_all) < 3 or values[-1] <= 0:
        return None
    recent = g_all[-5:]
    weights = range(1, len(recent) + 1)
    g = sum(w * x for w, x in zip(weights, recent)) / sum(weights) + nudge
    sd = statistics.pstdev(g_all[-8:]) or 0.05
    out = {"years": [], "base": [], "lo": [], "hi": []}
    cum = 0.0
    for h in range(1, horizon + 1):
        cum += g * damping ** h
        base = values[-1] * math.exp(cum)
        spread = sd * math.sqrt(h)
        out["years"].append(years[-1] + h)
        out["base"].append(round(base, 3))
        out["lo"].append(round(base * math.exp(-spread), 3))
        out["hi"].append(round(base * math.exp(spread), 3))
    out["growth_pct"] = round((math.exp(g * damping) - 1) * 100, 1)  # 来年の見込み伸び率
    return out


def backtest(years, values, damping=0.8, hold=3):
    """最後の hold 年を隠して予想したときの平均誤差(%)。データ不足なら None。"""
    if len(values) < hold + 5:
        return None
    fc = project(years[:-hold], values[:-hold], hold, damping)
    if not fc:
        return None
    errs = [abs(p - a) / a for p, a in zip(fc["base"], values[-hold:]) if a > 0]
    return round(100 * sum(errs) / len(errs), 1) if errs else None


def forecast_series(years, values, cfg, nudge=0.0):
    f = cfg["forecast"]
    fc = project(years, values, f["horizon"], f["damping"], nudge)
    if fc:
        fc["mape"] = backtest(years, values, f["damping"])
    return fc
