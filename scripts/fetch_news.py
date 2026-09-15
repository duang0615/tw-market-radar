# -*- coding: utf-8 -*-
"""新聞來源 adapter。

每個 adapter 都回傳同一種 dict，上游不需要知道它是 RSS 還是 JSON：
    {title, url, source, published_at, summary, language, source_type}

單一來源失敗只會少那一家，不會讓整條 pipeline 掛掉。
"""
import xml.etree.ElementTree as ET

from common import clean, fetch, gnews, log, parse_dt, env_on, iso

ATOM = "{http://www.w3.org/2005/Atom}"


def _item(title, url, source, dt, summary="", stype="news", lang="zh", broad=True):
    # broad=True 表示「這個來源不分產業、一視同仁地抓」，量才能拿來跨產業比較。
    # Google News 是針對每個產業各查一次，每次都回傳到上限，
    # 量反映的是「Google 回幾筆」而不是真實熱度，所以標成 broad=False。
    return {"title": title, "url": url, "source": source,
            "published_at": iso(dt), "_dt": dt, "summary": summary[:300],
            "language": lang, "source_type": stype, "_broad": broad}


def _rss(raw, source, stype="news", lang="zh", broad=True):
    """RSS 2.0（<item>）與 Atom（<entry>）都吃。"""
    root = ET.fromstring(raw.strip())
    out = []
    for it in root.iter("item"):
        t = clean(it.findtext("title"))
        if t:
            out.append(_item(t, clean(it.findtext("link")), source,
                             parse_dt(it.findtext("pubDate")),
                             clean(it.findtext("description")), stype, lang, broad))
    for en in root.iter(ATOM + "entry"):
        t = clean(en.findtext(ATOM + "title"))
        if not t:
            continue
        link = ""
        for ln in en.iter(ATOM + "link"):
            link = ln.get("href") or link
        dt = parse_dt(en.findtext(ATOM + "published") or en.findtext(ATOM + "updated"))
        out.append(_item(t, link, source, dt,
                         clean(en.findtext(ATOM + "summary")), stype, lang, broad))
    return out


# ── 固定的媒體 RSS ────────────────────────────────────────────────
MEDIA = [
    ("鉅亨網·台股", "https://news.cnyes.com/rss/v1/news/category/tw_stock"),
    ("鉅亨網·頭條", "https://news.cnyes.com/rss/v1/news/category/headline"),
    ("鉅亨網·總經", "https://news.cnyes.com/rss/v1/news/category/tw_macro"),
    ("鉅亨網·國際股", "https://news.cnyes.com/rss/v1/news/category/wd_stock"),
    ("鉅亨網·研究", "https://news.cnyes.com/rss/v1/news/category/cnyes_research"),
    ("TechNews", "https://technews.tw/feed/"),
    ("iThome", "https://www.ithome.com.tw/rss"),
    ("經濟日報", "https://money.udn.com/rssfeed/news/1001/5591?ch=money"),
]

# 沒有官方 RSS 的站，用 Google News 的「站內」搜尋補。
# 注意：site: 查詢是整站、不分產業，所以量可以拿來跨產業比較（broad=True）；
# 下面 fetch_google_news 的「關鍵字」查詢才是偏的。
SITE_FEEDS = [
    ("MoneyDJ", "site:moneydj.com"),
    ("DigiTimes", "site:digitimes.com.tw"),
    ("工商時報", "site:ctee.com.tw"),
    ("自由財經", "site:ec.ltn.com.tw"),
]


def fetch_site_feeds(window="3d"):
    out = []
    for name, q in SITE_FEEDS:
        try:
            rows = _rss(fetch(gnews(q, window), timeout=20, retry=1), name)
            out += rows
            log.info("  [OK  ] %-14s %d 則（Google News 站內搜尋）", name, len(rows))
        except Exception as e:                      # noqa: BLE001
            log.warning("  [FAIL] %-14s %s", name, repr(e)[:70])
    return out


def fetch_media():
    out = []
    for name, url in MEDIA:
        try:
            rows = _rss(fetch(url), name)
            out += rows
            log.info("  [OK  ] %-14s %d 則", name, len(rows))
        except Exception as e:                      # noqa: BLE001
            log.warning("  [FAIL] %-14s %s", name, repr(e)[:70])
    return out


def fetch_google_news(industries, window="3d"):
    """每個產業打一次關鍵字搜尋。這是產業熱度的主要訊號來源。

    只用每個產業前 3 個關鍵字，避免請求數爆炸（26 個產業已經 26 次請求）。
    """
    if not env_on("GOOGLE_NEWS_ENABLED", True):
        log.info("  [skip] Google News（GOOGLE_NEWS_ENABLED=false）")
        return []
    out, ok, fail = [], 0, 0
    for ind in industries:
        kws = ind.get("keywords", [])[:3]
        if not kws:
            continue
        q = " OR ".join('"%s"' % k for k in kws)
        try:
            rows = _rss(fetch(gnews(q, window), timeout=20, retry=1),
                        "Google News", "news", broad=False)
            for r in rows:
                r["_hint"] = ind["id"]          # 這則是從哪個產業的查詢來的
            out += rows
            ok += 1
        except Exception as e:                      # noqa: BLE001
            fail += 1
            log.warning("  [FAIL] GN:%-12s %s", ind["id"], repr(e)[:60])
    log.info("  [OK  ] %-14s %d 則（%d 個產業查詢成功，%d 失敗）",
             "Google News", len(out), ok, fail)
    return out


def fetch_gdelt(industries, timespan="72h", maxrecords=50):
    """GDELT DOC API。免費但常常 429，預設關閉；開了失敗也只是少這一家。"""
    if not env_on("GDELT_ENABLED", False):
        log.info("  [skip] GDELT（GDELT_ENABLED=false，它很常回 429）")
        return []
    import json as _json
    out = []
    for ind in industries[:8]:                      # 只打前幾個，避免被限流
        kw = (ind.get("keywords") or [ind["name"]])[0]
        url = ("https://api.gdeltproject.org/api/v2/doc/doc?query=%s"
               "&mode=artlist&format=json&timespan=%s&maxrecords=%d"
               % (kw.replace(" ", "%20"), timespan, maxrecords))
        try:
            arts = _json.loads(fetch(url, timeout=25, retry=1).decode("utf-8", "replace"))
            for a in arts.get("articles", []):
                r = _item(clean(a.get("title")), a.get("url", ""),
                          "GDELT·" + clean(a.get("domain")),
                          parse_dt(a.get("seendate", "")), "", "news", "en", broad=False)
                r["_hint"] = ind["id"]
                out.append(r)
        except Exception as e:                      # noqa: BLE001
            log.warning("  [FAIL] GDELT:%-10s %s", ind["id"], repr(e)[:60])
    log.info("  [OK  ] %-14s %d 則", "GDELT", len(out))
    return out


def fetch_all(industries):
    log.info("抓新聞 ...")
    return (fetch_media() + fetch_site_feeds()
            + fetch_google_news(industries) + fetch_gdelt(industries))
