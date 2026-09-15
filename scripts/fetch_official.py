# -*- coding: utf-8 -*-
"""官方資訊 adapter：證交所 / 櫃買 / 期交所。

重大訊息與月營收是「每日快照檔」，不是即時流——
遇到連假或當天沒有新申報，裡面就是前幾天的資料，不要用時間窗把它砍光。
"""
import json

from common import clean, fetch, log, parse_dt, roc_to_dt, env_on, iso

MOPS_URL = "https://mopsov.twse.com.tw/mops/web/t05st01"


def mops_link(code, kind):
    """每一筆要有自己的網址。

    全部共用 MOPS 那一個網址的話，去重那一關會把 200 多筆重大訊息
    當成同一則殺到只剩一筆，官方訊號就整個不見了（我第一版就是這樣）。
    多帶一個 MOPS 會忽略的參數，連結照樣開得起來，但去重看得出是不同筆。
    """
    return "%s?co=%s&t=%s" % (MOPS_URL, code or "na", kind)


def _item(title, url, source, dt, summary="", stype="official"):
    return {"title": title, "url": url, "source": source,
            "published_at": iso(dt), "_dt": dt, "summary": summary[:300],
            "language": "zh", "source_type": stype, "_snapshot": True}


def _mops(raw, source):
    """證交所與櫃買的重大訊息欄位名不一樣，而且證交所的欄位名尾端有空白。"""
    out = []
    for r in json.loads(raw.decode("utf-8")):
        r = {(k or "").strip(): v for k, v in r.items()}
        subj = clean(r.get("主旨"))
        if not subj:
            continue
        code = clean(r.get("公司代號") or r.get("SecuritiesCompanyCode"))
        name = clean(r.get("公司名稱") or r.get("CompanyName"))
        dt = roc_to_dt(r.get("發言日期") or r.get("出表日期") or r.get("Date"),
                       r.get("發言時間"))
        it = _item("%s %s｜%s" % (code, name, subj[:70]),
                   mops_link(code, "mops"), source, dt, clean(r.get("說明")))
        it["_code"] = code
        out.append(it)
    return out


def fetch_mops():
    out = []
    for name, url in [
            ("證交所·重大訊息", "https://openapi.twse.com.tw/v1/opendata/t187ap04_L"),
            ("櫃買·重大訊息", "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap04_O")]:
        try:
            rows = _mops(fetch(url), name)
            out += rows
            log.info("  [OK  ] %-14s %d 則", name, len(rows))
        except Exception as e:                      # noqa: BLE001
            log.warning("  [FAIL] %-14s %s", name, repr(e)[:70])
    return out


def fetch_revenue(tracked=None):
    """上市公司月營收。年增率高的當成一個官方事件訊號。

    只取「我們有追蹤的股票」——全市場年增最大的都是沒人聽過的小型股，
    它們對不到任何產業，收進來只是讓官方訊號整區歸零。
    """
    tracked = set(tracked or [])
    name = "證交所·月營收"
    try:
        rows = json.loads(fetch("https://openapi.twse.com.tw/v1/opendata/t187ap05_L"
                                ).decode("utf-8"))
    except Exception as e:                          # noqa: BLE001
        log.warning("  [FAIL] %-14s %s", name, repr(e)[:70])
        return []
    out = []
    for r in rows:
        r = {(k or "").strip(): v for k, v in r.items()}
        code = clean(r.get("公司代號"))
        cname = clean(r.get("公司名稱"))
        try:
            yoy = float(str(r.get("營業收入-去年同月增減(%)", "")).replace(",", ""))
        except (TypeError, ValueError):
            continue
        thr = 20 if code in tracked else 60         # 有追蹤的放寬，其他只留極端值
        if abs(yoy) < thr:
            continue
        it = _item("%s %s｜月營收年增 %+.1f%%" % (code, cname, yoy),
                   mops_link(code, "rev"),
                   name, roc_to_dt(clean(r.get("出表日期"))),
                   "資料月份 %s" % clean(r.get("資料年月")))
        it["_code"] = code
        it["_yoy"] = yoy
        out.append(it)
    out.sort(key=lambda x: (x.get("_code") not in tracked, -abs(x.get("_yoy", 0))))
    hit = sum(1 for x in out[:120] if x.get("_code") in tracked)
    log.info("  [OK  ] %-14s %d 則（其中 %d 檔在追蹤清單內）", name, len(out[:120]), hit)
    return out[:120]


def fetch_taifex():
    from fetch_news import _rss
    out = []
    for name, url in [("期交所·公告", "https://www.taifex.com.tw/cht/11/RSS1"),
                      ("期交所·新聞稿", "https://www.taifex.com.tw/cht/11/RSS2")]:
        try:
            rows = _rss(fetch(url), name, "official")
            for r in rows:
                r["_snapshot"] = False
            out += rows
            log.info("  [OK  ] %-14s %d 則", name, len(rows))
        except Exception as e:                      # noqa: BLE001
            log.warning("  [FAIL] %-14s %s", name, repr(e)[:70])
    return out


def fetch_quotes():
    """全市場日成交行情，用來算『市場異動』那 5%。回傳 {股票代號: 漲跌%}。"""
    if not env_on("TWSE_QUOTES_ENABLED", True):
        log.info("  [skip] 證交所行情（TWSE_QUOTES_ENABLED=false）")
        return {}
    try:
        rows = json.loads(fetch("https://openapi.twse.com.tw/v1/exchangeReport/"
                                "STOCK_DAY_ALL").decode("utf-8"))
    except Exception as e:                          # noqa: BLE001
        log.warning("  [FAIL] %-14s %s", "證交所·行情", repr(e)[:70])
        return {}
    out = {}
    for r in rows:
        try:
            close = float(r.get("ClosingPrice", "") or 0)
            chg = float(r.get("Change", "") or 0)
            prev = close - chg
            if prev > 0:
                out[r.get("Code", "")] = round(chg / prev * 100, 2)
        except (TypeError, ValueError):
            continue
    log.info("  [OK  ] %-14s %d 檔", "證交所·行情", len(out))
    return out


def fetch_all(tracked=None):
    log.info("抓官方資訊 ...")
    return fetch_mops() + fetch_revenue(tracked) + fetch_taifex()
