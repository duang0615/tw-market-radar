# -*- coding: utf-8 -*-
"""共用工具：抓網頁、清字串、時間處理、路徑。

整條 pipeline 只用 Python 標準函式庫，不需要 pip install 任何東西。
"""
import io
import json
import logging
import os
import re
import time
import html as _html
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timedelta, timezone

TZ = timezone(timedelta(hours=8))                      # 台灣時間
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("radar")


def env_on(name, default=False):
    """讀環境變數開關。沒設就用預設值，不要因為少一把 key 就整支掛掉。"""
    v = os.environ.get(name)
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def now():
    return datetime.now(TZ)


def fetch(url, timeout=25, retry=2, backoff=2.0):
    """抓網頁：逾時、重試、最後仍失敗才丟例外（由呼叫端接住）。"""
    last = None
    for i in range(retry + 1):
        try:
            req = urllib.request.Request(url, headers=UA)
            return urllib.request.urlopen(req, timeout=timeout).read()
        except Exception as e:                      # noqa: BLE001 - 來源千奇百怪
            last = e
            if i < retry:
                time.sleep(backoff * (i + 1))
    raise last


def clean(s):
    """把 HTML 標籤、跳脫字元、多餘空白壓成一行乾淨文字。"""
    if not s:
        return ""
    s = re.sub(r"(?s)<[^>]+>", " ", str(s))
    s = _html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def parse_dt(s):
    """RSS / Atom 的時間字串 → 台灣時區 datetime。看不懂就回 None。"""
    s = clean(s)
    if not s:
        return None
    fmts = ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z",
            "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S")
    for f in fmts:
        try:
            d = datetime.strptime(s, f)
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
            return d.astimezone(TZ)
        except ValueError:
            continue
    # Atom 常見的 2026-09-15T01:02:03+08:00，Python 3.7+ 可直接吃
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(TZ)
    except ValueError:
        return None


def roc_to_dt(s, hhmmss=None):
    """民國日期 1150914 → datetime(2026, 9, 14)；有發言時間就一併補上。"""
    s = (s or "").strip()
    if len(s) != 7 or not s.isdigit():
        return None
    h = m = sec = 0
    t = (hhmmss or "").strip()
    if t.isdigit() and 5 <= len(t) <= 6:
        t = t.zfill(6)
        h, m, sec = int(t[:2]), int(t[2:4]), int(t[4:6])
    try:
        return datetime(int(s[:3]) + 1911, int(s[3:5]), int(s[5:7]),
                        min(h, 23), min(m, 59), min(sec, 59), tzinfo=TZ)
    except ValueError:
        return None


def gnews(query, window="3d"):
    """Google News 站內／關鍵字搜尋 RSS。沒有官方 RSS 的站全靠它。"""
    q = urllib.parse.quote("%s when:%s" % (query, window))
    return ("https://news.google.com/rss/search?q=" + q +
            "&hl=zh-TW&gl=TW&ceid=TW:zh-Hant")


def load_json(name, default=None):
    path = os.path.join(DATA, name)
    try:
        return json.loads(io.open(path, encoding="utf-8").read())
    except FileNotFoundError:
        return default if default is not None else []
    except Exception as e:                          # noqa: BLE001
        log.warning("  ! %s 讀不動（%s），用預設值", name, repr(e)[:60])
        return default if default is not None else []


def save_json(name, obj):
    path = os.path.join(DATA, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    io.open(path, "w", encoding="utf-8").write(
        json.dumps(obj, ensure_ascii=False, indent=2))
    return path


def iso(dt):
    return dt.isoformat() if dt else None
