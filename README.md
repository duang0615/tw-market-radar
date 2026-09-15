# AI Market Radar · 台股市場熱度雷達

> AI煉金術系列 · 堂 1「打造你的移動交易室」延伸作業
> 星系投資 AI墨達人 × 麥可鄧 · 教方法，非投資建議

**線上看成品 →** https://duang0615.github.io/tw-market-radar/

找出過去 **72 小時**討論度快速上升的產業，把「事件 → 產業 → 台股公司」串成一張圖。

這不是新聞閱讀器，是**市場討論度偵測器**。
所以首頁不是按新聞時間排，是按**熱度 + 熱度加速度**排——
第一眼要看出來的是：**這 72 小時，市場的注意力正在往哪裡移動。**

---

## 1. 專案用途

| 想知道 | 看哪裡 |
|---|---|
| 現在市場在炒什麼 | 熱門產業排行的 Heat Score |
| 是「一直很熱」還是「突然變熱」 | 加速度那一欄（近 24h vs 前 48h） |
| 為什麼突然變熱 | 產業卡的 why_hot 與代表事件 |
| 跟哪些台股有關 | 產業卡下方的公司標籤 |
| 這個分數可不可信 | 資料完整度（coverage）那一欄 |

---

## 2. 架構

```
資料來源 (adapter)
   ↓ fetch_news.py / fetch_official.py / fetch_social.py
normalize.py     統一格式、砍視窗外、濾雜訊
   ↓
classify.py      關鍵字 + 股票代號 → 產業（含排除字）
   ↓
dedupe.py        URL 去重 → 標題去重 → TF-IDF 事件聚類
   ↓
score.py         六項指標加權 → Heat Score + 加速度 + coverage
   ↓
summarize.py     LLM 摘要（沒 key 就用資料統計 fallback）
   ↓
build_radar.py   組出 data/radar.json
   ↓
index.html + app.js   純前端讀 radar.json，搜尋／篩選都在瀏覽器跑
```

**整條 pipeline 只用 Python 標準函式庫**，不用 `pip install` 任何東西
（唯一例外是跑測試要 `pytest`）。前端沒有任何框架、沒有 CDN、沒有後端。

---

## 3. 資料來源

**驗證日期 2026-09-15**，每一個都實際抓過。

### 新聞（廣泛型，可用來比較「量」）

| 來源 | 方式 | 狀態 |
|---|---|---|
| 鉅亨網（台股／頭條／總經／國際股／研究） | 官方 RSS | ✅ |
| TechNews | 官方 RSS | ✅ |
| iThome | 官方 RSS | ✅ |
| 經濟日報 | 官方 RSS | ✅ |
| MoneyDJ · DigiTimes · 工商時報 · 自由財經 | Google News `site:` 搜尋 | ✅ |

### 新聞（產業關鍵字，只拿來發現事件）

| 來源 | 方式 | 狀態 |
|---|---|---|
| Google News 關鍵字搜尋（26 個產業各一次） | RSS | ✅ |
| GDELT DOC API | JSON | ⚠️ 很常回 429，預設關閉 |

### 官方

| 來源 | 方式 | 狀態 |
|---|---|---|
| 證交所 上市重大訊息 | OpenAPI | ✅ |
| 櫃買 上櫃重大訊息 | OpenAPI | ✅ |
| 證交所 月營收 | OpenAPI | ✅ |
| 證交所 全市場日行情 | OpenAPI | ✅ 用來算「市場異動」 |
| 期交所 公告／新聞稿 | 官方 RSS | ✅ |

### 社群

| 來源 | 方式 | 狀態 |
|---|---|---|
| PTT Stock · Tech_Job | 公開 Atom | ✅ 但每板只給最新 20 篇 |
| Reddit | 公開 `.json` | ❌ 已被擋（403），要自己申請 OAuth app |
| YouTube | 頻道 RSS | ⚠️ 要自己填頻道 ID |

> **社群是這個雷達最弱的一環，而且我沒有掩飾它。**
> PTT 兩個板加起來不到 40 篇，能對到產業關鍵字的更少，
> 所以「社群提及量／增速」這 35% 常常是沒有資料的。
> 這時候不是把它算 0 分——那會把所有產業一起拉低、排名失去意義——
> 而是**把那兩項的權重拿掉、其餘重新正規化**，並在頁面上標出 coverage 只有 65%。
>
> 沒有硬爬、沒有繞登入、沒有編一個數字出來。寧可顯示 65%，也不要假裝有 100%。

---

## 4. 安裝與本機執行

```bash
git clone https://github.com/duang0615/tw-market-radar.git
cd tw-market-radar

python scripts/build_radar.py --dry-run     # 先只抓不寫檔，確認來源都通
python scripts/build_radar.py               # 確認沒問題再正式產出

python -m http.server 8000                  # 開網站
# 瀏覽器打開 http://localhost:8000
```

> 直接用 `file://` 開 index.html 會失敗——瀏覽器會擋 `fetch()` 讀本機 JSON。
> 一定要用 http server 或放到 GitHub Pages。

| 參數 | 作用 |
|---|---|
| `--dry-run` | 只抓不寫檔，印出各來源筆數與熱度前五 |
| `--scheduled` | 排程用：照 `config.json` 的開關與時間決定要不要動手 |
| （不加參數） | 完整跑一次並寫檔 |

---

## 5. 三個控制項

全部在 [`config.json`](config.json)，改完 commit 就生效，**不用動排程檔**：

```json
{
  "auto_update": true,
  "update_time": "08:00",
  "timezone": "Asia/Taipei",
  "repo": "duang0615/tw-market-radar"
}
```

| 想做什麼 | 怎麼做 |
|---|---|
| **開／關自動更新** | `auto_update` 改 `true` / `false` |
| **改更新時間** | `update_time` 改成你要的 `HH:MM`（台灣時間） |
| **立刻更新一次** | 網頁右上角的 **「立即更新」** |

排程每小時醒來，看 `config.json` 決定跑不跑。**手動執行永遠不受開關影響。**

> GitHub Actions 的排程只精確到小時，尖峰時段常延遲 5～20 分鐘，
> 所以 `update_time` 的分鐘只拿來顯示。

---

## 6. API key 設定

**沒有 key 網站也能跑**，只是 AI 摘要換成「資料統計 fallback」，
卡片右上角會標示「資料統計」而不是「AI 摘要」。

本機：複製 `.env.example` 成 `.env` 填入（`.env` 已在 `.gitignore`，不會被 commit）。

GitHub：Settings → Secrets and variables → Actions → New repository secret

```
LLM_BASE_URL   例如 https://api.openai.com/v1
LLM_API_KEY    你的 key
LLM_MODEL      模型名稱
```

模型**不寫死**，任何 OpenAI 相容的服務都可以換上去。

**key 絕對不會進到前端**——前端只讀 `data/radar.json`，那是後端跑完的結果。

---

## 7. GitHub Actions

`.github/workflows/update-radar.yml`：每小時觸發、先跑 pytest、再產雷達、
**只有資料真的變動才 commit**。

**已驗證**：GitHub 的機器在美國，但證交所、櫃買、期交所都沒有擋境外 IP。

## 8. GitHub Pages

Settings → Pages → Source 選 `main` / `/ (root)`。
前端檔案放在 repo 根目錄就是為了這個。

---

## 9. 怎麼加東西

| 想加 | 改哪裡 |
|---|---|
| **新聞來源** | `scripts/fetch_news.py` 的 `MEDIA` 或 `SITE_FEEDS` 加一行 |
| **產業** | `data/industries.json` 加一筆（`id` / `name` / `group` / `keywords` / `exclude` / `stocks`） |
| **股票** | `data/stocks.json` 加一筆，`industries` 填產業 id |
| **追蹤的人** | `data/people.json` |
| **調整權重** | `scripts/score.py` 的 `WEIGHTS` |
| **版面** | `style.css` / `app.js` |

公司與產業的對應**全部寫在 JSON**，程式碼裡沒有硬編任何一家公司。

---

## 10. Heat Score 怎麼算

```
新聞量      30%     ← 只算廣泛型來源
新聞量增速  20%     ← 近 24h vs 前 48h 的日均
社群提及量  20%
社群增速    15%
官方重大事件 10%     ← 重大訊息 / 月營收異動
市場異動     5%      ← 成分股當日平均絕對漲跌幅
```

三個關鍵設計：

**① 量只算「廣泛型」來源。**
Google News 是每個產業各查一次、每次都回到上限，
拿它的筆數跨產業比較，等於在比「Google 回幾筆」，不是在比熱度。
所以關鍵字查詢的結果只拿來**發現事件**和算**加速度**（同產業內的比值），
不計入跨產業的量。

**② 計數取對數再正規化。**
新聞則數是重尾分布。直接 min-max 會讓第一名拿 100、其他全擠在 0～30，
排名等於沒有鑑別度。取 `log1p` 之後層次才出得來。

**③ 加速度計分時夾在 ±200%。**
基期接近 0 時，加速度會噴出 +2700% 這種數字，
一個離群值就把其他所有產業壓扁。顯示用原始值，計分用夾過的值。

---

## 11. 已知限制

1. **社群訊號很薄** — PTT 兩個板不到 40 篇，coverage 常常只有 65%
2. **分類是關鍵字比對，不是語意理解** — 加了排除字（例如「聊天機器人」不算機器人產業），但仍會有誤判
3. **關鍵字寬窄會影響排名** — 關鍵字越廣抓到越多。第一版「金融」放了「銀行／升息／降息」，把總經新聞全掃進來，分數 96 分排第一；收緊之後掉到 78 分第四名。**這是校準問題，不是市場真相**
4. **加速度在小基期時很敏感** — 前兩天 1 則、今天 5 則就是 +400%
5. **沒有歷史趨勢** — 每次都是當下重算，不保存跨日的分數變化（要做的話再加 SQLite）
6. **GDELT 預設關閉** — 免費額度很容易 429
7. **公司與產業的對應是人工維護的** — 不是從財報或營收結構自動推導
8. **people.json 是人工清單** — 不是自動偵測出來的熱門人物；沒驗證過的社群帳號網址一律留空

---

## 12. 測試

```bash
python -m pytest tests -q
```

22 個測試，重點測「不報錯但結果是錯的」那幾種：

- 快照類資料（重大訊息）不能被時間窗砍掉
- 每筆官方訊息要有自己的網址，否則 URL 去重會把 200 多筆殺到剩 1 筆
- 「聊天機器人」不能被分到機器人產業
- 社群沒資料時要重新分配權重，不能算 0 分
- Google News 的筆數不能灌進跨產業的「量」
- 加速度在基期為 0 時不能爆掉

---

## 授權與聲明

程式碼：MIT。

`data/` 裡的新聞標題與連結**屬各原網站所有**，本專案僅做索引與連結，不重製內文。
原始報導請點連結到各來源網站閱讀。若任一來源方不希望被收錄，開 issue 告知即可移除。

**熱度只代表討論度，不代表股價會漲。** 名單上的公司只是與該產業相關，
不是推薦標的。本專案為課程教學示範，**非投資建議**。
