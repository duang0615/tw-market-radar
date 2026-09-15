# -*- coding: utf-8 -*-
"""正規化：把各來源的原始資料整理成同一種格式，並砍掉視窗外的東西。"""
import hashlib
import re
import urllib.parse

from common import TZ, clean, now
from datetime import timedelta

# Google News 的標題尾巴會掛「 - 來源名」，去重前要砍掉
_TAIL = re.compile(r"\s*[-–—]\s*[^-–—]{2,16}$")
# 模板式自動產文，資訊量低
NOISE = [re.compile(r"鉅亨速報.*Factset"), re.compile(r"^\s*Re:\s*\[閒聊\]")]


def strip_tail(title):
    return _TAIL.sub("", title or "").strip()


def canon_url(u):
    """去掉追蹤參數，讓同一篇文章的不同連結能對上。"""
    u = (u or "").strip()
    if not u:
        return ""
    try:
        p = urllib.parse.urlsplit(u)
        keep = [(k, v) for k, v in urllib.parse.parse_qsl(p.query)
                if not k.lower().startswith(("utm_", "fbclid", "gclid"))]
        return urllib.parse.urlunsplit(
            (p.scheme, p.netloc.lower(), p.path.rstrip("/"),
             urllib.parse.urlencode(keep), ""))
    except ValueError:
        return u


def item_id(it):
    base = canon_url(it.get("url")) or strip_tail(it.get("title", ""))
    return hashlib.sha1(base.encode("utf-8", "ignore")).hexdigest()[:16]


def normalize(items, window_hours=72):
    """統一格式 + 砍掉視窗外的資料。

    快照類（重大訊息、月營收）不套時間窗——它們本來就是每日檔，
    連假時整批都是前幾天的，砍掉會讓官方訊號整區歸零。
    """
    cutoff = now() - timedelta(hours=window_hours)
    out = []
    for it in items:
        title = clean(it.get("title"))
        if not title or any(p.search(title) for p in NOISE):
            continue
        dt = it.get("_dt")
        if dt is not None and dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ)
        if not it.get("_snapshot") and dt is not None and dt < cutoff:
            continue
        out.append({
            "id": item_id(it),
            "title": title,
            "title_key": strip_tail(title),
            "url": canon_url(it.get("url")),
            "source": it.get("source", ""),
            "published_at": it.get("published_at"),
            "_dt": dt,
            "summary": clean(it.get("summary"))[:300],
            "language": it.get("language", "zh"),
            "source_type": it.get("source_type", "news"),
            "hint": it.get("_hint"),
            "code": it.get("_code"),
            "broad": bool(it.get("_broad", True)),
        })
    return out
