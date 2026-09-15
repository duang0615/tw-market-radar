# -*- coding: utf-8 -*-
"""72 小時熱度計分。

公式（規格書第六節）：
    新聞量      30%
    新聞量增速  20%
    社群提及量  20%
    社群增速    15%
    官方重大事件 10%
    市場異動     5%

重點在「available-data weighted scoring」：
某個來源整個沒資料時，不是把那一項算 0 分——那會讓所有產業一起被拉低，
排名失去意義。正確做法是把那一項的權重拿掉、其餘權重重新正規化，
然後誠實地在頁面上標出 Data Coverage 是多少。
"""
import math
from datetime import timedelta

from common import now

WEIGHTS = {
    "news_volume": 0.30,
    "news_accel": 0.20,
    "social_volume": 0.20,
    "social_accel": 0.15,
    "official": 0.10,
    "market": 0.05,
}


def _log_norm(values):
    """計數類訊號先取 log1p 再正規化。

    新聞則數是重尾分布：某個產業 30 則、其他 1～10 則，
    直接 min-max 會讓第一名拿 100、其他全部擠在 0～30，排名等於沒有鑑別度。
    取對數之後差距才看得出層次。
    """
    return _norm({k: math.log1p(max(0.0, v)) for k, v in values.items()})


def _norm(values):
    """把一組數字壓到 0～100。全部一樣時給 50，不要讓分母變 0。"""
    if not values:
        return {}
    lo, hi = min(values.values()), max(values.values())
    if hi - lo < 1e-9:
        return {k: (50.0 if hi > 0 else 0.0) for k in values}
    return {k: (v - lo) / (hi - lo) * 100.0 for k, v in values.items()}


ACCEL_CLIP = 200.0       # 計分時把加速度夾在 ±200%，避免單一離群值壓扁其他人


def _accel(recent, baseline_rate):
    """加速度：最近 24 小時的量 vs 前 48 小時的每日平均。

    回傳百分比變化。基期是 0 而最近有量 → 視為 +100%（新話題）。
    """
    if baseline_rate <= 0:
        return 100.0 if recent > 0 else 0.0
    return (recent - baseline_rate) / baseline_rate * 100.0


def _clip(v, lo=-ACCEL_CLIP, hi=ACCEL_CLIP):
    return max(lo, min(hi, v))


def compute(industries, events, quotes, window_hours=72):
    """回傳每個產業的分項與總分。"""
    t0 = now()
    recent_cut = t0 - timedelta(hours=24)

    raw = {}
    for ind in industries:
        raw[ind["id"]] = {"news": 0, "news_all": 0, "news_recent": 0, "news_old": 0,
                          "social": 0, "social_recent": 0, "social_old": 0,
                          "official": 0, "events": 0}

    for ev in events:
        dt = ev.get("_dt")
        is_recent = bool(dt and dt >= recent_cut)
        types = set(ev.get("source_types", []))
        n = ev.get("count", 1)
        # 「量」只算 broad 來源（不分產業、一視同仁抓回來的）。
        # Google News 是每個產業各查一次、每次都回到上限，
        # 拿它的筆數跨產業比較等於在比「Google 回幾筆」，不是比熱度。
        nb = ev.get("broad_count", n)
        for iid in ev.get("industries", []):
            if iid not in raw:
                continue
            r = raw[iid]
            r["events"] += 1
            if "official" in types:
                r["official"] += nb
            if "social" in types:
                r["social"] += nb
                r["social_recent" if is_recent else "social_old"] += nb
            if "news" in types:
                r["news"] += nb
                r["news_all"] += n
                # 加速度是同一個產業「近 24h vs 前 48h」的比值，
                # 不跨產業比大小，所以用全部新聞（含 Google News）算才夠靈敏。
                r["news_recent" if is_recent else "news_old"] += n

    # 哪些訊號整體有資料？完全沒有的就不計入權重
    has = {
        "news_volume": any(r["news"] for r in raw.values()),
        "news_accel": any(r["news_all"] for r in raw.values()),
        "social_volume": any(r["social"] for r in raw.values()),
        "social_accel": any(r["social"] for r in raw.values()),
        "official": any(r["official"] for r in raw.values()),
        "market": bool(quotes),
    }

    # 市場異動：該產業成分股當日漲跌幅的平均絕對值
    stock_map = {i["id"]: i.get("stocks", []) for i in industries}
    market = {}
    for iid, codes in stock_map.items():
        vals = [abs(quotes[c]) for c in codes if c in quotes]
        market[iid] = sum(vals) / len(vals) if vals else 0.0

    news_v = {k: r["news"] for k, r in raw.items()}
    social_v = {k: r["social"] for k, r in raw.items()}
    offi_v = {k: r["official"] for k, r in raw.items()}
    base_h = max(1.0, window_hours - 24)
    news_a = {k: _accel(r["news_recent"], r["news_old"] / base_h * 24.0)
              for k, r in raw.items()}
    social_a = {k: _accel(r["social_recent"], r["social_old"] / base_h * 24.0)
                for k, r in raw.items()}

    n_news_v, n_social_v = _log_norm(news_v), _log_norm(social_v)
    n_offi, n_market = _log_norm(offi_v), _norm(market)
    n_news_a = _norm({k: _clip(v) for k, v in news_a.items()})
    n_social_a = _norm({k: _clip(v) for k, v in social_a.items()})

    out = {}
    for ind in industries:
        iid = ind["id"]
        parts = {
            "news_volume": n_news_v.get(iid, 0.0),
            "news_accel": n_news_a.get(iid, 0.0),
            "social_volume": n_social_v.get(iid, 0.0),
            "social_accel": n_social_a.get(iid, 0.0),
            "official": n_offi.get(iid, 0.0),
            "market": n_market.get(iid, 0.0),
        }
        live = {k: w for k, w in WEIGHTS.items() if has[k]}
        total_w = sum(live.values())
        score = (sum(parts[k] * w for k, w in live.items()) / total_w) if total_w else 0.0
        out[iid] = {
            "heat_score": round(score, 1),
            "acceleration": round(news_a.get(iid, 0.0), 1),
            "news_count": raw[iid]["news"],
            "news_all": raw[iid]["news_all"],
            "social_mentions": raw[iid]["social"],
            "official_events": raw[iid]["official"],
            "event_count": raw[iid]["events"],
            "market_move": round(market.get(iid, 0.0), 2),
            "coverage": round(total_w / sum(WEIGHTS.values()) * 100),
            "parts": {k: round(v, 1) for k, v in parts.items()},
            "missing": sorted([k for k, v in has.items() if not v]),
        }
    return out, has


def trend(acc):
    if acc >= 25:
        return "rising"
    if acc <= -25:
        return "falling"
    return "flat"
