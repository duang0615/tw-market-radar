/* AI Market Radar — 前端。
   所有資料都在 data/radar.json，這支只負責畫和篩選，沒有任何後端。 */
(function () {
  "use strict";

  var D = null;                       // radar.json
  var state = { group: "全部", hours: 72, q: "", industry: null };

  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  };

  function fmtTime(iso) {
    if (!iso) return "時間不詳";
    var d = new Date(iso);
    if (isNaN(d)) return "時間不詳";
    var p = function (n) { return (n < 10 ? "0" : "") + n; };
    return d.getFullYear() + "/" + p(d.getMonth() + 1) + "/" + p(d.getDate()) +
           " " + p(d.getHours()) + ":" + p(d.getMinutes());
  }

  function heatColor(v) {
    if (v >= 70) return "var(--hot)";
    if (v >= 45) return "var(--warm)";
    return "var(--cool)";
  }

  function trendIcon(t, acc) {
    if (t === "rising") return '<span class="up">🔥 升溫</span>';
    if (t === "falling") return '<span class="down">↓ 降溫</span>';
    return '<span class="flat">— 持平</span>';
  }

  /* ── 篩選 ───────────────────────────────────────────── */
  function matchQ(ind) {
    var q = state.q.trim().toLowerCase();
    if (!q) return true;
    if (ind.name.toLowerCase().indexOf(q) >= 0) return true;
    if (ind.id.indexOf(q) >= 0) return true;
    for (var i = 0; i < ind.stocks.length; i++) {
      var s = ind.stocks[i];
      if (s.code.indexOf(q) >= 0 || s.name.toLowerCase().indexOf(q) >= 0) return true;
    }
    for (var j = 0; j < ind.events.length; j++) {
      if (ind.events[j].title.toLowerCase().indexOf(q) >= 0) return true;
    }
    return false;
  }

  function visibleIndustries() {
    return D.industries.filter(function (r) {
      if (state.group !== "全部" && r.group !== state.group) return false;
      if (state.industry && r.id !== state.industry) return false;
      return matchQ(r);
    });
  }

  function visibleNews() {
    var cutoff = Date.now() - state.hours * 3600 * 1000;
    var q = state.q.trim().toLowerCase();
    var groups = {};
    D.industries.forEach(function (r) { groups[r.id] = r.group; });

    // 鎖定單一產業時，top_news（全域前 40 則）通常只剩一兩則，
    // 改用該產業自己的事件清單，才看得到東西。
    var pool = D.top_news;
    if (state.industry) {
      var ind = D.industries.filter(function (r) { return r.id === state.industry; })[0];
      var seen = {};
      pool = (ind ? ind.events : []).concat(D.top_news).filter(function (e) {
        if (seen[e.id]) return false;
        seen[e.id] = 1;
        return true;
      });
    }
    return pool.filter(function (e) {
      var t = e.published_at ? new Date(e.published_at).getTime() : 0;
      if (t && t < cutoff) return false;
      if (state.industry && e.industries.indexOf(state.industry) < 0) return false;
      if (state.group !== "全部") {
        var ok = e.industries.some(function (i) { return groups[i] === state.group; });
        if (!ok) return false;
      }
      if (q && e.title.toLowerCase().indexOf(q) < 0) return false;
      return true;
    });
  }

  /* ── 畫面 ───────────────────────────────────────────── */
  function renderRank(rows) {
    var name = {};
    D.industries.forEach(function (r) { name[r.id] = r.name; });
    $("rank").innerHTML = rows.slice(0, 20).map(function (r) {
      return '<tr data-id="' + r.id + '">' +
        '<td class="rk">' + r.rank + "</td>" +
        '<td class="nm">' + esc(r.name) +
          '<span class="grp">' + esc(r.group) + "</span></td>" +
        "<td><span class='bar'><i style='width:" + Math.max(3, r.heat_score) +
          "%;background:" + heatColor(r.heat_score) + "'></i></span>" +
          "<span class='hs'>" + r.heat_score.toFixed(1) + "</span></td>" +
        '<td class="acc ' + (r.acceleration > 0 ? "up" : r.acceleration < 0 ? "down" : "flat") +
          '">' + (r.acceleration > 0 ? "+" : "") + Math.round(r.acceleration) + "%</td>" +
        "<td>" + r.news_count + "</td>" +
        "<td>" + r.social_mentions + "</td>" +
        "<td>" + r.official_events + "</td>" +
        '<td class="cov">' + r.coverage + "%</td>" +
        "<td>" + trendIcon(r.trend, r.acceleration) + "</td></tr>";
    }).join("");
    $("rankEmpty").hidden = rows.length > 0;

    Array.prototype.forEach.call($("rank").querySelectorAll("tr"), function (tr) {
      tr.addEventListener("click", function () {
        state.industry = (state.industry === tr.dataset.id) ? null : tr.dataset.id;
        render();
        window.scrollTo({ top: 0, behavior: "smooth" });
      });
    });
  }

  function renderWhy(rows) {
    $("why").innerHTML = rows.slice(0, 6).map(function (r) {
      var why = (r.why_hot || []).map(function (w) { return "<li>" + esc(w) + "</li>"; }).join("");
      var evs = (r.events || []).slice(0, 3).map(function (e) {
        return '<div class="ev">· <a href="' + esc(e.url) + '" target="_blank" rel="noopener">' +
               esc(e.title) + "</a>" +
               (e.count > 1 ? " <span class='badge'>" + e.count + " 家報導</span>" : "") +
               "</div>";
      }).join("");
      var stk = (r.stocks || []).slice(0, 10).map(function (s) {
        return "<span class='" + (s.highlighted ? "hi" : "") + "'>" +
               esc(s.code) + " " + esc(s.name) + "</span>";
      }).join("");
      return '<div class="card">' +
        '<div class="ch"><b>' + esc(r.name) + "</b>" +
          "<span class='s' style='color:" + heatColor(r.heat_score) + "'>" +
          r.heat_score.toFixed(0) + "</span>" +
          '<span class="acc ' + (r.acceleration >= 0 ? "up" : "down") + '">' +
          (r.acceleration >= 0 ? "+" : "") + Math.round(r.acceleration) + "%</span>" +
          '<span class="tagai">' + (r.ai_generated ? "AI 摘要" : "資料統計") + "</span></div>" +
        "<ul>" + why + "</ul>" + evs +
        (stk ? '<div class="stk">' + stk + "</div>" : "") +
        "</div>";
    }).join("");
  }

  function renderNews(list) {
    var name = {};
    D.industries.forEach(function (r) { name[r.id] = r.name; });
    $("news").innerHTML = list.slice(0, 60).map(function (e) {
      var inds = (e.industries || []).slice(0, 3).map(function (i) {
        return '<span class="ind">' + esc(name[i] || i) + "</span>";
      }).join("");
      return "<li><div class='m'>" +
        "<span>" + fmtTime(e.published_at) + "</span>" +
        "<span>" + esc((e.sources || []).slice(0, 3).join("、")) + "</span>" +
        (e.count > 1 ? "<span class='badge'>" + e.count + " 則併為一事件</span>" : "") +
        inds + "</div>" +
        "<a class='t' href='" + esc(e.url) + "' target='_blank' rel='noopener'>" +
        esc(e.title) + "</a></li>";
    }).join("");
    $("newsEmpty").hidden = list.length > 0;
  }

  function renderPeople() {
    var name = {};
    D.industries.forEach(function (r) { name[r.id] = r.name; });
    $("ppl").innerHTML = (D.people || []).map(function (p) {
      var tp = (p.topics || []).map(function (t) { return name[t] || t; }).join("、");
      var title = p.zh ? p.name + "（" + p.zh + "）" : p.name;
      var inner = "<b>" + esc(title) + "</b>" +
        '<div class="o">' + esc(p.org || "") + " · " + esc(p.type) + "</div>" +
        '<div class="tp">' + esc(tp) + "</div>";
      return '<div class="p">' + (p.url ? "<a href='" + esc(p.url) +
             "' target='_blank' rel='noopener'>" + inner + "</a>" : inner) + "</div>";
    }).join("");
    $("pplNote").innerHTML =
      "這份名單是<b>人工維護</b>的追蹤清單（<code>data/people.json</code>），" +
      "不是自動從社群抓出來的熱門人物。<br>" +
      "沒有經過驗證的社群帳號網址一律留空，不亂猜——寧可沒有連結，也不要給錯的連結。";
  }

  function renderHeader() {
    var c = D.counts || {};
    $("sub").innerHTML =
      "過去 " + D.window_hours + " 小時 · 最後更新 " + esc(fmtTime(D.generated_at)) +
      " · 原始 " + (c.raw || 0) + " 筆 → 視窗內 " + (c.in_window || 0) +
      " 筆 → 聚成 " + (c.events || 0) + " 個事件 · 行情 " + (c.quotes || 0) + " 檔";
    $("mkt").textContent = D.market_summary || "";

    var cf = D.config || {};
    var repo = (cf.repo || "").trim();
    var btn = repo
      ? "<a class='btn go' target='_blank' rel='noopener' href='https://github.com/" + esc(repo) +
        "/actions/workflows/update-radar.yml'>立即更新</a>" +
        "<a class='btn' target='_blank' rel='noopener' href='https://github.com/" + esc(repo) +
        "/edit/main/config.json'>改設定</a>" +
        "<a class='btn' target='_blank' rel='noopener' href='https://github.com/" + esc(repo) +
        "'>原始碼</a>"
      : "";
    var miss = (D.signals_missing || []);
    var LAB = { news_volume: "新聞量", news_accel: "新聞增速", social_volume: "社群量",
                social_accel: "社群增速", official: "官方事件", market: "市場異動" };
    $("cfg").innerHTML =
      "<span>自動更新</span><span class='sw " + (cf.auto_update ? "on'>開啟" : "off'>已關閉") + "</span>" +
      "<span>每天</span><span class='vv'>" + esc(cf.update_time || "08:00") + "</span><span>台灣時間</span>" +
      "<span>· AI 摘要</span><span class='vv'>" + (D.ai_enabled ? "開啟" : "未設定 API key，改用資料統計") + "</span>" +
      (miss.length ? "<span>· 缺資料的訊號</span><span class='vv'>" +
        esc(miss.map(function (m) { return LAB[m] || m; }).join("、")) + "（權重已重新分配）</span>" : "") +
      "<span class='sp'></span>" + btn;

    $("foot").innerHTML =
      "資料來源：證交所 OpenAPI／櫃買 OpenAPI／期交所 RSS／鉅亨網／TechNews／iThome／經濟日報／" +
      "MoneyDJ・DigiTimes・工商時報・自由財經（Google News 站內搜尋）／PTT Stock・Tech_Job。" +
      "由 GitHub Actions 自動更新，整條 pipeline 只用 Python 標準函式庫。";
  }

  function render() {
    var rows = visibleIndustries();
    renderRank(rows);
    renderWhy(rows);
    var news = visibleNews();
    renderNews(news);
    $("count").textContent = "產業 " + rows.length + " / " + D.industries.length +
      " · 新聞 " + news.length + " 則" + (state.industry ? "（已鎖定單一產業，再點一次取消）" : "");
  }

  function buildChips() {
    var groups = ["全部"];
    D.industries.forEach(function (r) {
      if (r.group && groups.indexOf(r.group) < 0) groups.push(r.group);
    });
    $("groups").innerHTML = groups.map(function (g) {
      return "<span class='chip" + (g === state.group ? " on" : "") + "' data-g='" +
             esc(g) + "'>" + esc(g) + "</span>";
    }).join("");
    Array.prototype.forEach.call($("groups").children, function (c) {
      c.addEventListener("click", function () {
        state.group = c.dataset.g; state.industry = null;
        buildChips(); render();
      });
    });

    var times = [[6, "最近 6 小時"], [24, "最近 24 小時"], [72, "最近 72 小時"]];
    $("times").innerHTML = times.map(function (t) {
      return "<span class='chip" + (t[0] === state.hours ? " on" : "") + "' data-h='" +
             t[0] + "'>" + t[1] + "</span>";
    }).join("");
    Array.prototype.forEach.call($("times").children, function (c) {
      c.addEventListener("click", function () {
        state.hours = parseInt(c.dataset.h, 10);
        buildChips(); render();
      });
    });
  }

  fetch("data/radar.json", { cache: "no-store" })
    .then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(function (j) {
      D = j;
      renderHeader();
      renderPeople();
      buildChips();
      render();
      $("q").addEventListener("input", function () { state.q = this.value; render(); });
    })
    .catch(function (e) {
      $("sub").textContent = "讀不到 data/radar.json（" + e.message + "）";
      $("mkt").innerHTML = "請先在本機跑一次 <code>python scripts/build_radar.py</code>，" +
        "或等 GitHub Actions 產生資料。直接用 file:// 開啟時瀏覽器會擋 fetch，" +
        "請改用 <code>python -m http.server 8000</code> 開。";
    });
})();
