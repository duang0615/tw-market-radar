# -*- coding: utf-8 -*-
"""AI 摘要層。

設計原則：
  · 模型不寫死，全部走 OpenAI-compatible 介面，用環境變數指定
  · 沒有 API key 時走 fallback，用真實資料組出說明，並明確標示「非 AI 產生」
  · 只有新事件才送 LLM，用 ai_cache.json 記住處理過的東西，不要每次重燒 token
  · 嚴禁捏造：prompt 裡只給實際抓到的標題，要求沒資料就說資料不足
"""
import hashlib
import json
import os

from common import DATA, load_json, log, now, save_json

CACHE = "ai_cache.json"


def llm_config():
    return (os.environ.get("LLM_BASE_URL", "").strip(),
            os.environ.get("LLM_API_KEY", "").strip(),
            os.environ.get("LLM_MODEL", "").strip())


def llm_available():
    base, key, model = llm_config()
    return bool(base and key and model)


SYSTEM = (
    "你是台股產業研究助理。只能根據使用者提供的新聞標題作答，"
    "不得加入標題裡沒有的事實，不得捏造數字、日期或公司名稱。"
    "沒有足夠資料就直接寫「資料不足」。"
    "熱度只代表討論度，不等於股價會漲，不要寫出任何保證獲利或買賣建議的句子。"
    "只輸出 JSON，不要加任何說明文字。"
)


def _prompt(ind, events, stocks):
    lines = []
    for e in events[:12]:
        lines.append("- %s（來源：%s）" % (e["title"][:90], "、".join(e["sources"][:3])))
    return (
        "產業：%s\n"
        "過去 72 小時相關新聞標題：\n%s\n\n"
        "候選相關公司（僅供挑選，不要自己新增）：%s\n\n"
        "請輸出 JSON：\n"
        '{"summary":"兩句話說明這個產業最近在發生什麼",'
        '"why_hot":["原因1","原因2","原因3"],'
        '"key_events":["最代表性的事件標題"],'
        '"beneficiary_stocks":["股號"],'
        '"confidence":0.0}\n'
        "why_hot 最多三點，每點不超過 40 字。"
        "beneficiary_stocks 只能從候選公司裡挑，最多 5 檔，沒把握就給空陣列。"
        % (ind["name"], "\n".join(lines) or "（沒有抓到相關新聞）",
           "、".join("%s %s" % (s["code"], s["name"]) for s in stocks[:12]))
    )


def _call_llm(prompt, timeout=60):
    import urllib.request
    base, key, model = llm_config()
    body = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": prompt}],
        "temperature": 0.2,
    }).encode("utf-8")
    req = urllib.request.Request(
        base.rstrip("/") + "/chat/completions", data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + key})
    raw = urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8")
    txt = json.loads(raw)["choices"][0]["message"]["content"].strip()
    if txt.startswith("```"):
        txt = txt.strip("`")
        txt = txt[txt.find("{"):]
    return json.loads(txt[txt.find("{"):txt.rfind("}") + 1])


def fallback(ind, events, stocks, sc):
    """沒有 API key 時的替代方案：用實際數字組說明，不假裝是 AI 寫的。"""
    why = []
    if sc["event_count"]:
        why.append("過去 72 小時聚出 %d 個相關事件，其中綜合媒體報導 %d 則"
                   % (sc["event_count"], sc["news_count"]))
    if sc["acceleration"] >= 25:
        why.append("最近 24 小時的報導量比前兩天平均高出 %.0f%%" % sc["acceleration"])
    elif sc["acceleration"] <= -25:
        why.append("最近 24 小時報導量比前兩天平均少 %.0f%%，熱度在退"
                   % abs(sc["acceleration"]))
    if sc["official_events"]:
        why.append("有 %d 筆官方重大訊息／月營收變動落在這個產業"
                   % sc["official_events"])
    if sc["social_mentions"]:
        why.append("社群（PTT）出現 %d 則相關討論" % sc["social_mentions"])
    if sc["market_move"]:
        why.append("成分股當日平均波動 %.2f%%" % sc["market_move"])
    if not why:
        why = ["資料不足"]
    top = events[0]["title"][:80] if events else ""
    return {
        "summary": ("%s 熱度分數 %.0f，趨勢 %s。以下為依實際抓到的資料統計的結果，"
                    "未經 AI 改寫。" % (ind["name"], sc["heat_score"],
                                      {"rising": "上升", "falling": "下降",
                                       "flat": "持平"}[sc["_trend"]])),
        "why_hot": why[:3],
        "key_events": [top] if top else [],
        "beneficiary_stocks": [s["code"] for s in stocks[:5]],
        "risk_stocks": [],
        "confidence": 0.0,
        "ai_generated": False,
    }


def summarize(industries, per_ind_events, per_ind_stocks, scores, limit=10):
    """只摘要熱度前幾名的產業，其他用 fallback——省 token，也省時間。"""
    cache = load_json(CACHE, {})
    use_llm = llm_available()
    log.info("AI 摘要：%s", "走 LLM（%s）" % llm_config()[2] if use_llm
             else "沒有 LLM_API_KEY，改用資料統計 fallback")

    ranked = sorted(industries, key=lambda i: -scores[i["id"]]["heat_score"])
    out, hits, calls = {}, 0, 0
    for n, ind in enumerate(ranked):
        iid = ind["id"]
        evs = per_ind_events.get(iid, [])
        sts = per_ind_stocks.get(iid, [])
        sc = scores[iid]
        if not use_llm or n >= limit:
            out[iid] = fallback(ind, evs, sts, sc)
            continue
        sig = hashlib.sha1(("|".join(e["id"] for e in evs[:12])).encode()).hexdigest()[:16]
        cached = cache.get(iid)
        if cached and cached.get("sig") == sig:
            out[iid] = cached["result"]
            hits += 1
            continue
        try:
            r = _call_llm(_prompt(ind, evs, sts))
            valid = {s["code"] for s in sts}
            r["beneficiary_stocks"] = [c for c in r.get("beneficiary_stocks", [])
                                       if c in valid][:5]
            r.setdefault("risk_stocks", [])
            r["ai_generated"] = True
            out[iid] = r
            cache[iid] = {"sig": sig, "result": r, "ai_processed_at": now().isoformat()}
            calls += 1
        except Exception as e:                      # noqa: BLE001
            log.warning("  [FAIL] LLM %-12s %s", iid, repr(e)[:70])
            out[iid] = fallback(ind, evs, sts, sc)
    if use_llm:
        save_json(CACHE, cache)
        log.info("  LLM 呼叫 %d 次，快取命中 %d 次", calls, hits)
    return out
