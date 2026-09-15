# -*- coding: utf-8 -*-
"""pipeline 單元測試：pytest -q

重點測「不報錯但結果是錯的」那幾種狀況，不是測 happy path。
"""
import os
import sys
from datetime import timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))

import classify as C          # noqa: E402
import dedupe as D            # noqa: E402
import normalize as N         # noqa: E402
import score as S             # noqa: E402
from common import now        # noqa: E402

INDS = [
    {"id": "asic", "name": "ASIC", "group": "AI",
     "keywords": ["ASIC", "客製化晶片"], "stocks": ["3661"]},
    {"id": "robotics", "name": "機器人", "group": "新應用",
     "keywords": ["機器人"], "exclude": ["聊天機器人"], "stocks": ["2049"]},
    {"id": "cooling", "name": "散熱", "group": "零組件",
     "keywords": ["液冷"], "stocks": ["3017"]},
]
STOCKS = [
    {"code": "3661", "name": "世芯-KY", "industries": ["asic"]},
    {"code": "2049", "name": "上銀", "industries": ["robotics"]},
    {"code": "3017", "name": "奇鋐", "industries": ["cooling"]},
]


def mk(title, hours_ago=1, stype="news", url=None, snapshot=False, broad=True, code=None):
    return {"title": title, "url": url if url is not None else "http://x/" + title,
            "source": "t", "_dt": now() - timedelta(hours=hours_ago),
            "summary": "", "language": "zh", "source_type": stype,
            "_snapshot": snapshot, "_broad": broad, "_code": code}


# ── normalize ────────────────────────────────────────────────────
def test_normalize_drops_out_of_window():
    got = N.normalize([mk("新的", 1), mk("太舊的", 200)], window_hours=72)
    assert [g["title"] for g in got] == ["新的"]


def test_normalize_keeps_snapshot_even_if_old():
    """重大訊息是每日快照檔，連假時整批都是舊的，不能被時間窗砍掉。"""
    got = N.normalize([mk("重大訊息", 500, "official", snapshot=True)], window_hours=72)
    assert len(got) == 1


def test_normalize_strips_google_news_tail():
    got = N.normalize([mk("台積電法說會 - 經濟日報", 1)])
    assert got[0]["title_key"] == "台積電法說會"


def test_normalize_drops_noise():
    got = N.normalize([mk("鉅亨速報 - Factset 最新調查：某某上修", 1)])
    assert got == []


def test_canon_url_strips_tracking():
    a = N.canon_url("https://a.com/x?utm_source=fb&id=3")
    b = N.canon_url("https://a.com/x?id=3")
    assert a == b


# ── classify ─────────────────────────────────────────────────────
def test_classify_by_keyword():
    items = C.classify(N.normalize([mk("台廠搶進 ASIC 供應鏈")]), INDS, STOCKS)
    assert items[0]["industries"] == ["asic"]


def test_classify_exclude_blocks_false_positive():
    """『聊天機器人』不是機器人產業的新聞——這是最典型的誤判。"""
    items = C.classify(N.normalize([mk("這家銀行推出聊天機器人客服")]), INDS, STOCKS)
    assert "robotics" not in items[0]["industries"]


def test_classify_by_stock_code():
    items = C.classify(N.normalize([mk("公告", 1, "official", code="3017",
                                       snapshot=True)]), INDS, STOCKS)
    assert items[0]["industries"] == ["cooling"]


def test_classify_allows_no_industry():
    items = C.classify(N.normalize([mk("今天天氣很好")]), INDS, STOCKS)
    assert items[0]["industries"] == []


# ── dedupe ───────────────────────────────────────────────────────
def test_dedupe_same_url():
    items = N.normalize([mk("A", url="http://same"), mk("B", url="http://same")])
    assert len(D.dedupe(items)) == 1


def test_dedupe_different_url_kept():
    """每筆官方訊息要有自己的網址，否則整批會被當成同一則殺掉。"""
    items = N.normalize([mk("甲公司公告", url="http://mops?co=1"),
                         mk("乙公司公告", url="http://mops?co=2")])
    assert len(D.dedupe(items)) == 2


def test_cluster_merges_similar_titles():
    a = mk("輝達發表新一代 ASIC 加速晶片 搶攻資料中心")
    b = mk("NVIDIA 推出新一代 ASIC 加速晶片 進軍資料中心")
    evs = D.cluster(C.classify(N.normalize([a, b]), INDS, STOCKS))
    assert max(e["count"] for e in evs) == 2


def test_cluster_keeps_unrelated_apart():
    a = mk("ASIC 供應鏈拉貨動能轉強")
    b = mk("液冷散熱模組明年報價看漲")
    evs = D.cluster(C.classify(N.normalize([a, b]), INDS, STOCKS))
    assert all(e["count"] == 1 for e in evs)


# ── score ────────────────────────────────────────────────────────
def _events(items):
    return D.cluster(C.classify(N.normalize(items), INDS, STOCKS))


def test_score_missing_signal_reweights_not_zeroes():
    """社群完全沒資料時，不能把那 35% 當 0 分算——要把權重拿掉重新分配。"""
    evs = _events([mk("ASIC 大單") for _ in range(3)])
    sc, has = S.compute(INDS, evs, {})
    assert has["social_volume"] is False
    assert sc["asic"]["coverage"] < 100
    assert sc["asic"]["heat_score"] > 0           # 沒被沒資料的項目拖到 0


def test_score_all_signals_gives_full_coverage():
    evs = _events([mk("ASIC 大單"), mk("PTT 討論 ASIC", stype="social"),
                   mk("公告", 1, "official", code="3661", snapshot=True)])
    sc, has = S.compute(INDS, evs, {"3661": 5.0})
    assert sc["asic"]["coverage"] == 100


def test_score_google_news_does_not_inflate_volume():
    """Google News 是每個產業各查一次，量不能拿來跨產業比。"""
    broad = _events([mk("液冷 %d" % i) for i in range(3)])
    narrow = _events([mk("ASIC %d" % i, broad=False) for i in range(30)])
    sc, _ = S.compute(INDS, broad + narrow, {})
    assert sc["cooling"]["news_count"] == 3
    assert sc["asic"]["news_count"] == 0          # 30 則 Google News 不算進「量」
    assert sc["asic"]["news_all"] == 30           # 但仍保留，供加速度與展示使用


def test_accel_new_topic_from_zero_baseline():
    assert S._accel(5, 0) == 100.0
    assert S._accel(0, 0) == 0.0


def test_accel_is_clipped_for_scoring():
    assert S._clip(2700.0) == S.ACCEL_CLIP


def test_norm_handles_all_equal():
    out = S._norm({"a": 3, "b": 3})
    assert out == {"a": 50.0, "b": 50.0}


def test_norm_handles_all_zero():
    assert S._norm({"a": 0, "b": 0}) == {"a": 0.0, "b": 0.0}


def test_trend_thresholds():
    assert S.trend(30) == "rising"
    assert S.trend(-30) == "falling"
    assert S.trend(0) == "flat"


def test_empty_input_does_not_crash():
    sc, has = S.compute(INDS, [], {})
    assert all(v["heat_score"] == 0 for v in sc.values())
    assert not any(has.values())
