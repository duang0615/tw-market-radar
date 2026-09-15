> ## ⚠️ 先看這段：這份是「原始規格」，不是「實作說明」
>
> 這份檔案是當初丟給 AI 的需求規格。實際做出來之後，有幾個地方**刻意沒有照它做**，
> 原因都是實際跑過才發現的。**要照抄的人請以 [README.md](README.md) 為準。**
>
> | 規格原本說 | 實際做法 | 為什麼 |
> |---|---|---|
> | 前端放在 `web/` | 放在 repo 根目錄 | GitHub Pages 的 legacy 來源只吃 `/` 或 `/docs`，放 `web/` 會開不起來 |
> | 抓 Reddit / X / Threads | 只做 PTT，Reddit 介面留著但預設關 | Reddit 公開 `.json` 端點回 403，要自己申請 OAuth app |
> | 社群佔 35% 權重 | 常常沒資料，權重會被拿掉重新分配 | PTT 兩個板不到 40 篇，能對到產業的更少；coverage 會誠實顯示 65% |
> | 新聞量直接計數 | 只算「廣泛型」來源，且取對數 | Google News 每個產業各查一次都回到上限，拿它比量等於在比「Google 回幾筆」 |
> | 加速度直接用 | 計分時夾在 ±200% | 基期接近 0 會噴出 +2700%，一個離群值把其他產業全壓扁 |
> | GDELT 當主要來源 | 做了 adapter 但預設關閉 | 免費額度很容易 429，實測連續三次都被擋 |
> | `person.json` | `data/people.json`，且網址全部留空 | 規格自己也說「不要假設沒有驗證過的社群帳號 URL」 |
>
> 另外三個規格沒提、但實際會出事的坑，都寫在 README 的「已知限制」：
> 重大訊息共用同一個網址會被去重殺光、民國年要併發言時間、證交所欄位名尾端有空白。

---

# 麥可鄧 AI Market Radar — Claude 執行規格

## 目標
請直接在目前的 GitHub repository 中，建立一個可部署到 **GitHub Pages** 的「AI Market Radar／市場熱度雷達」網站。

網站目的：
1. 找出過去 72 小時網路討論度快速上升的產業。
2. 將新聞、社群、官方公告整理成條列式資訊。
3. 用 AI 對事件做摘要、聚類、產業分類與熱度評分。
4. 將產業連到相關台股公司，形成「事件 → 產業 → 股票」視圖。
5. 所有資料與程式碼都放在 GitHub repository，可由 GitHub Actions 自動更新。

不要只做靜態 mockup。請完成一個「可以實際跑起來」的 MVP。

---

## 一、技術方向

優先採用：
- Frontend：HTML + CSS + Vanilla JavaScript（避免第一版過度複雜）
- Data pipeline：Python
- Storage：JSON / SQLite 擇一，MVP 優先 JSON；若需要歷史趨勢再加入 SQLite
- AI：透過環境變數指定 OpenAI-compatible API
- CI/CD：GitHub Actions
- Hosting：GitHub Pages

要求：
- 不需要後端 server 才能瀏覽網站。
- GitHub Pages 可以直接打開。
- 敏感 API key 不可寫進 frontend。
- API key 一律使用 GitHub Secrets / environment variables。

---

## 二、Repository 結構

建立並維持類似以下結構：

```text
.
├── README.md
├── requirements.txt
├── .env.example
├── data/
│   ├── news.json
│   ├── social.json
│   ├── official.json
│   ├── industries.json
│   ├── stocks.json
│   └── radar.json
├── scripts/
│   ├── fetch_news.py
│   ├── fetch_social.py
│   ├── fetch_official.py
│   ├── normalize.py
│   ├── classify.py
│   ├── score.py
│   ├── summarize.py
│   └── build_radar.py
├── web/
│   ├── index.html
│   ├── industry.html
│   ├── stock.html
│   ├── person.html
│   ├── app.js
│   └── style.css
└── .github/
    └── workflows/
        └── update-radar.yml
```

可以調整檔案結構，但功能不可減少。

---

## 三、第一版資料來源

### A. 新聞

優先使用容易自動化且合法取得的來源：
- Google News RSS
- GDELT DOC API
- Reuters 等公開 RSS／可合法取得的來源
- TechNews
- iThome
- DIGITIMES（若可取得）
- 鉅亨／經濟日報／工商時報等公開 feed（能合法取得才使用）

不要用暴力爬蟲繞過 robots、登入、付費牆或 CAPTCHA。

每筆資料至少保存：
```json
{
  "title": "",
  "url": "",
  "source": "",
  "published_at": "",
  "summary": "",
  "language": "",
  "source_type": "news"
}
```

### B. 官方資訊

第一版至少預留 TWSE / MOPS connector。

優先抓：
- 上市公司重大訊息
- 月營收
- 法說會／公告
- 財報相關公告

若某 API 在開發環境不能穩定抓取，請建立 adapter interface，讓未來替換來源時不需要改整個系統。

### C. 社群

第一版不要為了抓 X / Threads 而做不穩定或違反平台規範的爬蟲。

先支援可以合法取得的：
- Reddit（若 API 可用）
- PTT 公開頁面／RSS（若合法、穩定）
- YouTube Search / RSS（若可用）

同時建立 `social_source` 介面，之後可加入 X / Threads 官方 API。

### D. 搜尋趨勢

如果可取得，預留 Google Trends / GDELT volume 欄位。

---

## 四、產業分類

第一版先建立以下產業 taxonomy：

```text
AI伺服器
GPU
ASIC
HBM
DRAM
NAND
先進封裝
CoWoS
PCB
CCL
散熱
電源
網通
光通訊
高速傳輸
機器人
半導體設備
晶圓代工
IC設計
封裝測試
重電
儲能
電動車
金融
航運
```

設計成 `industries.json`，未來可以增加產業。

每個產業至少包含：
```json
{
  "id": "asic",
  "name": "ASIC",
  "keywords": ["ASIC", "custom silicon", "自研晶片", "客製化晶片"],
  "stocks": ["3035", "3443", "3661"]
}
```

不要硬編死公司關係在程式碼中。

---

## 五、台股公司資料

建立 `stocks.json`，第一版加入與 AI / 科技產業相關的代表性公司，例如：

```text
2330 台積電
2317 鴻海
2382 廣達
6669 緯穎
3231 緯創
3017 奇鋐
2376 技嘉
2356 英業達
3035 智原
3443 創意
3661 世芯-KY
3711 日月光投控
6488 環球晶
6239 力成
```

這只是初始 mapping，不代表投資建議。

每支股票至少：
```json
{
  "code": "3035",
  "name": "智原",
  "industries": ["asic", "ic-design"]
}
```

---

## 六、核心：72 小時市場熱度分數

做出真正的 scoring engine。

初始公式：

```text
Heat Score =
新聞量         30%
新聞量增速     20%
社群提及量     20%
社群增速       15%
官方重大事件   10%
市場異動        5%
```

所有指標先 normalize 到 0～100。

另外計算：

```text
Heat Acceleration
```

定義：比較最近 24 小時與前一個 24 小時／前 72 小時基準的變化。

例如：

```text
ASIC
Heat Score: 84
Acceleration: +32%
Trend: rising
```

### 注意

若某來源沒有資料，不要直接讓整個分數失效。
使用 available-data weighted scoring，並在結果顯示資料完整度：

```text
Data Coverage: 78%
```

---

## 七、新聞去重與事件聚類

不同媒體可能報同一件事。

需要：
1. URL 去重
2. title similarity 去重
3. 同事件 clustering
4. 事件保留多個來源

最後不是顯示 10 篇重複新聞，而是顯示：

```text
【Google／TPU 新產品消息】
來源：Reuters / TechNews / ...
涉及產業：ASIC
討論度：↑
```

第一版可以使用 TF-IDF / cosine similarity；若已有 LLM，可再加入 AI clustering。

---

## 八、AI 分析

請透過 OpenAI-compatible API 建立可替換模型的介面。

環境變數：

```text
LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=
```

不要把模型寫死。

AI 對每個熱門產業輸出：

```json
{
  "industry": "ASIC",
  "summary": "...",
  "why_hot": [
    "...",
    "...",
    "..."
  ],
  "key_events": [
    "..."
  ],
  "beneficiary_stocks": [
    "3035",
    "3443",
    "3661"
  ],
  "risk_stocks": [],
  "watch_people": [],
  "confidence": 0.82
}
```

AI 必須遵守：
- 不得捏造新聞
- 每一個重要判斷盡量對應 source URL
- 沒有資料就寫「資料不足」
- 不把新聞熱度直接等同股價上漲
- 股票只是「相關公司／可能受關注」，不要生成保證獲利語句

---

## 九、值得追蹤的人／帳號

建立 `person.json` 或 `people.json`。

第一版分類：

### AI / 半導體
- Jensen Huang
- Dylan Patel / SemiAnalysis
- Patrick Moorhead
- Jim Handy

### 公司／產業高層
預留可加入：
- 台積電管理層
- NVIDIA 管理層
- AMD 管理層
- Intel 管理層
- Microsoft / Google / Amazon AI 相關主管

### 研究機構
- SemiAnalysis
- TrendForce
- TechInsights
- Counterpoint
- Omdia

每個人／來源：
```json
{
  "name": "Dylan Patel",
  "type": "analyst",
  "topics": ["AI", "ASIC", "HBM", "data-center"],
  "url": ""
}
```

不要假設沒有驗證過的社群帳號 URL；若無法確認，保留空值並在 README 說明。

---

## 十、網站 UI

首頁要做到「一眼看到現在市場在炒什麼」。

### Header
```text
麥可鄧 AI Market Radar
過去 72 小時市場熱度
最後更新時間
```

### 區塊 1：熱門產業 Top 10

表格或卡片：

```text
排名 | 產業 | Heat Score | 加速度 | 新聞量 | 社群 | 狀態
1    | ASIC | 84         | +32%   | 127    | 1842 | 🔥
```

### 區塊 2：為什麼突然變熱

每個熱門產業顯示：
- 3～5 個原因
- 代表事件
- 相關公司

### 區塊 3：最值得看的新聞

每篇：
```text
時間
標題
來源
涉及產業
AI 摘要
```

### 區塊 4：今天值得追蹤的人

顯示：
- 人物 / 機構
- 最近討論主題
- 來源連結

### 區塊 5：相關台股

依產業顯示：
```text
3035 智原
3443 創意
3661 世芯-KY
```

只做資訊整理，不直接輸出買進／賣出指令。

---

## 十一、篩選功能

至少加入：

```text
[全部]
[AI]
[半導體]
[記憶體]
[PCB]
[伺服器]
[重電]
...
```

以及：
- 最近 6 小時
- 最近 24 小時
- 最近 72 小時

搜尋框可以查：
- 產業
- 公司
- 關鍵字

---

## 十二、GitHub Actions

建立：

`.github/workflows/update-radar.yml`

至少做到：

```text
schedule：每日自動執行
workflow_dispatch：手動執行
```

建議 MVP 每 3～6 小時更新一次；若 GitHub Actions quota 或 API 限制不適合，可以先每天更新。

流程：

```text
fetch
↓
normalize
↓
classify
↓
deduplicate
↓
score
↓
AI summarize
↓
build radar.json
↓
commit generated data
↓
deploy GitHub Pages
```

避免每次更新都產生大量無意義 Git commit；可以讓 workflow 只有資料真的變化時才 commit。

---

## 十三、環境設定

建立 `.env.example`：

```env
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=
LLM_MODEL=

GDELT_ENABLED=true
GOOGLE_NEWS_ENABLED=true
REDDIT_ENABLED=false
YOUTUBE_ENABLED=false
TWSE_ENABLED=false
MOPS_ENABLED=false
```

程式必須能在沒有某些 API key 時正常啟動，只是跳過該來源。

---

## 十四、資料格式

`data/radar.json` 建議：

```json
{
  "generated_at": "",
  "window_hours": 72,
  "market_summary": "",
  "industries": [
    {
      "rank": 1,
      "id": "asic",
      "name": "ASIC",
      "heat_score": 84,
      "acceleration": 32,
      "news_count": 127,
      "social_mentions": 1842,
      "official_events": 4,
      "coverage": 78,
      "trend": "rising",
      "summary": "",
      "why_hot": [],
      "key_events": [],
      "stocks": [],
      "people": []
    }
  ],
  "top_news": [],
  "people": []
}
```

---

## 十五、錯誤處理

所有 data source adapter 都要：
- timeout
- retry
- logging
- 不因單一來源失敗而整個 pipeline 掛掉

使用：
```python
try:
    ...
except Exception as e:
    logger.exception(...)
```

不要靜默吞掉錯誤。

---

## 十六、快取與 API 成本

非常重要：不要每次 workflow 都把所有歷史新聞重新送給 LLM。

要求：
- 原始新聞先保存
- hash / id 去重
- 只有新事件或需要更新的事件才送 LLM
- 儘量批次摘要
- 保留 `ai_processed_at`

---

## 十七、隱私與安全

絕對不要：
- commit API key
- commit `.env`
- 在 frontend 暴露 API key
- 把私有學生資料放進 GitHub repo

`.gitignore` 必須包含：

```text
.env
.venv/
__pycache__/
*.pyc
```

---

## 十八、README

README 必須清楚說明：
1. 專案用途
2. 架構
3. 資料來源
4. 安裝方式
5. 本機執行方式
6. API key 設定
7. GitHub Actions 設定
8. GitHub Pages 部署方式
9. 如何增加新的新聞來源
10. 如何增加產業
11. 如何增加股票
12. AI scoring 原理
13. 已知限制

---

## 十九、開發方式

請直接開始實作，不要只提供教學文字。

執行順序：

### Phase 1
先檢查 repository 現況。
如果已經存在相關程式，優先沿用，不要重建整個專案。

### Phase 2
完成最小可用 pipeline：
```text
Google News RSS / GDELT
→ normalize
→ industry classify
→ deduplicate
→ heat score
→ radar.json
```

### Phase 3
完成前端 GitHub Pages：
```text
Top 10 industries
Top news
Why hot
Stocks
People
```

### Phase 4
加入 LLM summarization。

### Phase 5
加入 GitHub Actions 自動更新。

### Phase 6
本機執行一次完整流程並驗證網站可以載入。

---

## 二十、測試要求

至少建立：

```text
pytest
```

測試：
- scoring
- normalization
- dedup
- industry classification
- missing data handling

並實際執行：

```bash
python scripts/build_radar.py
```

確認產生：

```text
data/radar.json
```

然後啟動本機 server，例如：

```bash
python -m http.server 8000 --directory web
```

確認首頁正常讀取 `radar.json`。

---

## 二十一、最重要的產品原則

這不是「新聞閱讀器」，而是：

> **市場討論度偵測器。**

所以首頁排序不能按照新聞發布時間，而要按照：

```text
市場熱度
+
熱度加速度
+
事件重要性
```

例如：

```text
ASIC       84 ↑32%
HBM        82 ↑24%
AI Server  79 ↑ 5%
PCB        71 ↓ 2%
```

使用者第一眼就應該知道：

> **這 72 小時，市場正在從 AI Server 把注意力轉向 ASIC。**

這才是整個網站存在的價值。

---

## 二十二、第一版完成標準

當以下條件全部成立，才算完成：

- [ ] GitHub Pages 可以開啟
- [ ] 首頁能顯示 Top 10 熱門產業
- [ ] 每個產業有 Heat Score
- [ ] 有 Heat Acceleration
- [ ] 有過去 72 小時新聞
- [ ] 新聞可以依產業分類
- [ ] 重複新聞不會大量出現
- [ ] 有 AI 摘要（沒有 API key 時顯示 fallback）
- [ ] 有相關台股
- [ ] 有值得追蹤的人／機構
- [ ] GitHub Actions 可以自動更新
- [ ] API key 沒有洩漏到 frontend 或 GitHub
- [ ] README 完整
- [ ] pytest 通過

完成後請在終端機輸出：

```text
IMPLEMENTATION COMPLETE

Files changed:
...

How to run locally:
...

How to configure GitHub Secrets:
...

How to enable GitHub Pages:
...

Known limitations:
...
```

不要只告訴我「應該怎麼做」，請直接修改 repository、建立檔案、執行測試並完成 MVP。
