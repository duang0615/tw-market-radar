# -*- coding: utf-8 -*-
"""產業分類：關鍵字比對 + 股票代號比對。

公司與產業的關係全部寫在 data/industries.json 與 data/stocks.json，
程式碼裡不硬編任何一家公司——要加產業、加股票都只改 JSON。
"""
import re


def build_matchers(industries, stocks):
    """先把每個產業的關鍵字編成一條 regex，比一則一則字串比對快得多。"""
    matchers = []
    excluders = {}
    for ind in industries:
        ex = [k for k in ind.get("exclude", []) if k]
        if ex:
            excluders[ind["id"]] = re.compile("|".join(re.escape(k) for k in ex), re.I)
        kws = [k for k in ind.get("keywords", []) if k]
        if not kws:
            continue
        # 英文關鍵字要求詞邊界，中文不需要（中文沒有空白分詞）
        parts = []
        for k in sorted(kws, key=len, reverse=True):
            e = re.escape(k)
            parts.append(r"\b%s\b" % e if re.match(r"^[\x00-\x7f]+$", k) else e)
        matchers.append((ind["id"], re.compile("|".join(parts), re.I)))
    code2ind = {}
    for s in stocks:
        code2ind[s["code"]] = s.get("industries", [])
    return matchers, code2ind, excluders


def classify(items, industries, stocks):
    """替每一則標上 industries（可能多個，也可能空）。"""
    matchers, code2ind, excluders = build_matchers(industries, stocks)
    valid = {i["id"] for i in industries}
    for it in items:
        hits = set()
        text = it["title"] + " " + it.get("summary", "")
        for iid, rx in matchers:
            if not rx.search(text):
                continue
            # 排除字：例如「機器人」會吃到「聊天機器人」，那不是這個產業的新聞
            ex = excluders.get(iid)
            if ex and ex.search(text):
                continue
            hits.add(iid)
        # 重大訊息／月營收帶著股票代號，直接查表對應到產業
        if it.get("code") and it["code"] in code2ind:
            hits.update(code2ind[it["code"]])
        # Google News 是針對某個產業的關鍵字查出來的，那個產業算命中
        if it.get("hint") in valid:
            hits.add(it["hint"])
        it["industries"] = sorted(hits)
    return items


def industry_stocks(ind, stocks):
    """產業對應的股票：industries.json 寫的 + stocks.json 反查，兩邊聯集。"""
    codes = list(ind.get("stocks", []))
    for s in stocks:
        if ind["id"] in s.get("industries", []) and s["code"] not in codes:
            codes.append(s["code"])
    name = {s["code"]: s["name"] for s in stocks}
    return [{"code": c, "name": name.get(c, "")} for c in codes if c in name]
