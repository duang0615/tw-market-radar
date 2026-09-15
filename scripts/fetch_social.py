# -*- coding: utf-8 -*-
"""社群來源 adapter。

實話說在前面：社群是這個雷達最弱的一環。

  · PTT    公開 Atom feed，合法穩定，但每個板只給最新 20 篇     → 預設開啟
  · Reddit 公開 .json 端點已經擋掉（HTTP 403），要 OAuth app  → 預設關閉
  · YouTube 要頻道 ID 或 API key                              → 預設關閉

所以「社群提及量」這一項的資料完整度通常不高。
score.py 會用 available-data weighted scoring 處理，並在頁面上顯示 coverage，
而不是假裝有資料。這比硬爬到被擋、或編一個數字出來誠實。
"""
from common import clean, fetch, log, env_on, iso
from fetch_news import _rss

PTT_BOARDS = ["Stock", "Tech_Job"]


def fetch_ptt():
    if not env_on("PTT_ENABLED", True):
        log.info("  [skip] PTT（PTT_ENABLED=false）")
        return []
    out = []
    for b in PTT_BOARDS:
        name = "PTT·" + b
        try:
            rows = _rss(fetch("https://www.ptt.cc/atom/%s.xml" % b),
                        name, "social")
            out += rows
            log.info("  [OK  ] %-14s %d 則", name, len(rows))
        except Exception as e:                      # noqa: BLE001
            log.warning("  [FAIL] %-14s %s", name, repr(e)[:70])
    return out


def fetch_reddit():
    """Reddit 的公開 .json 已經回 403，要跑得動需要自己申請 OAuth app。

    介面留著，設 REDDIT_ENABLED=true 才會嘗試，失敗也只是少這一家。
    """
    if not env_on("REDDIT_ENABLED", False):
        log.info("  [skip] Reddit（REDDIT_ENABLED=false，公開端點已被擋）")
        return []
    import json as _json
    out = []
    for sub in ["hardware", "semiconductor", "nvidia"]:
        name = "Reddit·r/" + sub
        try:
            j = _json.loads(fetch("https://www.reddit.com/r/%s/new.json?limit=25" % sub
                                  ).decode("utf-8", "replace"))
            for c in j.get("data", {}).get("children", []):
                d = c.get("data", {})
                from datetime import datetime
                from common import TZ
                dt = datetime.fromtimestamp(d.get("created_utc", 0), TZ)
                out.append({"title": clean(d.get("title")),
                            "url": "https://www.reddit.com" + d.get("permalink", ""),
                            "source": name, "published_at": iso(dt), "_dt": dt,
                            "summary": "", "language": "en", "source_type": "social"})
            log.info("  [OK  ] %-14s", name)
        except Exception as e:                      # noqa: BLE001
            log.warning("  [FAIL] %-14s %s", name, repr(e)[:70])
    return out


def fetch_youtube():
    """YouTube 頻道 RSS。要自己填頻道 ID，沒填就跳過。"""
    if not env_on("YOUTUBE_ENABLED", False):
        log.info("  [skip] YouTube（YOUTUBE_ENABLED=false，需要自己填頻道 ID）")
        return []
    import os
    ids = [x.strip() for x in os.environ.get("YOUTUBE_CHANNEL_IDS", "").split(",") if x.strip()]
    out = []
    for cid in ids:
        try:
            out += _rss(fetch("https://www.youtube.com/feeds/videos.xml?channel_id=" + cid),
                        "YouTube", "social")
        except Exception as e:                      # noqa: BLE001
            log.warning("  [FAIL] YouTube:%s %s", cid[:12], repr(e)[:60])
    log.info("  [OK  ] %-14s %d 則", "YouTube", len(out))
    return out


def fetch_all():
    log.info("抓社群 ...")
    return fetch_ptt() + fetch_reddit() + fetch_youtube()
