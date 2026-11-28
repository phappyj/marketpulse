/* ==========================================================================
   예측판 YECHEUKPAN — core
   ·Supabase REST/RPC 연결, 예측 카드 렌더, 한줄 투표, 이슈 상세·댓글
   ========================================================================== */
(function () {
  "use strict";

  var YP = window.YP = window.YP || {};
  var CFG = YP.supabase || {};
  var $ = function (id) { return document.getElementById(id); };

  /* ---------------- utils ---------------- */
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  // 이슈별 정적 페이지(/issues/{slug}.html) 파일명 — scripts/build_issue_pages.py 와 같은 규칙
  function issueSlug(key) {
    var s = String(key == null ? "" : key).trim().toLowerCase()
      .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
    return s || "issue";
  }

  function uid() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return "id-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 10);
  }

  function lsGet(k) {
    try { return localStorage.getItem(k); } catch (e) { return null; }
  }
  function lsSet(k, v) {
    try { localStorage.setItem(k, v); } catch (e) { /* ignore */ }
  }

  var CLIENT_ID = lsGet("yp_cid");
  if (!CLIENT_ID) { CLIENT_ID = uid(); lsSet("yp_cid", CLIENT_ID); }

  var toastTimer = null;
  function toast(msg, isErr) {
    var el = $("toast");
    if (!el) return;
    el.textContent = msg;
    el.className = "toast show" + (isErr ? " err" : "");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.className = "toast"; }, 2600);
  }

  var ERR = {
    cooldown: "연속 작성은 15초 뒤에 가능합니다.",
    rate_limited: "잠시 후 다시 시도해 주세요. (1시간 작성 한도)",
    banned: "금칙어가 포함되어 등록할 수 없습니다. (도박·홍보·욕설)",
    bad_pw: "비밀번호는 숫자 4자리입니다.",
    wrong_pw: "비밀번호가 맞지 않습니다. 작성할 때 입력한 4자리를 확인해 주세요.",
    bad_choice: "투표 값을 확인해 주세요.",
    bad_issue: "이슈 정보를 확인하지 못했습니다.",
    bad_kind: "신고 대상을 확인하지 못했습니다.",
    bad_category: "말머리를 선택해 주세요.",
    client_required: "브라우저 저장 공간이 막혀 참여할 수 없습니다. 쿠키·저장을 허용해 주세요.",
    nickname_required: "닉네임을 입력해 주세요.",
    nickname_too_long: "닉네임은 16자까지 가능합니다.",
    text_required: "내용을 입력해 주세요.",
    text_too_long: "내용이 너무 깁니다. 조금 줄여 주세요.",
    post_not_found: "삭제되었거나 없는 글입니다.",
    not_found: "이미 삭제된 항목입니다.",
    protected_post: "운영 공지 글은 삭제할 수 없습니다.",
    "PGRST202": "서버 기능을 찾지 못했습니다. 잠시 후 다시 시도해 주세요."
  };
  function errMsg(e) {
    var m = (e && (e.message || e.msg)) || "";
    if (ERR[m]) return ERR[m];
    if (/Failed to fetch|NetworkError|Load failed/i.test(m)) return "네트워크 오류입니다. 연결을 확인해 주세요.";
    return m || "알 수 없는 오류가 발생했습니다.";
  }

  /* 금칙어 — 서버에서 한 번 더 검사합니다(즉시 안내용) */
  var BANNED = [
    "토토", "사설", "사설토토", "배팅사이트", "먹튀", "바카라", "카지노", "슬롯", "파워볼",
    "스포츠토토", "프로토", "온라인카지노", "배당률", "배당판", "역배", "정배",
    "레퍼럴", "추천인", "리퍼럴", "수익인증",
    "리딩방", "텔레그램", "오픈채팅", "카톡주세요", "카톡문의", "디엠주세요", "대리입금",
    "환전", "선입금", "고정수익", "원금보장", "100%수익", "폭리",
    /* 접속 우회·가입 유도·입금 안내 금지 (해외 거래소 관련 법적 안전선) */
    "vpn", "우회", "가입링크", "추천인코드", "초대코드", "입금방법", "지갑연결",
    "픽공유", "텔레그램방",
    "씨발", "시발", "ㅅㅂ", "병신", "븅신", "좆", "지랄", "염병", "미친놈", "미친년",
    "개새끼", "새끼", "닥쳐", "꺼져"
  ];
  function findBanned(text) {
    var t = String(text || "").toLowerCase();
    for (var i = 0; i < BANNED.length; i++) {
      if (t.indexOf(BANNED[i].toLowerCase()) !== -1) return BANNED[i];
    }
    return null;
  }

  function nick() { return lsGet("yp_nick") || ""; }
  function setNick(v) { if (v) lsSet("yp_nick", String(v).slice(0, 16)); }

  var COOLDOWN_MS = 15000;
  function cooldownLeft(bucket) {
    var last = parseInt(lsGet("yp_last_" + bucket) || "0", 10);
    var left = last + COOLDOWN_MS - Date.now();
    return left > 0 ? Math.ceil(left / 1000) : 0;
  }
  function markWrite(bucket) { lsSet("yp_last_" + bucket, String(Date.now())); }

  /* ---------------- API ---------------- */
  function api(path, body, method) {
    var url = CFG.url + "/rest/v1/" + path;
    var ctrl = (typeof AbortController !== "undefined") ? new AbortController() : null;
    var timer = ctrl ? setTimeout(function () { try { ctrl.abort(); } catch (e) {} }, 12000) : null;
    return fetch(url, {
      method: method || (body ? "POST" : "GET"),
      headers: {
        "apikey": CFG.key,
        "Authorization": "Bearer " + CFG.key,
        "Content-Type": "application/json"
      },
      body: body ? JSON.stringify(body) : undefined,
      signal: ctrl ? ctrl.signal : undefined
    }).then(function (r) {
      return r.text().then(function (txt) {
        var data = null;
        try { data = txt ? JSON.parse(txt) : null; } catch (e) { data = txt; }
        if (!r.ok) {
          var err = new Error((data && (data.message || data.hint || data.code)) || ("HTTP " + r.status));
          err.payload = data;
          throw err;
        }
        return data;
      });
    }).then(function (data) {
      if (timer) clearTimeout(timer);
      return data;
    }, function (e) {
      if (timer) clearTimeout(timer);
      throw (e && e.name === "AbortError") ? new Error("요청 시간이 초과되었습니다.") : e;
    });
  }

  // 읽기 전용 RPC — 실패하면 한 번만 다시 시도합니다(쓰기는 재시도하지 않음)
  var READ_RPCS = {
    yp_vote_tally: 1, yp_my_votes: 1, yp_comment_counts: 1,
    yp_issue_comments: 1, yp_list_posts: 1, yp_get_post: 1
  };
  function rpc(name, args) {
    var call = function () { return api("rpc/" + name, args || {}); };
    if (!READ_RPCS[name]) return call();
    return call().catch(function () {
      return new Promise(function (res) { setTimeout(res, 600); }).then(call);
    });
  }

  /* ---------------- time ---------------- */
  function relTime(iso) {
    if (!iso) return "";
    var d = new Date(iso);
    if (isNaN(d.getTime())) return "";
    var diff = (Date.now() - d.getTime()) / 1000;
    if (diff < 60) return "방금";
    if (diff < 3600) return Math.floor(diff / 60) + "분 전";
    if (diff < 86400) return Math.floor(diff / 3600) + "시간 전";
    if (diff < 172800) return "어제";
    if (diff < 604800) return Math.floor(diff / 86400) + "일 전";
    var m = d.getMonth() + 1, day = d.getDate();
    var y = d.getFullYear();
    return (y === new Date().getFullYear() ? "" : y + ".") + m + "." + day;
  }

  /* ---------------- state ---------------- */
  var state = {
    data: null,
    byMid: {},      // Polymarket market id -> item (Kalshi 항목은 mid 없음)
    cat: "all",
    q: "",
    openKey: null,
    tally: {},      // issue_key -> {yes, no}
    mine: {},       // issue_key -> 'yes'|'no'
    cmtCount: {},   // issue_key -> n
    cmtRows: {},    // issue_key -> rows | null(미로드)
    issueViews: {}  // issue_key -> 조회(클릭) 수
  };

  var CAT_LABEL = { economy: "경제·금리", crypto: "코인·금융", ai: "AI·테크", global: "글로벌" };

  /* 카테고리 미니 심볼 */
  var CAT_ICON = {
    economy: '<svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M1.2 9.6L4 6.6l2.2 2.2L10.8 3.9"/><path d="M8.2 3.9h2.6v2.6"/></svg>',
    crypto: '<svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 .9v10.2"/><path d="M3.6 2.7h3.1a1.7 1.7 0 010 3.4H3.6h3.4a1.7 1.7 0 010 3.4H3.6"/></svg>',
    ai: '<svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round" aria-hidden="true"><path d="M6 1.2l1.3 3.1L10.4 5.6 7.3 6.9 6 10 4.7 6.9 1.6 5.6l3.1-1.3z"/></svg>',
    global: '<svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.3" aria-hidden="true"><circle cx="6" cy="6" r="4.5"/><path d="M1.6 6h8.8M6 1.5c1.7 1.4 1.7 7.6 0 9"/></svg>'
  };

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
  function parseDate(iso) {
    if (!iso) return null;
    var d = new Date(iso.length <= 10 ? iso + "T00:00:00Z" : iso);
    return isNaN(d.getTime()) ? null : d;
  }
  function shortDate(iso) {
    var d = parseDate(iso); if (!d) return "—";
    return (d.getUTCFullYear() === new Date().getFullYear() ? "" : d.getUTCFullYear() + ".")
      + (d.getUTCMonth() + 1) + "." + d.getUTCDate();
  }
  function daysLeft(iso) {
    var d = parseDate(iso); if (!d) return "";
    var diff = Math.ceil((d.getTime() - Date.now()) / 86400000);
    if (diff < 0) return "마감";
    if (diff === 0) return "오늘 마감";
    return "D-" + diff;
  }

  /* 카테고리 배지 */
  function ctag(cat) {
    return '<span class="ctag ' + esc(cat) + '">' + (CAT_ICON[cat] || "") +
      esc(CAT_LABEL[cat] || "기타") + '</span>';
  }

  /* ---------- 출처 표기 (Kalshi / Polymarket) ---------- */
  function sourceOf(it) { return (it && it.source) ? it.source : "Polymarket"; }

  function srcTag(it) {
    var s = sourceOf(it);
    var tip = s === "Kalshi"
      ? "미국 CFTC 인가 Kalshi 공개 시장 · 2시간마다 갱신되는 저장 데이터"
      : "글로벌 공개 시장 Polymarket · 1분마다 실시간 갱신";
    return '<span class="src-tag ' + (s === "Kalshi" ? "kalshi" : "pm") + '" title="' + esc(tip) + '">' +
      esc(s) + '</span>';
  }

  /* 카드·상세에 붙는 갱신 주기 — Kalshi(2시간 저장값)와 Polymarket(1분 실시간)을 섮지 않게 */
  function freshTag(it) {
    var k = sourceOf(it) === "Kalshi";
    return '<span class="fresh-tag ' + (k ? "kalshi" : "pm") + '">' +
      (k ? "2시간마다 갱신" : "1분마다 실시간 갱신") + '</span>';
  }

  /* Kalshi 거래량은 계약 수, Polymarket 은 금액이다. */
  function contracts(n) {
    if (n === null || n === undefined || n === "") return "—";
    n = Number(n);
    if (!isFinite(n)) return "—";
    if (n >= 1e8) return (n / 1e8).toFixed(1).replace(/\.0$/, "") + "억계약";
    if (n >= 1e4) return (n / 1e4).toFixed(1).replace(/\.0$/, "") + "만계약";
    return Math.round(n).toLocaleString() + "계약";
  }  function volTxt(n, it) { return sourceOf(it) === "Kalshi" ? contracts(n) : money(n); }
  function heatOf(it) {
    return (Number(it.volume_24h) || 0) + 0.01 * (Number(it.open_interest) || 0);
  }
  /* 변동 배지 — 있을 때만, 작게 */
  function deltaChip(v) {
    if (v === null || v === undefined) return "";
    var n = Math.round(Number(v) * 10) / 10;
    if (!isFinite(n) || Math.abs(n) < 0.5) return "";
    return n > 0
      ? '<span class="dlt up" title="최근 24시간 변동">▲ ' + pct(n) + 'p</span>'
      : '<span class="dlt down" title="최근 24시간 변동">▼ ' + pct(Math.abs(n)) + 'p</span>';
  }

  function itemByKey(key) {
    var items = (state.data && state.data.items) || [];
    for (var i = 0; i < items.length; i++) { if (items[i].key === key) return items[i]; }
    return null;
  }

  /* ---------------- 1클릭 투표 ---------------- */
  /* 라벨 — 카드·상세 공용. 글로벌 시장 확률과 예측판 유저 투표를 같은 언어로 구분합니다. */
  var LB_GLOBAL = '<span class="src-lb glob">🌐 글로벌 시장 확률<b class="y">YES</b></span>';
  var LB_USER = '<span class="src-lb user">🇰🇷 예측판 유저 투표</span>';

  function voteTotal(key) {
    var t = state.tally[key] || { yes: 0, no: 0 };
    return Number(t.yes || 0) + Number(t.no || 0);
  }

  /* 참여 현황 — 아직 없으면 안내 문구, 있으면 YES/NO 비율과 인원 */
  function voteStatHTML(key) {
    var t = state.tally[key] || { yes: 0, no: 0 };
    var y = Number(t.yes || 0), n = Number(t.no || 0), tot = y + n;
    if (!tot) return '<span class="emp">아직 0명 · 첫 투표</span>';
    var yp = Math.round((y / tot) * 100), np = 100 - yp;
    return '<span class="y">YES ' + yp + '%</span> · <span class="n">NO ' + np + '%</span> <span class="c">(' + tot + '명)</span>';
  }

  function voteHTML(key) {
    var t = state.tally[key] || { yes: 0, no: 0 };
    var tot = (t.yes || 0) + (t.no || 0);
    var mine = state.mine[key] || "";
    var tip = tot
      ? "예측판 유저 투표 " + tot + "명 참여 (YES " + t.yes + " · NO " + t.no + ")" + (mine ? " · 내 선택 " + (mine === "yes" ? "YES" : "NO") : "")
      : "예측판 유저 투표 — 위의 글로벌 시장 확률과 별개로, 당신의 판단은?";
    return '' +
      '<div class="vote-row" data-vote="' + esc(key) + '" role="group" aria-label="예측판 유저 투표">' +
        '<button type="button" class="vbtn yes' + (mine === "yes" ? " mine" : "") + '" data-choice="yes" aria-pressed="' + (mine === "yes") + '" title="' + esc(tip) + '">' +
          '👍 YES' +
        '</button>' +
        '<button type="button" class="vbtn no' + (mine === "no" ? " mine" : "") + '" data-choice="no" aria-pressed="' + (mine === "no") + '" title="' + esc(tip) + '">' +
          '👎 NO' +
        '</button>' +
      '</div>';
  }

  /* ---------------- 오늘의 주요 예측 (슬림 1줄) ---------------- */
  function renderFeatured() {
    var el = $("featured");
    if (!el) return;
    var items = (state.data && state.data.items || []).filter(function (it) { return it.featured; })
      .sort(function (a, b) { return (a.featured_rank || 9) - (b.featured_rank || 9); })
      .slice(0, 3);
    if (!items.length) { el.innerHTML = '<span class="loading">주요 이슈를 준비 중입니다.</span>'; return; }

    el.innerHTML = items.map(function (it, i) {
      return '<button type="button" class="topline-it" data-key="' + esc(it.key) + '" title="' + esc(it.title) + '">' +
          '<span class="rk">' + (i + 1) + '</span>' +
          '<span class="t">' + esc(it.title) + '</span>' +
          '<span class="p">' + pct(it.yes) + '%</span>' +
        '</button>';
    }).join("");
  }

  /* ---------------- 사이드바: 인기 이슈 TOP 5 ---------------- */
  function renderSidebar() {
    var el = $("side-hot");
    if (!el || !state.data) return;
    var items = (state.data.items || []).slice().sort(function (a, b) {
      var fa = a.featured ? 1 : 0, fb = b.featured ? 1 : 0;
      if (fa !== fb) return fb - fa;
      return heatOf(b) - heatOf(a);
    }).slice(0, 5);
    el.innerHTML = items.map(function (it, i) {
      return '<li data-hot-key="' + esc(it.key) + '" title="' + esc(it.title) + '">' +
          '<span class="rk">' + (i + 1) + '</span>' +
          '<span class="hot-t">' +
            '<span class="ti">' + esc(it.title) + '</span>' +
            '<span class="mt">' + esc(CAT_LABEL[it.category] || "기타") + ' · YES <b>' + pct(it.yes) + '%</b></span>' +
          '</span>' +
        '</li>';
    }).join("");
  }

  /* ---------------- 예측 카드 ---------------- */
  function cmtChip(key) {
    var n = state.cmtCount[key] || 0;
    return '<button type="button" class="pcard-cmt' + (n ? " has" : "") + '" data-goto-cmt="' + esc(key) + '" ' +
      'aria-label="이슈 댓글 ' + n + '개 보기" title="이슈 댓글 보기">💬 <b data-cmt-count="' + esc(key) + '">' + n + '</b></button>';
  }

  function viewChip(key) {
    var n = state.issueViews[key] || 0;
    return '<span class="pcard-views" title="이슈 조회 수">👁 <b data-issue-views="' + esc(key) + '">' + n + '</b></span>';
  }

  function cardHTML(it) {
    var yes = Math.max(0, Math.min(100, Number(it.yes) || 0));
    var dl = daysLeft(it.end_date);
    var meta = '누적 ' + volTxt(it.volume_total, it) + (dl ? ' <span class="sp">·</span> ' + esc(dl) : '');
    return '' +
      '<article class="pcard" data-key="' + esc(it.key) + '" data-cat="' + esc(it.category) + '">' +
        '<div class="pcard-hit" role="button" tabindex="0" data-expand="' + esc(it.key) + '" aria-haspopup="dialog" aria-expanded="false" aria-label="' + esc(it.title) + ' 상세 보기">' +
          '<div class="pcard-top">' + ctag(it.category) + srcTag(it) + deltaChip(it.change_24h) + viewChip(it.key) + cmtChip(it.key) + '</div>' +
          '<h3 class="pcard-t">' + esc(it.title) + '</h3>' +
          '<div class="pcard-glob">' +
            LB_GLOBAL +
            '<span class="pcard-pv">' + pct(it.yes) + '<small>%</small></span>' +
            '<span class="gauge"><i style="width:' + Math.max(2, yes) + '%"></i></span>' +
            '<div class="pcard-meta">' + meta + '</div>' +
            '<div class="pcard-fresh">' + freshTag(it) + '</div>' +
          '</div>' +
        '</div>' +
        '<div class="pcard-foot">' +
          '<div class="vote-hd">' + LB_USER +
            '<span class="st" data-vote-st="' + esc(it.key) + '">' + voteStatHTML(it.key) + '</span>' +
          '</div>' +
          voteHTML(it.key) +
        '</div>' +
        '<a class="pcard-open" href="issues/' + esc(issueSlug(it.key)) + '.html">상세 페이지 열기 ↗</a>' +
      '</article>';
  }

  function renderCards() {
    var el = $("grid");
    if (!el) return;
    var q = state.q.trim().toLowerCase();
    var items = ((state.data && state.data.items) || []).filter(function (it) {
      if (state.cat !== "all" && it.category !== state.cat) return false;
      if (!q) return true;
      var hay = (it.title + " " + (it.question || "") + " " + (it.event_title || "") + " " + (it.option || "")).toLowerCase();
      return hay.indexOf(q) !== -1;
    });

    el.innerHTML = items.length
      ? items.map(cardHTML).join("")
      : '<div class="empty"><b>조건에 맞는 이슈가 없습니다.</b>다른 키워드로 검색하거나 전체 탭을 눌러 보세요.</div>';

    var cnt = $("count");
    if (cnt) cnt.textContent = items.length + "개 이슈";
    updateTabCounts();
    if (state.openKey) {
      var hit = el.querySelector('.pcard[data-key="' + state.openKey + '"] .pcard-hit');
      if (hit) hit.setAttribute("aria-expanded", "true");
    }
  }

  function updateTabCounts() {
    var items = (state.data && state.data.items) || [];
    Array.prototype.forEach.call(document.querySelectorAll("#tabs .chip-btn"), function (tab) {
      var cat = tab.getAttribute("data-cat");
      var n = cat === "all" ? items.length : items.filter(function (i) { return i.category === cat; }).length;
      var base = tab.getAttribute("data-label") || tab.textContent.replace(/\s\d+$/, "");
      tab.setAttribute("data-label", base);
      tab.innerHTML = esc(base) + ' <span class="n">' + n + '</span>';
    });
  }

  /* ---------------- 이슈 상세 (모달) ---------------- */
  function detailHTML(it) {
    var yes = Math.max(0, Math.min(100, Number(it.yes) || 0));
    var dl = daysLeft(it.end_date);
    var n = state.cmtCount[it.key] || 0;
    var w1 = (it.change_1w === null || it.change_1w === undefined)
      ? '<b>—</b>'
      : '<b class="' + (Number(it.change_1w) < 0 ? 'down' : 'up') + '">' +
        (Number(it.change_1w) > 0 ? '+' : '') + pct(it.change_1w) + 'p</b>';
    return '' +
      '<h2 class="dd-title" id="dd-title">' + esc(it.title) + '</h2>' +
      '<div class="dd-glob">' +
        LB_GLOBAL + freshTag(it) +
        '<div class="dd-prob">' +
          '<span class="dd-pv">' + pct(it.yes) + '<small>%</small></span>' +
          '<span class="side"><span>시장 NO</span><b>' + pct(it.no) + '%</b></span>' +
        '</div>' +
        '<span class="gauge"><i style="width:' + Math.max(2, yes) + '%"></i></span>' +
      '</div>' +
      '<ul class="dd-facts">' +
        '<li>24시간 거래량 <b>' + volTxt(it.volume_24h, it) + '</b></li>' +
        '<li>누적 거래량 <b>' + volTxt(it.volume_total, it) + '</b></li>' +
        '<li>마감 <b>' + esc(shortDate(it.end_date)) + (dl ? ' · ' + esc(dl) : '') + '</b></li>' +
        '<li>최근 1주 변동 ' + w1 + '</li>' +
        '<li>조회 <b data-issue-views="' + esc(it.key) + '">' + (state.issueViews[it.key] || 0) + '</b></li>' +
      '</ul>' +
      '<div class="dd-vote">' +
        '<div class="vote-hd">' + LB_USER +
          '<span class="st" data-vote-st="' + esc(it.key) + '">' + voteStatHTML(it.key) + '</span>' +
        '</div>' +
        voteHTML(it.key) +
      '</div>' +
      '<div class="dd-blocks">' +
        '<div class="dd-block"><h4>이슈 배경</h4><p>' + esc(it.explain) + '</p></div>' +
        '<div class="dd-block"><h4>관전 포인트</h4><p>' + esc(it.watch) + '</p></div>' +
        '<div class="dd-block origin"><h4>원문 질문</h4><p>' + esc(it.question) + '</p></div>' +
      '</div>' +
      '<a class="dd-open" href="issues/' + esc(issueSlug(it.key)) + '.html">' +
        '📄 이 이슈 상세 페이지 열기 ↗ <span>해설·1개월 변화·판정 기준</span></a>' +
      '<div class="dd-src">출처 · ' + esc(sourceOf(it)) + ' 공개 데이터 · ' +
        (sourceOf(it) === "Kalshi" ? '2시간마다 갱신되는 저장값' : '1분마다 실시간 갱신') +
        (it.auto ? ' · 자동 선별 항목' : '') + '</div>' +
      '<div class="cmt-box" id="dd-cmt" data-cmt-box="' + esc(it.key) + '">' +
        '<div class="cmt-head">💬 이슈 댓글 <span class="n" data-cmt-count2="' + esc(it.key) + '">' + n + '</span></div>' +
        '<div class="cmt-list" data-cmt-list="' + esc(it.key) + '"></div>' +
        cmtFormHTML("issue", it.key) +
      '</div>';
  }

  function openDetail(key, opts) {
    var it = itemByKey(key);
    if (!it || !$("detail-ov")) return;
    var prev = state.openKey;
    if (prev && prev !== key) {
      var pc = document.querySelector('.pcard[data-key="' + prev + '"] .pcard-hit');
      if (pc) pc.setAttribute("aria-expanded", "false");
    }
    state.openKey = key;

    var badge = $("dd-badge"), delta = $("dd-delta");
    if (badge) badge.innerHTML = ctag(it.category);
    if (delta) delta.innerHTML = deltaChip(it.change_24h);

    var body = $("dd-body");
    body.innerHTML = detailHTML(it);
    body.scrollTop = 0;

    $("detail-ov").classList.add("show");
    document.body.classList.add("no-scroll");

    var hit = document.querySelector('.pcard[data-key="' + key + '"] .pcard-hit');
    if (hit) hit.setAttribute("aria-expanded", "true");

    trackIssueView(key);
    renderComments(key);

    var x = document.querySelector("#detail-ov .x");
    if (x) setTimeout(function () { try { x.focus({ preventScroll: true }); } catch (e) { x.focus(); } }, 40);

    if (opts && opts.cmt) {
      setTimeout(function () {
        var c = $("dd-cmt");
        if (c) c.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 240);
    }
  }

  function closeDetail() {
    var ov = $("detail-ov");
    if (!ov || !ov.classList.contains("show")) return;
    ov.classList.remove("show");
    document.body.classList.remove("no-scroll");
    var key = state.openKey;
    state.openKey = null;
    if (!key) return;
    var card = document.querySelector('.pcard[data-key="' + key + '"]');
    if (!card) return;
    var hit = card.querySelector(".pcard-hit");
    if (hit) {
      hit.setAttribute("aria-expanded", "false");
      try { hit.focus({ preventScroll: true }); } catch (e) { /* ignore */ }
    }
    card.classList.add("flash");
    setTimeout(function () { card.classList.remove("flash"); }, 1400);
  }

  function focusCard(key) {
    var live = $("pane-live");
    if (live && live.hidden) setTab("live");
    openDetail(key);
  }

  /* ---------------- votes ---------------- */
  function loadVotes() {
    return Promise.all([
      rpc("yp_vote_tally", {}).catch(function () { return []; }),
      rpc("yp_my_votes", { p_voter: CLIENT_ID }).catch(function () { return []; })
    ]).then(function (res) {
      (res[0] || []).forEach(function (r) {
        state.tally[r.issue_key] = { yes: Number(r.yes || 0), no: Number(r.no || 0) };
      });
      (res[1] || []).forEach(function (r) { state.mine[r.issue_key] = r.choice; });
    });
  }

  function paintVote(key, pulse) {
    var nodes = document.querySelectorAll('[data-vote="' + key + '"]');
    Array.prototype.forEach.call(nodes, function (node) {
      node.outerHTML = voteHTML(key);
    });
    Array.prototype.forEach.call(document.querySelectorAll('[data-vote-st="' + key + '"]'), function (el) {
      el.innerHTML = voteStatHTML(key);
      if (!pulse) return;
      el.classList.remove("bump");
      void el.offsetWidth;
      el.classList.add("bump");
      setTimeout(function () { el.classList.remove("bump"); }, 900);
    });
  }

  function castVote(key, choice, btn) {
    var prev = state.mine[key];
    if (btn) btn.disabled = true;
    rpc("yp_vote", { p_issue_key: key, p_choice: choice, p_voter: CLIENT_ID })
      .then(function (r) {
        state.tally[key] = { yes: Number(r.yes || 0), no: Number(r.no || 0) };
        state.mine[key] = r.my || choice;
        paintVote(key, true);
        if (prev && prev !== choice) toast("이미 참여한 투표입니다 · " + (prev === "yes" ? "YES" : "NO") + "로 집계됩니다", true);
      })
      .catch(function (e) {
        if (btn) btn.disabled = false;
        toast(errMsg(e), true);
      });
  }

  /* ---------------- issue comments ---------------- */
  function cmtHTML(kind, c) {
    return '' +
      '<div class="cmt" data-cmt-id="' + c.id + '">' +
        '<div class="cmt-top">' +
          '<b>' + esc(c.nickname) + '</b>' +
          '<span class="time">' + esc(relTime(c.created_at)) + '</span>' +
          '<span class="acts">' +
            '<button type="button" class="link-btn" data-report="' + kind + '" data-id="' + c.id + '">신고</button>' +
            '<button type="button" class="link-btn danger" data-del-cmt="' + kind + '" data-id="' + c.id + '">삭제</button>' +
          '</span>' +
        '</div>' +
        '<div class="cmt-body">' + esc(c.body) + '</div>' +
      '</div>';
  }

  function cmtFormHTML(kind, targetId) {
    return '' +
      '<form class="cmt-form" data-cmt-form="' + kind + '" data-target="' + esc(targetId) + '" autocomplete="off">' +
        '<label class="field"><span>닉네임</span>' +
          '<input class="input" name="nick" maxlength="16" placeholder="닉네임" value="' + esc(nick()) + '" required></label>' +
        '<label class="field"><span>비밀번호 4자리</span>' +
          '<input class="input" name="pw" inputmode="numeric" maxlength="4" placeholder="0000" required></label>' +
        '<label class="field full"><span>댓글</span>' +
          '<textarea class="textarea" name="body" rows="2" maxlength="600" placeholder="짧은 의견을 남겨 주세요 (도배·홍보·욕설은 차단됩니다)" required></textarea></label>' +
        '<div class="full cmt-actions">' +
          '<button class="btn primary" type="submit">댓글 등록</button>' +
        '</div>' +
      '</form>';
  }

  function paintCommentList(el, rows) {
    el.innerHTML = rows.length
      ? rows.map(function (c) { return cmtHTML("issue", c); }).join("")
      : '<div class="hintline" style="padding:4px 2px">첫 의견을 남겨 보세요.</div>';
  }

  function renderComments(key) {
    var el = document.querySelector('[data-cmt-list="' + key + '"]');
    if (!el) return;
    var rows = state.cmtRows[key];
    if (rows) { paintCommentList(el, rows); return; }
    el.innerHTML = '<div class="loading">댓글을 불러오는 중…</div>';
    rpc("yp_issue_comments", { p_issue_key: key })
      .then(function (list) {
        list = list || [];
        state.cmtRows[key] = list;
        state.cmtCount[key] = list.length;
        updateCounts(key, list.length);
        var node = document.querySelector('[data-cmt-list="' + key + '"]');
        if (node) paintCommentList(node, list);
      })
      .catch(function () {
        var node = document.querySelector('[data-cmt-list="' + key + '"]');
        if (node) node.innerHTML = '<div class="hintline" style="color:#B45309;padding:4px 2px">댓글을 불러오지 못했습니다.</div>';
      });
  }

  function updateCounts(key, n) {
    Array.prototype.forEach.call(document.querySelectorAll('[data-cmt-count="' + key + '"], [data-cmt-count2="' + key + '"]'), function (el) {
      el.textContent = n;
      var chip = el.closest ? el.closest(".pcard-cmt") : null;
      if (chip) {
        if (n > 0) chip.classList.add("has"); else chip.classList.remove("has");
        chip.setAttribute("aria-label", "이슈 댓글 " + n + "개 보기");
      }
    });
  }

  function submitComment(kind, target, form) {
    var nickVal = form.nick.value.trim();
    var pw = form.pw.value.trim();
    var body = form.body.value.trim();

    if (!nickVal) return toast("닉네임을 입력해 주세요.", true);
    if (!/^[0-9]{4}$/.test(pw)) return toast("비밀번호는 숫자 4자리입니다.", true);
    if (!body) return toast("댓글 내용을 입력해 주세요.", true);
    var bad = findBanned(nickVal + " " + body);
    if (bad) return toast("금칙어('" + bad + "')가 포함되어 등록할 수 없습니다.", true);

    var left = cooldownLeft("comment");
    if (left) return toast("연속 작성은 " + left + "초 뒤에 가능합니다.", true);

    var btn = form.querySelector("button[type=submit]");
    if (btn) { btn.disabled = true; btn.textContent = "등록 중…"; }

    var args = kind === "issue"
      ? { p_issue_key: target, p_nickname: nickVal, p_pw: pw, p_body: body, p_client: CLIENT_ID }
      : { p_post_id: Number(target), p_nickname: nickVal, p_pw: pw, p_body: body, p_client: CLIENT_ID };
    var fn = kind === "issue" ? "yp_add_issue_comment" : "yp_add_post_comment";

    rpc(fn, args).then(function () {
      markWrite("comment");
      setNick(nickVal);
      form.body.value = "";
      toast("댓글을 등록했습니다.");
      if (kind === "issue") {
        state.cmtRows[target] = null;
        renderComments(target);
      } else if (YP.community && YP.community.refreshPost) {
        YP.community.refreshPost(target);
      }
    }).catch(function (e) {
      toast(errMsg(e), true);
    }).then(function () {
      if (btn) { btn.disabled = false; btn.textContent = "댓글 등록"; }
    });
  }

  function deleteComment(kind, id) {
    askPassword("댓글을 삭제합니다. 작성할 때 입력한 4자리 비밀번호를 넣어 주세요.", function (pw) {
      if (!/^[0-9]{4}$/.test(pw)) return toast("비밀번호는 숫자 4자리입니다.", true);
      rpc("yp_delete_comment", { p_id: Number(id), p_pw: pw }).then(function () {
        toast("삭제했습니다.");
        var node = document.querySelector('[data-cmt-id="' + id + '"]');
        var key = node && node.closest("[data-cmt-box]") ? node.closest("[data-cmt-box]").getAttribute("data-cmt-box") : null;
        if (key) { state.cmtRows[key] = null; renderComments(key); }
        if (kind === "post" && YP.community && YP.community.refreshCurrent) YP.community.refreshCurrent();
      }).catch(function (e) { toast(errMsg(e), true); });
    });
  }

  function reportTarget(kind, id) {
    var reported = lsGet("yp_rep_" + kind + "_" + id);
    if (reported) return toast("이미 신고한 항목입니다.", true);
    rpc("yp_report", { p_kind: kind, p_id: Number(id), p_reporter: CLIENT_ID }).then(function (r) {
      lsSet("yp_rep_" + kind + "_" + id, "1");
      toast("신고 접수 · 누적 " + (r && r.report_count ? r.report_count : 1) + "회 (3회 시 자동 숨김)");
      if (r && r.report_count >= 3) {
        var node = document.querySelector('[data-cmt-id="' + id + '"]');
        var key = node && node.closest("[data-cmt-box]") ? node.closest("[data-cmt-box]").getAttribute("data-cmt-box") : null;
        if (key) { state.cmtRows[key] = null; renderComments(key); }
      }
    }).catch(function (e) { toast(errMsg(e), true); });
  }

  /* ---------------- password modal ---------------- */
  var pwCb = null;
  function askPassword(desc, cb) {
    pwCb = cb;
    $("pw-desc").textContent = desc || "작성할 때 입력한 4자리 비밀번호를 넣어 주세요.";
    var input = $("pw-input");
    input.value = "";
    $("pw-ov").classList.add("show");
    setTimeout(function () { input.focus(); }, 60);
  }
  function closeModal(idOf) {
    if (idOf === "detail-ov") { closeDetail(); return; }
    var el = $(idOf);
    if (el) el.classList.remove("show");
  }

  /* ---------------- delegated events ---------------- */
  document.addEventListener("click", function (e) {
    var t = e.target;

    var vote = t.closest ? t.closest(".vbtn") : null;
    if (vote) {
      var wrap = vote.closest("[data-vote]");
      if (wrap) castVote(wrap.getAttribute("data-vote"), vote.getAttribute("data-choice"), vote);
      return;
    }

    var cmtBtn = t.closest ? t.closest("[data-goto-cmt]") : null;
    if (cmtBtn) { openDetail(cmtBtn.getAttribute("data-goto-cmt"), { cmt: true }); return; }

    var top = t.closest ? t.closest(".topline-it") : null;
    if (top) { openDetail(top.getAttribute("data-key")); return; }

    var hot = t.closest ? t.closest("[data-hot-key]") : null;
    if (hot) { focusCard(hot.getAttribute("data-hot-key")); return; }

    var exp = t.closest ? t.closest("[data-expand]") : null;
    if (exp) { openDetail(exp.getAttribute("data-expand")); return; }

    var del = t.closest ? t.closest("[data-del-cmt]") : null;
    if (del) { deleteComment(del.getAttribute("data-del-cmt"), del.getAttribute("data-id")); return; }

    var rep = t.closest ? t.closest("[data-report]") : null;
    if (rep) { reportTarget(rep.getAttribute("data-report"), rep.getAttribute("data-id")); return; }

    var closer = t.closest ? t.closest("[data-close]") : null;
    if (closer) { closeModal(closer.getAttribute("data-close")); return; }

    if (t.id === "pw-ov") closeModal("pw-ov");
    if (t.id === "compose-ov") closeModal("compose-ov");
    if (t.id === "detail-ov") closeDetail();
  });

  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (form && form.matches && form.matches("[data-cmt-form]")) {
      e.preventDefault();
      submitComment(form.getAttribute("data-cmt-form"), form.getAttribute("data-target"), form);
    }
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      if ($("pw-ov") && $("pw-ov").classList.contains("show")) { closeModal("pw-ov"); return; }
      if ($("compose-ov") && $("compose-ov").classList.contains("show")) { closeModal("compose-ov"); return; }
      closeDetail();
    }
    if (e.key === "Enter" && document.activeElement && document.activeElement.id === "pw-input") {
      e.preventDefault();
      $("pw-confirm").click();
    }
    if (e.key === "Enter" || e.key === " ") {
      var a = document.activeElement;
      if (a && a.classList && a.classList.contains("pcard-hit")) {
        e.preventDefault();
        openDetail(a.getAttribute("data-expand"));
      }
    }
  });

  document.addEventListener("DOMContentLoaded", function () {
    var btn = $("pw-confirm");
    if (btn) btn.addEventListener("click", function () {
      var pw = $("pw-input").value.trim();
      closeModal("pw-ov");
      if (pwCb) { var cb = pwCb; pwCb = null; cb(pw); }
    });
  });

  /* ---------------- tabs / routing ---------------- */
  var TABS = ["live", "talk", "guide"];
  function setTab(name, opts) {
    if (TABS.indexOf(name) === -1) name = "live";
    Array.prototype.forEach.call(document.querySelectorAll(".hd-tabs .tab"), function (b) {
      b.setAttribute("aria-selected", b.getAttribute("data-tab") === name ? "true" : "false");
    });
    TABS.forEach(function (t) {
      var pane = $("pane-" + t);
      if (pane) pane.hidden = t !== name;
    });
    if (!opts || !opts.noHash) {
      var hash = "#/" + name;
      if (location.hash !== hash) history.replaceState(null, "", hash);
    }
    if (name === "talk" && YP.community) YP.community.showList();
    window.scrollTo({ top: 0, behavior: "instant" in document.documentElement.style ? "instant" : "auto" });
  }

  function route() {
    var h = (location.hash || "").replace(/^#\/?/, "");
    var parts = h.split("/");
    var name = parts[0] || "live";
    setTab(name, { noHash: true });
    if (name === "talk" && parts[1] === "post" && parts[2] && YP.community) {
      YP.community.openPost(parts[2], { fromHash: true });
    }
  }

  document.addEventListener("click", function (e) {
    var tab = e.target.closest ? e.target.closest(".hd-tabs .tab") : null;
    if (tab) {
      e.preventDefault();
      setTab(tab.getAttribute("data-tab"));
    }
  });

  window.addEventListener("hashchange", route);

  /* ---------------- filtering ---------------- */
  function initFilters() {
    document.addEventListener("click", function (e) {
      var chip = e.target.closest ? e.target.closest("#tabs .chip-btn") : null;
      if (!chip) return;
      Array.prototype.forEach.call(document.querySelectorAll("#tabs .chip-btn"), function (c) {
        c.setAttribute("aria-pressed", c === chip ? "true" : "false");
      });
      state.cat = chip.getAttribute("data-cat");
      state.openKey = null;
      renderCards();
    });

    var input = $("q");
    if (input) {
      var timer;
      input.addEventListener("input", function () {
        var sw = $("hd-search-wrap");
        if (sw) sw.classList.toggle("has-value", !!input.value);
        var live = $("pane-live");
        if (input.value && live && live.hidden) setTab("live");
        clearTimeout(timer);
        timer = setTimeout(function () { state.q = input.value; renderCards(); }, 120);
      });
    }
    var clearBtn = $("q-clear");
    if (clearBtn) clearBtn.addEventListener("click", function () {
      if (input) { input.value = ""; input.focus(); }
      state.q = "";
      var sw = $("hd-search-wrap"); if (sw) sw.classList.remove("has-value");
      renderCards();
    });
  }

  /* ==========================================================================
     실시간 확률 — 브라우저가 Polymarket Gamma API를 직접 조회합니다.
     · 첫 화면은 data/markets.json으로 즉시 그리고(SEO·폴백), 곧바로 실시간 값으로 덮어씁니다.
     · 실패·타임아웃(5초)이면 저장된 값을 조용히 유지합니다(화면을 깨지 않음).
     · Kalshi 공개 API는 교차 출처 요청을 허용하지 않아(Origin 헤더 → 403) 브라우저가
       직접 부를 수 없습니다. Kalshi 항목은 실시간 조회에서 빼고 markets.json 값을 그대로
       쓰미며, 카드의 출처 배지로 그 사실을 밝힙니다(2시간마다 갱신).
     ========================================================================== */
  var LIVE = {
    api: "https://gamma-api.polymarket.com",
    batch: 8,          // 한 요청에 묶는 마켓 수
    timeout: 5000,     // 요청 타임아웃(ms)
    interval: 60000,   // 자동 갱신 주기(ms)
    inFlight: false,
    applied: false,
    lastAt: 0
  };

  function jarr(v) {
    if (Array.isArray(v)) return v;
    if (!v) return [];
    try { var a = JSON.parse(v); return Array.isArray(a) ? a : []; } catch (e) { return []; }
  }
  function numOrNull(v) {
    if (v === null || v === undefined || v === "") return null;
    var n = Number(v);
    return isFinite(n) ? n : null;
  }
  function r1(n) { return Math.round(Number(n) * 10) / 10; }
  function pad2(n) { return (n < 10 ? "0" : "") + n; }

  function liveRef(it) {
    // Kalshi 는 브라우저 교차 출처 요청을 받지 않는다(Origin 헤더가 붙으면 403).
    // 그래서 Kalshi 항목은 60초 실시간 조회 대상에서 빼고 data/markets.json 값을 유지한다.
    if (it.source && it.source !== "Polymarket") return null;
    if (it.mid) return { key: "id", val: String(it.mid) };
    if (it.condition_id) return { key: "condition_ids", val: String(it.condition_id) };
    if (it.slug) return { key: "slug", val: String(it.slug) };
    return null;
  }

  function fetchLiveBatch(refKey, ids, path) {
    var url = LIVE.api + (path || "/markets") + "?" + ids.map(function (v) {
      return refKey + "=" + encodeURIComponent(v);
    }).join("&") + "&_=" + Math.floor(Date.now() / LIVE.interval);
    var ctrl = (typeof AbortController !== "undefined") ? new AbortController() : null;
    var timer = ctrl ? setTimeout(function () { try { ctrl.abort(); } catch (e) { /* ignore */ } }, LIVE.timeout) : null;
    return fetch(url, { cache: "no-store", signal: ctrl ? ctrl.signal : undefined })
      .then(function (r) {
        if (timer) clearTimeout(timer);
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      }, function (e) {
        if (timer) clearTimeout(timer);
        throw e;
      })
      .then(function (data) {
        if (Array.isArray(data)) return data;                              // /markets
        if (data && Array.isArray(data.markets)) return data.markets;      // /markets/keyset
        return [];
      });
  }

  /* /markets 응답이 비거나 실패하면 keyset 경로로 한 번 더 시도합니다. */
  function fetchLiveWithFallback(refKey, ids) {
    var viaKeyset = function () { return fetchLiveBatch(refKey, ids, "/markets/keyset"); };
    return fetchLiveBatch(refKey, ids, "/markets").then(function (rows) {
      return (rows && rows.length) ? rows : viaKeyset();
    }, viaKeyset);
  }

  function setNum(obj, field, value) {
    if (value === null) return false;
    if (Number(obj[field]) === Number(value)) return false;
    obj[field] = value;
    return true;
  }

  /* Gamma 응답 한 건을 카드 데이터에 반영합니다. 반영 여부를 돌려줍니다. */
  function applyLiveRow(row) {
    if (!row || row.id === undefined || row.id === null) return false;
    var it = state.byMid[String(row.id)];
    if (!it) return false;
    var prices = jarr(row.outcomePrices);
    var yes = numOrNull(prices[0]);
    if (yes === null || yes < 0 || yes > 1) return false;

    var changed = false;
    if (setNum(it, "yes", r1(yes * 100))) changed = true;
    if (setNum(it, "no", r1((1 - yes) * 100))) changed = true;

    var d1 = numOrNull(row.oneDayPriceChange);
    if (d1 !== null && setNum(it, "change_24h", r1(d1 * 100))) changed = true;
    var d7 = numOrNull(row.oneWeekPriceChange);
    if (d7 !== null && setNum(it, "change_1w", r1(d7 * 100))) changed = true;

    var v24 = numOrNull(row.volume24hr);
    if (v24 !== null && setNum(it, "volume_24h", Math.round(v24))) changed = true;
    var vt = numOrNull(row.volumeNum !== undefined && row.volumeNum !== null ? row.volumeNum : row.volume);
    if (vt !== null && setNum(it, "volume_total", Math.round(vt))) changed = true;
    var lq = numOrNull(row.liquidityNum !== undefined && row.liquidityNum !== null ? row.liquidityNum : row.liquidity);
    if (lq !== null && setNum(it, "liquidity", Math.round(lq))) changed = true;

    it.live = true;
    return changed;
  }

  /* 상세 모달은 숫자 노드만 바꿔 다시 그립니다 — 댓글 폼에 입력 중인 내용을 지키기 위해서입니다. */
  function patchDetail() {
    if (!state.openKey) return;
    var ov = $("detail-ov");
    if (!ov || !ov.classList.contains("show")) return;
    var it = itemByKey(state.openKey);
    var body = $("dd-body");
    if (!it || !body) return;

    var pv = body.querySelector(".dd-pv");
    if (pv) pv.innerHTML = pct(it.yes) + "<small>%</small>";
    var side = body.querySelector(".dd-prob .side b");
    if (side) side.textContent = pct(it.no) + "%";
    var gauge = body.querySelector(".dd-glob .gauge i");
    if (gauge) gauge.style.width = Math.max(2, Math.min(100, Number(it.yes) || 0)) + "%";

    var facts = body.querySelectorAll(".dd-facts li b");
    if (facts[0]) facts[0].textContent = money(it.volume_24h);
    if (facts[1]) facts[1].textContent = money(it.volume_total);
    if (facts[3]) {
      var w = Number(it.change_1w) || 0;
      facts[3].className = w < 0 ? "down" : "up";
      facts[3].textContent = (w > 0 ? "+" : "") + pct(w) + "p";
    }
    var delta = $("dd-delta");
    if (delta) delta.innerHTML = deltaChip(it.change_24h);
  }

  function paintLive(redraw) {
    setLiveStamp(new Date());
    if (!redraw) return;
    renderFeatured();
    renderCards();
    renderSidebar();
    patchDetail();
  }

  /* 실시간 재조회 — 성공하면 true. 실패해도 예외를 던지지 않습니다(기존 값 유지). */
  function liveRefresh(manual) {
    if (LIVE.inFlight) return Promise.resolve(false);
    var items = (state.data && state.data.items) || [];
    if (!items.length) return Promise.resolve(false);

    var groups = { id: [], condition_ids: [], slug: [] };
    items.forEach(function (it) {
      var ref = liveRef(it);
      if (ref && groups[ref.key]) groups[ref.key].push(ref.val);
    });

    var jobs = [];
    Object.keys(groups).forEach(function (key) {
      var list = groups[key];
      for (var i = 0; i < list.length; i += LIVE.batch) {
        jobs.push(fetchLiveWithFallback(key, list.slice(i, i + LIVE.batch)));
      }
    });
    if (!jobs.length) return Promise.resolve(false);

    LIVE.inFlight = true;
    return Promise.all(jobs.map(function (p) {
      return p.then(function (rows) { return rows; }, function (e) { return e; });
    })).then(function (results) {
      var rowsOk = 0, applied = 0, changed = 0, failed = 0, matchedIds = {};
      results.forEach(function (res) {
        if (!Array.isArray(res)) { failed += 1; return; }
        rowsOk += 1;
        res.forEach(function (row) {
          if (!row || row.id === undefined) return;
          matchedIds[String(row.id)] = 1;
          if (!state.byMid[String(row.id)]) return;
          applied += 1;
          if (applyLiveRow(row)) changed += 1;
        });
      });
      if (!applied) throw new Error("no-live-match");
      LIVE.applied = true;
      LIVE.lastAt = Date.now();
      if (failed) console.warn("[live] 일부 요청 실패(" + failed + "/" + jobs.length + ")" + (manual ? " · 수동 갱신" : ""));
      paintLive(changed > 0);
      return true;
    }).catch(function (e) {
      console.warn("[live] 실시간 갱신 실패 — 저장된 값을 유지합니다:", e && (e.name === "AbortError" ? "timeout" : e.message));
      return false;
    }).then(function (ok) {
      LIVE.inFlight = false;
      return ok;
    });
  }

  var liveTimer = null, liveVisibilityBound = false;
  function startLiveTimer() {
    if (liveTimer) clearInterval(liveTimer);
    liveTimer = setInterval(function () {
      if (document.visibilityState && document.visibilityState !== "visible") return;
      if (!state.data) return;
      liveRefresh();          // 조용한 백그라운드 갱신
    }, LIVE.interval);
    if (liveVisibilityBound) return;
    liveVisibilityBound = true;
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState !== "visible") return;
      if (!state.data) return;
      if (Date.now() - LIVE.lastAt >= LIVE.interval) liveRefresh();
    });
  }

  /* ---------------- load ---------------- */
  function setStamp(label) {
    var full = $("updated-at"), short = $("updated-at-short");
    var stamp = $("stamp"), lab = $("stamp-label");
    var text = String(label || "—");
    var m = text.match(/(\d+)월 (\d+)일 (\d+:\d+)/);
    var compact = m ? m[1] + "." + m[2] + " " + m[3] : text.replace(/\s*\(KST\)/, "");
    if (stamp) stamp.classList.remove("live");
    if (lab) lab.textContent = "갱신";
    if (full) full.textContent = m ? (m[1] + "월 " + m[2] + "일 " + m[3]) : text;
    if (short) short.textContent = compact;
  }

  /* 실시간 반영 성공 — 🟢 실시간 HH:MM:SS */
  function setLiveStamp(d) {
    var stamp = $("stamp"), lab = $("stamp-label");
    var full = $("updated-at"), short = $("updated-at-short");
    var hh = pad2(d.getHours()) + ":" + pad2(d.getMinutes());
    var ss = ":" + pad2(d.getSeconds());
    if (stamp) {
      stamp.classList.add("live");
      stamp.setAttribute("title", "브라우저가 글로벌 공개 시장 API에서 직접 받은 시각 (KST) · 1분마다 자동 갱신");
    }
    if (lab) lab.textContent = "🟢 실시간";
    if (full) full.textContent = hh + ss;
    if (short) short.textContent = "🟢 " + hh;
  }

  function indexItems(data) {
    var map = {}, items = (data && data.items) || [];
    for (var i = 0; i < items.length; i++) {
      if (items[i].mid) map[String(items[i].mid)] = items[i];
    }
    state.byMid = map;
  }

  function loadData(fresh) {
    var url = "data/markets.json?t=" + Date.now();
    return fetch(url, fresh ? { cache: "no-store" } : { cache: "no-cache" })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (data) {
        state.data = data;
        indexItems(data);
        if (!LIVE.applied) setStamp(data.updated_label || data.updated_at || "—");
        var pill = $("pill-count");
        if (pill) pill.textContent = "오늘의 이슈 " + (data.count || (data.items || []).length) + "개";
        renderFeatured();
        renderCards();
        renderSidebar();
        // 상세가 열려 있으면 최신 숫자로 다시 그립니다(스크롤 위치 유지).
        if (state.openKey && $("detail-ov").classList.contains("show")) {
          var body = $("dd-body");
          var top = body.scrollTop;
          var it = itemByKey(state.openKey);
          if (it) {
            body.innerHTML = detailHTML(it);
            body.scrollTop = top;
            renderComments(state.openKey);
          }
        }
        return data;
      });
  }

  function loadCommentCounts() {
    var keys = ((state.data && state.data.items) || []).map(function (i) { return i.key; });
    if (!keys.length) return Promise.resolve();
    return rpc("yp_comment_counts", { p_keys: keys }).then(function (rows) {
      (rows || []).forEach(function (r) { state.cmtCount[r.issue_key] = Number(r.n || 0); });
      Object.keys(state.cmtCount).forEach(function (k) { updateCounts(k, state.cmtCount[k]); });
      Array.prototype.forEach.call(document.querySelectorAll("[data-cmt-count]"), function (el) {
        var k = el.getAttribute("data-cmt-count");
        el.textContent = state.cmtCount[k] || 0;
        var chip = el.closest ? el.closest(".pcard-cmt") : null;
        if (chip) {
          if (state.cmtCount[k] > 0) chip.classList.add("has"); else chip.classList.remove("has");
          chip.setAttribute("aria-label", "이슈 댓글 " + (state.cmtCount[k] || 0) + "개 보기");
        }
      });
    }).catch(function () { /* counts are optional */ });
  }

  /* ---------------- 조회수(클릭수) ---------------- */
  function ssGet(k) { try { return sessionStorage.getItem(k); } catch (e) { return null; } }
  function ssSet(k, v) { try { sessionStorage.setItem(k, v); } catch (e) { /* ignore */ } }
  function ssDel(k) { try { sessionStorage.removeItem(k); } catch (e) { /* ignore */ } }

  function paintIssueViews() {
    Array.prototype.forEach.call(document.querySelectorAll("[data-issue-views]"), function (el) {
      var k = el.getAttribute("data-issue-views");
      el.textContent = state.issueViews[k] || 0;
    });
  }

  function loadIssueViews() {
    var keys = ((state.data && state.data.items) || []).map(function (i) { return i.key; });
    if (!keys.length) return Promise.resolve();
    return rpc("yp_issue_view_counts", { p_keys: keys }).then(function (rows) {
      (rows || []).forEach(function (r) {
        state.issueViews[r.issue_key] = Number(r.views || 0);
      });
      paintIssueViews();
    }).catch(function () { /* 조회수는 없어도 화면은 동작 */ });
  }

  // 이슈 카드를 열 때 1회만 집계(같은 브라우저·같은 날 1회, 서버에서도 중복 차단)
  function trackIssueView(key) {
    var mark = "yp_v_issue_" + key;
    if (ssGet(mark)) return;
    ssSet(mark, "1");
    rpc("yp_track_view", { p_kind: "issue", p_key: String(key), p_viewer: CLIENT_ID })
      .then(function (r) {
        if (!r) return;
        state.issueViews[key] = Number(r.views || 0);
        paintIssueViews();
      })
      .catch(function () { ssDel(mark); });
  }

  function errorState(err) {
    console.error(err);
    setStamp("불러오기 실패");
    var grid = $("grid");
    if (grid) {
      grid.innerHTML = '<div class="empty"><b>데이터를 불러오지 못했습니다.</b>잠시 후 새로고침(↻)을 눌러 주세요.<br>' +
        '<span style="font-size:11.5px;color:#8B95A1">' + esc(err && err.message ? err.message : "") + '</span></div>';
    }
    var c = $("count"); if (c) c.textContent = "—";
  }

  function init() {
    initFilters();
    route();

    var btn = $("refresh");
    if (btn) {
      btn.addEventListener("click", function () {
        if (btn.classList.contains("spinning")) return;
        btn.classList.add("spinning");
        // 페이지를 다시 불러오지 않고 실시간 API만 재조회합니다.
        liveRefresh(true).then(function (ok) {
          if (ok) { toast("실시간 확률로 갱신했습니다"); return; }
          // 실패해도 이미 보고 있는 값을 바꾸지 않습니다(더 낡은 저장값으로 되돌리지 않음).
          toast("실시간 연결이 지연되고 있어요 · 표시된 값을 그대로 둡니다", true);
        }).then(function () { btn.classList.remove("spinning"); });
      });
    }

    loadData(false)
      .then(function () {
        return loadVotes().then(function () {
          renderFeatured(); renderCards(); return loadCommentCounts();
        }).then(loadIssueViews);
      })
      .then(function () {
        liveRefresh();     // 저장 데이터로 그린 직후, 곧바로 실시간 값으로 덮어씁니다.
        startLiveTimer();
      })
      .catch(errorState);
  }

  /* ---------------- exports ---------------- */
  YP.util = {
    esc: esc, rpc: rpc, api: api, toast: toast, errMsg: errMsg, relTime: relTime,
    clientId: CLIENT_ID, askPassword: askPassword, closeModal: closeModal,
    findBanned: findBanned, cooldownLeft: cooldownLeft, markWrite: markWrite,
    setTab: setTab, cmtFormHTML: cmtFormHTML, cmtHTML: cmtHTML,
    nick: nick, setNick: setNick,
    loadComments: renderComments, submitComment: submitComment,
    deleteComment: deleteComment, reportTarget: reportTarget, uid: uid
  };
  YP.state = state;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
