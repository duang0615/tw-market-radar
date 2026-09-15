# -*- coding: utf-8 -*-
"""市場雷達主流程。

    抓 → 正規化 → 分類 → 去重聚類 → 計分 → AI 摘要 → 產出 radar.json

用法：
    python scripts/build_radar.py              # 正常跑
    python scripts/build_radar.py --dry-run    # 只抓不寫檔，檢查來源通不通
    python scripts/build_radar.py --scheduled  # 排程用：照 config.json 決定要不要跑
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import classify as C                                    # noqa: E402
import dedupe as D                                      # noqa: E402
import fetch_news                                       # noqa: E402
import fetch_official                                   # noqa: E402
import fetch_social                                     # noqa: E402
import normalize as N                                   # noqa: E402
import score as S                                       # noqa: E402
import summarize as SUM                                 # noqa: E402
from common import DATA, ROOT, load_json, log, now, save_json   # noqa: E402

WINDOW_HOURS = 72
TOP_N = 10


def load_config():
    cfg = {"auto_update": True, "update_time": "08:00",
           "timezone": "Asia/Taipei", "repo": ""}
    try:
        user = json.loads(io.open(os.path.join(ROOT, "config.json"),
                                  encoding="utf-8").read())
        for k in cfg:
            if k in user:
                cfg[k] = user[k]
    except FileNotFoundError:
        pass
    except Exception as e:                              # noqa: BLE001
        log.warning("config.json 讀不動（%s），用預設值", repr(e)[:60])
    return cfg


def should_run(cfg):
    if not cfg.get("auto_update", True):
        return False, "config.json 的 auto_update 是 false，自動更新已關閉"
    try:
        hh = int(str(cfg.get("update_time", "08:00")).split(":")[0])
    except ValueError:
        return True, "update_time 格式看不懂，這次照跑"
    h = now().hour
    if h != hh:
        return False, "現在 %02d 點，設定是每天 %s，跳過" % (h, cfg["update_time"])
    return True, "現在 %02d 點，對上設定的 %s" % (h, cfg["update_time"])


def main():
    dry = "--dry-run" in sys.argv
    cfg = load_config()
    if "--scheduled" in sys.argv:
        go, why = should_run(cfg)
        log.info("排程模式：%s", why)
        if not go:
            log.info("這次不跑。（手動執行不受開關影響）")
            return 0

    industries = load_json("industries.json")
    stocks = load_json("stocks.json")
    people = load_json("people.json")
    log.info("產業 %d 個 ／ 股票 %d 檔 ／ 追蹤對象 %d 個",
             len(industries), len(stocks), len(people))

    # 1. 抓
    news = fetch_news.fetch_all(industries)
    official = fetch_official.fetch_all([s["code"] for s in stocks])
    social = fetch_social.fetch_all()
    quotes = fetch_official.fetch_quotes()
    log.info("原始筆數：新聞 %d ／ 官方 %d ／ 社群 %d ／ 行情 %d 檔",
             len(news), len(official), len(social), len(quotes))

    # 2. 正規化
    items = N.normalize(news + official + social, WINDOW_HOURS)
    log.info("正規化後（%d 小時內）：%d 則", WINDOW_HOURS, len(items))

    # 3. 分類
    items = C.classify(items, industries, stocks)
    tagged = sum(1 for i in items if i["industries"])
    log.info("分到產業的：%d 則（%.0f%%）", tagged, tagged / max(1, len(items)) * 100)

    # 4. 去重 + 聚類
    items = D.dedupe(items)
    events = D.cluster(items)
    merged = sum(1 for e in events if e["count"] > 1)
    log.info("去重後 %d 則 → 聚成 %d 個事件（其中 %d 個由多則併成）",
             len(items), len(events), merged)

    # 5. 計分
    scores, has = S.compute(industries, events, quotes, WINDOW_HOURS)
    for iid in scores:
        scores[iid]["_trend"] = S.trend(scores[iid]["acceleration"])
    missing = [k for k, v in has.items() if not v]
    if missing:
        log.info("沒有資料的訊號（權重已重新分配）：%s", "、".join(missing))

    if dry:
        log.info("--dry-run，不寫檔。熱度前五：")
        for ind in sorted(industries, key=lambda i: -scores[i["id"]]["heat_score"])[:5]:
            s = scores[ind["id"]]
            log.info("   %-10s %5.1f  加速 %+6.1f%%  新聞 %3d  社群 %3d  官方 %2d  coverage %d%%",
                     ind["name"], s["heat_score"], s["acceleration"],
                     s["news_count"], s["social_mentions"], s["official_events"],
                     s["coverage"])
        return 0

    # 6. AI 摘要
    per_ev, per_st = {}, {}
    for ind in industries:
        iid = ind["id"]
        per_ev[iid] = [e for e in events if iid in e["industries"]][:20]
        per_st[iid] = C.industry_stocks(ind, stocks)
    ai = SUM.summarize(industries, per_ev, per_st, scores, limit=TOP_N)

    # 7. 組 radar.json
    t = now()
    rows = []
    for ind in sorted(industries, key=lambda i: -scores[i["id"]]["heat_score"]):
        iid = ind["id"]
        s, a = scores[iid], ai[iid]
        bene = set(a.get("beneficiary_stocks", []))
        rows.append({
            "rank": len(rows) + 1, "id": iid, "name": ind["name"],
            "group": ind.get("group", ""),
            "heat_score": s["heat_score"], "acceleration": s["acceleration"],
            "news_count": s["news_count"], "social_mentions": s["social_mentions"],
            "official_events": s["official_events"], "event_count": s["event_count"],
            "market_move": s["market_move"], "coverage": s["coverage"],
            "trend": s["_trend"], "parts": s["parts"],
            "summary": a.get("summary", ""), "why_hot": a.get("why_hot", []),
            "key_events": a.get("key_events", []),
            "ai_generated": a.get("ai_generated", False),
            "confidence": a.get("confidence", 0.0),
            "stocks": [dict(x, highlighted=x["code"] in bene) for x in per_st[iid]],
            "events": [{k: e[k] for k in
                        ("id", "title", "url", "sources", "count",
                         "published_at", "industries", "source_types")}
                       for e in per_ev[iid][:8]],
        })

    top_news = [{k: e[k] for k in ("id", "title", "url", "sources", "count",
                                   "published_at", "industries", "source_types",
                                   "members")}
                for e in sorted(events,
                                key=lambda e: (e["count"],
                                               e["_dt"] or D._EPOCH), reverse=True)[:40]]

    hot = rows[:3]
    if hot and hot[0]["news_count"]:
        summary = ("過去 %d 小時，討論度最高的是 %s（%.0f 分，%s%.0f%%）。"
                   % (WINDOW_HOURS, hot[0]["name"], hot[0]["heat_score"],
                      "加速 +" if hot[0]["acceleration"] >= 0 else "降溫 ",
                      abs(hot[0]["acceleration"])))
        rise = [r for r in rows[:10] if r["trend"] == "rising"]
        if rise:
            summary += "注意力正在流向：" + "、".join(r["name"] for r in rise[:3]) + "。"
    else:
        summary = "這個時段沒有抓到足夠的資料。"

    radar = {
        "generated_at": t.isoformat(), "window_hours": WINDOW_HOURS,
        "market_summary": summary,
        "ai_enabled": SUM.llm_available(),
        "signals_missing": missing,
        "config": {"auto_update": cfg.get("auto_update", True),
                   "update_time": cfg.get("update_time", "08:00"),
                   "repo": cfg.get("repo", "")},
        "counts": {"raw": len(news) + len(official) + len(social),
                   "in_window": len(items), "events": len(events),
                   "quotes": len(quotes)},
        "industries": rows, "top_news": top_news, "people": people,
    }

    save_json("radar.json", radar)
    # 只留有分到產業的、而且不帶摘要——全量存檔會變成每天 commit 一個 1.3MB 的檔，
    # repo 很快就肥掉。原始摘要本來就只在產出當下用得到。
    save_json("news.json", [{k: i[k] for k in
                             ("id", "title", "url", "source", "published_at",
                              "language", "source_type", "industries")}
                            for i in items
                            if i["source_type"] == "news" and i["industries"]][:800])
    save_json("official.json", [{k: i[k] for k in
                                 ("id", "title", "url", "source", "published_at",
                                  "industries")}
                                for i in items if i["source_type"] == "official"])
    save_json("social.json", [{k: i[k] for k in
                               ("id", "title", "url", "source", "published_at",
                                "industries")}
                              for i in items if i["source_type"] == "social"])
    log.info("已寫出 data/radar.json（%d 個產業、%d 個事件）", len(rows), len(events))
    log.info("熱度前五：")
    for r in rows[:5]:
        log.info("   %d. %-10s %5.1f  %+6.1f%%  新聞 %3d  事件 %2d  coverage %d%%",
                 r["rank"], r["name"], r["heat_score"], r["acceleration"],
                 r["news_count"], r["event_count"], r["coverage"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
