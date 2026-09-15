# -*- coding: utf-8 -*-
"""去重與事件聚類。

三層：
  1. URL 去重      同一個連結只留一筆
  2. 標題完全相同  砍掉 Google News 的「 - 來源」尾巴後比對
  3. 事件聚類      TF-IDF + cosine similarity，把同一件事的多家報導併成一個事件

結果不是十篇重複新聞，而是一個事件掛著多個來源。
"""
import math
import re
from collections import Counter, defaultdict

SIM_THRESHOLD = 0.42        # 超過這個相似度就視為同一件事
STOP = set("的了是在和與及對於為並將把從到由更也都很就還我你他這那一個月日年"
           "報導指出表示說稱可能將會已經今天昨天上漲下跌新聞快訊獨家公告")


def tokens(text):
    """中英混雜的土法分詞：英文與數字照抓，中文取 bigram。"""
    text = text.lower()
    out = re.findall(r"[a-z]{2,}|\d{3,4}", text)
    zh = re.findall(r"[一-鿿]+", text)
    for run in zh:
        run = "".join(c for c in run if c not in STOP)
        out += [run[i:i + 2] for i in range(len(run) - 1)]
    return [t for t in out if t]


def tfidf(docs):
    tfs, df = [], Counter()
    for d in docs:
        c = Counter(tokens(d))
        tfs.append(c)
        df.update(c.keys())
    n = max(1, len(docs))
    vecs = []
    for c in tfs:
        total = sum(c.values()) or 1
        v = {t: (f / total) * math.log((1 + n) / (1 + df[t]) + 1) for t, f in c.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        vecs.append({t: x / norm for t, x in v.items()})
    return vecs


def cosine(a, b):
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(t, 0.0) for t, x in a.items())


def dedupe(items):
    """第 1、2 層：URL 與標題完全相同。"""
    seen_url, seen_title, out = set(), set(), []
    for it in items:
        u = it.get("url") or ""
        k = re.sub(r"[^\w一-鿿]", "", it.get("title_key", ""))[:48]
        if u and u in seen_url:
            continue
        if k and k in seen_title:
            continue
        if u:
            seen_url.add(u)
        if k:
            seen_title.add(k)
        out.append(it)
    return out


def cluster(items, threshold=SIM_THRESHOLD):
    """第 3 層：同事件聚類。

    先照產業分桶再兩兩比對——全體 O(n²) 在幾千則時會慢，
    而不同產業的新聞本來就不太可能是同一件事。
    """
    buckets = defaultdict(list)
    for it in items:
        buckets[(it["industries"] or ["_none"])[0]].append(it)

    events = []
    for _, group in buckets.items():
        vecs = tfidf([g["title_key"] + " " + g.get("summary", "")[:120] for g in group])
        used = [False] * len(group)
        for i, g in enumerate(group):
            if used[i]:
                continue
            members = [g]
            used[i] = True
            for j in range(i + 1, len(group)):
                if not used[j] and cosine(vecs[i], vecs[j]) >= threshold:
                    used[j] = True
                    members.append(group[j])
            members.sort(key=lambda m: m["_dt"] or _EPOCH, reverse=True)
            inds = sorted({x for m in members for x in m["industries"]})
            events.append({
                "id": members[0]["id"],
                "title": members[0]["title"],
                "url": members[0]["url"],
                "industries": inds,
                "sources": sorted({m["source"] for m in members}),
                "source_types": sorted({m["source_type"] for m in members}),
                "count": len(members),
                "broad_count": sum(1 for m in members if m.get("broad")),
                "published_at": members[0]["published_at"],
                "_dt": members[0]["_dt"],
                "summary": members[0].get("summary", ""),
                "members": [{"title": m["title"], "url": m["url"],
                             "source": m["source"], "published_at": m["published_at"]}
                            for m in members[:6]],
            })
    events.sort(key=lambda e: (e["count"], e["_dt"] or _EPOCH), reverse=True)
    return events


from datetime import datetime, timezone, timedelta       # noqa: E402
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone(timedelta(hours=8)))
