/* ==========================================================================
   마켓펄스 MarketPulse — front-end renderer
   data/markets.json 을 읽어 정적 페이지에 그립니다. 프레임워크 없음.
   ========================================================================== */
(function () {
  "use strict";

  var DATA_URL = "data/markets.json";
  var CAT_LABEL = { economy: "경제·금리", crypto: "코인·금융", ai: "AI·테크", global: "글로벌" };
  var state = { data: null, cat: "all", q: "" };

  var $ = function (id) { return document.getElementById(id); };
  var elGrid = $("grid");
  var elFeatured = $("featured");
  var elCount = $("count");
  var elStamp = $("updated-at");
  var elToast = $("toast");

  /* ---------- formatting ---------- */
  function won(n) { return "₩" + Math.round(n).toLocaleString("ko-KR"); }

  function money(n) {
    if (!n && n !== 0) return "—";
    if (n >= 1e9) return "$" + (n / 1e9).toFixed(n >= 1e10 ? 1 : 2).replace(/\.0+$/, "") + "B";
    if (n >= 1e6) return "$" + (n / 1e6).toFixed(n >= 1e7 ? 1 : 2).replace(/\.0+$/, "") + "M";
    if (n >= 1e3) return "$" + (n / 1e3).toFixed(1).replace(/\.0$/, "") + "K";
    return "$" + Math.round(n);
  }

  function pct(v) {
    if (v === null || v === undefined) return "—";
    return (Math.round(v * 10) / 10).toFixed(1);
  }

  var NOW = new Date();

  function parseDate(iso) {
    if (!iso) return null;
    var d = new Date(iso.length <= 10 ? iso + "T00:00:00Z" : iso);
    return isNaN(d.getTime()) ? null : d;
  }

  function shortDate(iso) {
    var d = parseDate(iso);
    if (!d) return "—";
    var m = d.getUTCMonth() + 1, day = d.getUTCDate(), y = d.getUTCFullYear();
    return (y === NOW.getFullYear() ? "" : y + ".") + m + "." + day;
  }

  function daysLeft(iso) {
    var d = parseDate(iso);
    if (!d) return "";
    var diff = Math.ceil((d.getTime() - NOW.getTime()) / 86400000);
    if (diff < 0) return "마감";
    if (diff === 0) return "오늘 마감";
    return "D-" + diff;
  }

  function deltaBadge(v) {
    var n = Math.round(v * 10) / 10;
    if (n >= 0.5) return '<span class="delta-badge up">▲ ' + pct(n) + "p</span>";
    if (n <= -0.5) return '<span class="delta-badge down">▼ ' + pct(Math.abs(n)) + "p</span>";
    return '<span class="delta-badge flat">변동 없음</span>';
  }

  function deltaText(v) {
    var n = Math.round(v * 10) / 10;
    if (n >= 0.5) return '<span class="delta up">▲ ' + pct(n) + "p</span>";
    if (n <= -0.5) return '<span class="delta down">▼ ' + pct(Math.abs(n)) + "p</span>";
    return '<span class="delta">변동 없음</span>';
  }

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function toast(msg) {
    if (!elToast) return;
    elToast.textContent = msg;
    elToast.classList.add("show");
    clearTimeout(elToast._t);
    elToast._t = setTimeout(function () { elToast.classList.remove("show"); }, 2200);
  }

  /* ---------- render: featured ---------- */
  function renderFeatured() {
    var d = state.data;
    if (!elFeatured) return;
    var items = (d.items || []).filter(function (it) { return it.featured; })
      .sort(function (a, b) { return (a.featured_rank || 9) - (b.featured_rank || 9); });
    if (!items.length) { elFeatured.innerHTML = ""; return; }

    elFeatured.innerHTML = items.map(function (it) {
      var yes = it.yes;
      return '' +
        '<article class="feature" data-rank="' + it.featured_rank + '" data-key="' + esc(it.key) + '" tabindex="0" role="link" aria-label="' + esc(it.title) + ' 자세히 보기">' +
          '<div class="feature-top">' +
            '<span class="feature-rank">TOP ' + it.featured_rank + '</span>' +
            '<span class="feature-cat">' + esc(CAT_LABEL[it.category] || "기타") + '</span>' +
          '</div>' +
          '<h3>' + esc(it.title) + '</h3>' +
          '<div class="feature-num">' +
            '<div class="big">' + pct(yes) + '<span>%</span></div>' +
            '<div class="side">' +
              '<span class="k">YES 확률 · 참가자 기대값</span>' +
              '<span class="v">NO ' + pct(it.no) + '%</span>' +
            '</div>' +
          '</div>' +
          '<div class="bar"><i style="width:' + Math.max(2, Math.min(100, yes)) + '%"></i></div>' +
          '<div class="feature-foot">' +
            '<span>24시간 <b>' + money(it.volume_24h) + '</b></span>' +
            '<span>누적 <b>' + money(it.volume_total) + '</b></span>' +
            '<span>' + esc(shortDate(it.end_date)) + ' 마감</span>' +
            '<span>' + deltaText(it.change_24h) + '</span>' +
          '</div>' +
        '</article>';
    }).join("");

    Array.prototype.forEach.call(elFeatured.querySelectorAll(".feature"), function (node) {
      var go = function () { focusCard(node.getAttribute("data-key")); };
      node.addEventListener("click", go);
      node.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); }
      });
    });
  }

  /* ---------- render: cards ---------- */
  function cardHTML(it) {
    var yes = it.yes;
    var flat = yes < 12 || yes > 88 ? " flat" : "";
    return '' +
      '<article class="card" data-key="' + esc(it.key) + '" data-cat="' + esc(it.category) + '">' +
        '<div class="card-head">' +
          '<span class="chip ' + esc(it.category) + '">' + esc(CAT_LABEL[it.category] || "기타") + '</span>' +
          deltaBadge(it.change_24h) +
        '</div>' +
        '<h3>' + esc(it.title) + '</h3>' +
        '<div class="prob">' +
          '<span class="yes"><span class="lab">YES</span><span class="val">' + pct(yes) + '<small>%</small></span></span>' +
          '<span class="no"><span class="val">' + pct(it.no) + '<small>%</small></span><span class="lab">NO</span></span>' +
        '</div>' +
        '<div class="bar' + flat + '"><i style="width:' + Math.max(2, Math.min(100, yes)) + '%"></i></div>' +
        '<div class="meta">' +
          '<span>24시간 <b>' + money(it.volume_24h) + '</b></span>' +
          '<span>누적 <b>' + money(it.volume_total) + '</b></span>' +
          '<span><b>' + esc(shortDate(it.end_date)) + '</b> 마감' + (daysLeft(it.end_date) ? " · " + daysLeft(it.end_date) : "") + '</span>' +
        '</div>' +
        '<button class="toggle" type="button" aria-expanded="false">' +
          '<span>이슈 배경 &amp; 관전 포인트</span>' +
          '<span class="chev" aria-hidden="true">' +
            '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>' +
          '</span>' +
        '</button>' +
        '<div class="detail">' +
          '<div class="block"><h4>이슈 배경</h4><p>' + esc(it.explain) + '</p></div>' +
          '<div class="block"><h4>관전 포인트</h4><p>' + esc(it.watch) + '</p></div>' +
          '<div class="block origin"><h4>원문 질문</h4><p>' + esc(it.question) + '</p></div>' +
          '<div class="src">출처: Polymarket 공개 데이터' + (it.auto ? " · 자동 선별 항목" : "") +
            ' · 최근 1주 변동 ' + (it.change_1w > 0 ? "+" : "") + pct(it.change_1w) + 'p</div>' +
        '</div>' +
      '</article>';
  }

  function renderCards() {
    var d = state.data;
    var q = state.q.trim().toLowerCase();
    var items = (d.items || []).filter(function (it) {
      if (state.cat !== "all" && it.category !== state.cat) return false;
      if (!q) return true;
      var hay = (it.title + " " + (it.question || "") + " " + (it.event_title || "") + " " + (it.option || "")).toLowerCase();
      return hay.indexOf(q) !== -1;
    });

    elGrid.innerHTML = items.length
      ? items.map(cardHTML).join("")
      : '<div class="empty">조건에 맞는 이슈가 없습니다.<br>다른 키워드로 검색하거나 전체 탭을 눌러 보세요.</div>';

    elCount.textContent = items.length + "개 이슈";
    updateTabCounts();
  }

  function updateTabCounts() {
    var items = state.data.items || [];
    Array.prototype.forEach.call(document.querySelectorAll(".tab"), function (tab) {
      var cat = tab.getAttribute("data-cat");
      var n = cat === "all" ? items.length : items.filter(function (i) { return i.category === cat; }).length;
      var base = tab.getAttribute("data-label") || tab.textContent.replace(/\s\d+$/, "");
      tab.setAttribute("data-label", base);
      tab.innerHTML = esc(base) + ' <span class="n">' + n + "</span>";
    });
  }

  function focusCard(key) {
    var sel = '[data-key="' + String(key).replace(/"/g, '\\"') + '"]';
    var card = elGrid.querySelector(sel);
    if (!card && (state.cat !== "all" || state.q)) {
      state.cat = "all";
      state.q = "";
      if (input) input.value = "";
      Array.prototype.forEach.call(tabs, function (t) {
        t.setAttribute("aria-selected", t.getAttribute("data-cat") === "all" ? "true" : "false");
      });
      renderCards();
      card = elGrid.querySelector(sel);
    }
    if (!card) return;
    card.scrollIntoView({ behavior: "smooth", block: "center" });
    if (!card.classList.contains("open")) card.querySelector(".toggle").click();
    card.style.borderColor = "#93b4f5";
    setTimeout(function () { card.style.borderColor = ""; }, 1600);
  }

  /* ---------- interactions ---------- */
  document.addEventListener("click", function (e) {
    var toggle = e.target.closest ? e.target.closest(".toggle") : null;
    if (toggle) {
      var card = toggle.closest(".card");
      var open = card.classList.toggle("open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    }
  });

  var tabs = document.querySelectorAll(".tab");
  Array.prototype.forEach.call(tabs, function (tab) {
    tab.addEventListener("click", function () {
      Array.prototype.forEach.call(tabs, function (t) { t.setAttribute("aria-selected", "false"); });
      tab.setAttribute("aria-selected", "true");
      state.cat = tab.getAttribute("data-cat");
      renderCards();
    });
  });

  var input = $("q");
  if (input) {
    var t;
    input.addEventListener("input", function () {
      clearTimeout(t);
      t = setTimeout(function () { state.q = input.value; renderCards(); }, 120);
    });
  }

  /* ---------- load ---------- */
  function setStamp(label) {
    if (!elStamp) return;
    var text = String(label || "—");
    var m = text.match(/(\d+)월 (\d+)일 (\d+:\d+)/);
    var short = m ? m[1] + "." + m[2] + " " + m[3] : text.replace(/\s*\(KST\)/, "");
    elStamp.innerHTML = '<span class="stamp-full">' + esc(text) + '</span>' +
                        '<span class="stamp-short">' + esc(short) + '</span>';
  }

  function load(fresh) {
    // 데이터는 항상 캐시를 우회해 최신 갱신본을 읽는다(파일 20KB 내외).
    var url = DATA_URL + "?t=" + Date.now();
    return fetch(url, fresh ? { cache: "no-store" } : { cache: "no-cache" })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (data) {
        state.data = data;
        NOW = new Date();
        setStamp(data.updated_label || data.updated_at || "—");
        var pill = $("pill-count");
        if (pill) pill.textContent = "오늘의 이슈 " + (data.count || (data.items || []).length) + "개";
        renderFeatured();
        renderCards();
        return data;
      });
  }

  function errorState(err) {
    console.error(err);
    setStamp("불러오기 실패");
    elGrid.innerHTML = '<div class="empty">데이터를 불러오지 못했습니다.<br>' +
      '잠시 후 새로고침(↻)을 눌러 주세요.<br><span style="font-size:12px;color:#94a3b8">' +
      esc(err && err.message ? err.message : "") + '</span></div>';
    elCount.textContent = "—";
  }

  var btn = $("refresh");
  if (btn) {
    btn.addEventListener("click", function () {
      btn.classList.add("spinning");
      load(true).then(function () {
        toast("최신 데이터로 갱신했습니다");
      }).catch(function (err) {
        toast("갱신 실패 · 잠시 후 다시 시도해 주세요");
        errorState(err);
      }).then(function () {
        btn.classList.remove("spinning");
      });
    });
  }

  load(false).catch(errorState);
})();
