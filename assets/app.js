/* ==========================================================================
   예측판 YECHEUKPAN — core
   ·Supabase REST/RPC 연결, 이슈 데이터 렌더, 한줄 투표, 이슈 댓글
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
    "토토", "사설토토", "배팅사이트", "먹튀", "바카라", "카지노", "슬롯", "파워볼",
    "스포츠토토", "프로토", "온라인카지노", "레퍼럴", "추천인", "리퍼럴", "수익인증",
    "리딩방", "텔레그램", "오픈채팅", "카톡주세요", "카톡문의", "디엠주세요", "대리입금",
    "환전", "선입금", "고정수익", "원금보장", "100%수익", "폭리",
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
    return call().catch(function (e) {
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
    cat: "all",
    q: "",
    open: {},
    tally: {},      // issue_key -> {yes, no}
    mine: {},       // issue_key -> 'yes'|'no'
    cmtCount: {},   // issue_key -> n
    cmtLoaded: {}   // issue_key -> bool
  };

  var CAT_LABEL = { economy: "경제·금리", crypto: "코인·금융", ai: "AI·테크", global: "글로벌" };

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
  function deltaText(v) {
    var n = Math.round(v * 10) / 10;
    if (n >= 0.5) return '<span class="delta-badge up">▲ ' + pct(n) + "p</span>";
    if (n <= -0.5) return '<span class="delta-badge down">▼ ' + pct(Math.abs(n)) + "p</span>";
    return '<span class="delta-badge flat">변동 없음</span>';
  }

  /* ---------------- vote row ---------------- */
  function voteHTML(key) {
    var t = state.tally[key] || { yes: 0, no: 0 };
    var tot = (t.yes || 0) + (t.no || 0);
    var yp = tot ? Math.round((t.yes / tot) * 100) : 0;
    var np = tot ? 100 - yp : 0;
    var mine = state.mine[key] || "";
    return '' +
      '<div class="vote" data-vote="' + esc(key) + '">' +
        '<button type="button" class="vote-btn yes' + (mine === "yes" ? " mine" : "") + '" data-choice="yes" aria-pressed="' + (mine === "yes") + '">' +
          '<span class="row"><span>👍 YES 간다</span>' +
          '<span class="pct">' + (tot ? yp + "%" : "0%") + '</span></span>' +
          '<span class="cnt">' + (tot ? t.yes + "명 참여" : "첫 투표") + '</span>' +
        '</button>' +
        '<button type="button" class="vote-btn no' + (mine === "no" ? " mine" : "") + '" data-choice="no" aria-pressed="' + (mine === "no") + '">' +
          '<span class="row"><span>👎 NO 꺾인다</span>' +
          '<span class="pct">' + (tot ? np + "%" : "0%") + '</span></span>' +
          '<span class="cnt">' + (tot ? t.no + "명 참여" : "첫 투표") + '</span>' +
        '</button>' +
        '<div class="vote-note" style="grid-column:1/-1">' +
          (tot ? "예측판 여론 " + tot + "명 참여" + (mine ? " · 내 선택 " + (mine === "yes" ? "YES" : "NO") : "")
               : "시장 확률과 별개로, 당신의 판단은?") +
        '</div>' +
      '</div>';
  }

  /* ---------------- featured ---------------- */
  function renderFeatured() {
    var el = $("featured");
    if (!el) return;
    var items = (state.data.items || []).filter(function (it) { return it.featured; })
      .sort(function (a, b) { return (a.featured_rank || 9) - (b.featured_rank || 9); });
    if (!items.length) { el.innerHTML = ""; return; }

    el.innerHTML = items.map(function (it) {
      return '' +
        '<article class="feature" data-rank="' + it.featured_rank + '" data-key="' + esc(it.key) + '" tabindex="0" role="button" aria-label="' + esc(it.title) + ' 해설 열기">' +
          '<div class="feature-top">' +
            '<span class="feature-rank">TOP ' + it.featured_rank + '</span>' +
            '<span class="feature-cat">' + esc(CAT_LABEL[it.category] || "기타") + '</span>' +
          '</div>' +
          '<h3>' + esc(it.title) + '</h3>' +
          '<div class="feature-num">' +
            '<div class="big">' + pct(it.yes) + '<span>%</span></div>' +
            '<div class="side">' +
              '<span class="k">시장 YES 확률</span>' +
              '<span class="v">NO ' + pct(it.no) + '%</span>' +
            '</div>' +
          '</div>' +
          '<div class="bar"><i style="width:' + Math.max(2, Math.min(100, it.yes)) + '%"></i></div>' +
          voteHTML(it.key) +
        '</article>';
    }).join("");

    Array.prototype.forEach.call(el.querySelectorAll(".feature"), function (node) {
      node.addEventListener("click", function (e) {
        if (e.target.closest("[data-vote]")) return;
        focusCard(node.getAttribute("data-key"));
      });
      node.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); focusCard(node.getAttribute("data-key")); }
      });
    });
  }

  /* ---------------- cards ---------------- */
  function cardHTML(it) {
    var yes = it.yes;
    var n = state.cmtCount[it.key] || 0;
    return '' +
      '<article class="card" data-key="' + esc(it.key) + '" data-cat="' + esc(it.category) + '">' +
        '<div class="card-head">' +
          '<span class="chip ' + esc(it.category) + '">' + esc(CAT_LABEL[it.category] || "기타") + '</span>' +
          deltaText(it.change_24h) +
        '</div>' +
        '<h3 class="card-title">' + esc(it.title) + '</h3>' +
        '<div class="prob">' +
          '<span class="yes"><span class="lab">시장 YES</span><span class="val">' + pct(yes) + '<small>%</small></span></span>' +
          '<span class="no"><span class="val">' + pct(it.no) + '<small>%</small></span><span class="lab">NO</span></span>' +
        '</div>' +
        '<div class="bar"><i style="width:' + Math.max(2, Math.min(100, yes)) + '%"></i></div>' +
        '<div class="meta">' +
          '<span>24시간 <b>' + money(it.volume_24h) + '</b></span>' +
          '<span>누적 <b>' + money(it.volume_total) + '</b></span>' +
          '<span><b>' + esc(shortDate(it.end_date)) + '</b> 마감' + (daysLeft(it.end_date) ? " · " + daysLeft(it.end_date) : "") + '</span>' +
        '</div>' +
        voteHTML(it.key) +
        '<div class="card-foot">' +
          '<button type="button" class="foot-btn" data-cmt-toggle="' + esc(it.key) + '">' +
            '💬 댓글 <span class="n" data-cmt-count="' + esc(it.key) + '">' + n + '</span>' +
          '</button>' +
          '<button type="button" class="foot-btn right" data-expand="' + esc(it.key) + '" aria-expanded="false">' +
            '<span>배경 해설</span>' +
            '<span class="chev" aria-hidden="true">' +
              '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>' +
            '</span>' +
          '</button>' +
        '</div>' +
        '<div class="detail">' +
          '<div class="block"><h4>이슈 배경</h4><p>' + esc(it.explain) + '</p></div>' +
          '<div class="block"><h4>관전 포인트</h4><p>' + esc(it.watch) + '</p></div>' +
          '<div class="block origin"><h4>원문 질문</h4><p>' + esc(it.question) + '</p></div>' +
          '<div class="src">출처: Polymarket 공개 데이터' + (it.auto ? " · 자동 선별 항목" : "") +
            ' · 최근 1주 변동 ' + (it.change_1w > 0 ? "+" : "") + pct(it.change_1w) + 'p</div>' +
          '<div class="cmt-box" data-cmt-box="' + esc(it.key) + '">' +
            '<div class="cmt-head">💬 이슈 댓글 <span class="n" data-cmt-count2="' + esc(it.key) + '">' + n + '</span></div>' +
            '<div class="cmt-list" data-cmt-list="' + esc(it.key) + '"><div class="loading">댓글을 불러오는 중…</div></div>' +
            cmtFormHTML("issue", it.key) +
          '</div>' +
        '</div>' +
      '</article>';
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
        '<div class="full" style="display:flex;justify-content:flex-end;gap:6px">' +
          '<button class="btn primary" type="submit" style="padding:7px 14px">댓글 등록</button>' +
        '</div>' +
      '</form>';
  }

  function renderCards() {
    var el = $("grid");
    if (!el) return;
    var q = state.q.trim().toLowerCase();
    var items = (state.data.items || []).filter(function (it) {
      if (state.cat !== "all" && it.category !== state.cat) return false;
      if (!q) return true;
      var hay = (it.title + " " + (it.question || "") + " " + (it.event_title || "") + " " + (it.option || "")).toLowerCase();
      return hay.indexOf(q) !== -1;
    });

    el.innerHTML = items.length
      ? items.map(cardHTML).join("")
      : '<div class="empty">조건에 맞는 이슈가 없습니다.<br>다른 키워드로 검색하거나 전체 탭을 눌러 보세요.</div>';

    $("count").textContent = items.length + "개 이슈";
    updateTabCounts();
    // 열려 있던 카드 복원
    Object.keys(state.open).forEach(function (k) {
      if (!state.open[k]) return;
      var card = el.querySelector('[data-key="' + k + '"]');
      if (card) { card.classList.add("open"); state.cmtLoaded[k] = false; loadComments(k); }
    });
  }

  function updateTabCounts() {
    var items = state.data.items || [];
    Array.prototype.forEach.call(document.querySelectorAll("#tabs .chip-btn"), function (tab) {
      var cat = tab.getAttribute("data-cat");
      var n = cat === "all" ? items.length : items.filter(function (i) { return i.category === cat; }).length;
      var base = tab.getAttribute("data-label") || tab.textContent.replace(/\s\d+$/, "");
      tab.setAttribute("data-label", base);
      tab.innerHTML = esc(base) + ' <span class="n">' + n + '</span>';
    });
  }

  function focusCard(key) {
    var sel = '[data-key="' + String(key).replace(/"/g, '\\"') + '"]';
    var card = $("grid") ? $("grid").querySelector(sel) : null;
    if (!card && (state.cat !== "all" || state.q)) {
      state.cat = "all"; state.q = "";
      var input = $("q"); if (input) input.value = "";
      Array.prototype.forEach.call(document.querySelectorAll("#tabs .chip-btn"), function (t) {
        t.setAttribute("aria-pressed", t.getAttribute("data-cat") === "all" ? "true" : "false");
      });
      renderCards();
      card = $("grid").querySelector(sel);
    }
    if (!card) return;
    card.scrollIntoView({ behavior: "smooth", block: "center" });
    if (!card.classList.contains("open")) toggleCard(card, true);
    card.style.borderColor = "rgba(76,141,255,.9)";
    setTimeout(function () { card.style.borderColor = ""; }, 1500);
  }

  function toggleCard(card, forceOpen) {
    var key = card.getAttribute("data-key");
    var open = forceOpen === true ? true : card.classList.toggle("open");
    if (forceOpen === false) open = false;
    state.open[key] = open;
    var btn = card.querySelector("[data-expand]");
    if (btn) btn.setAttribute("aria-expanded", open ? "true" : "false");
    if (open) loadComments(key);
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

  function paintVote(key) {
    var nodes = document.querySelectorAll('[data-vote="' + key + '"]');
    Array.prototype.forEach.call(nodes, function (node) {
      node.outerHTML = voteHTML(key);
    });
  }

  function castVote(key, choice, btn) {
    var prev = state.mine[key];
    if (btn) btn.disabled = true;
    rpc("yp_vote", { p_issue_key: key, p_choice: choice, p_voter: CLIENT_ID })
      .then(function (r) {
        state.tally[key] = { yes: Number(r.yes || 0), no: Number(r.no || 0) };
        state.mine[key] = r.my || choice;
        paintVote(key);
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

  function loadComments(key) {
    if (state.cmtLoaded[key]) return Promise.resolve();
    state.cmtLoaded[key] = true;
    var list = document.querySelector('[data-cmt-list="' + key + '"]');
    return rpc("yp_issue_comments", { p_issue_key: key })
      .then(function (rows) {
        rows = rows || [];
        state.cmtCount[key] = rows.length;
        updateCounts(key, rows.length);
        var el = document.querySelector('[data-cmt-list="' + key + '"]');
        if (!el) return;
        el.innerHTML = rows.length
          ? rows.map(function (c) { return cmtHTML("issue", c); }).join("")
          : '<div class="hintline" style="padding:4px 2px">첫 의견을 남겨 보세요.</div>';
      })
      .catch(function () {
        state.cmtLoaded[key] = false;
        var el2 = document.querySelector('[data-cmt-list="' + key + '"]');
        if (el2) el2.innerHTML = '<div class="hintline" style="color:#ffc78a">댓글을 불러오지 못했습니다.</div>';
      });
  }

  function updateCounts(key, n) {
    Array.prototype.forEach.call(document.querySelectorAll('[data-cmt-count="' + key + '"], [data-cmt-count2="' + key + '"]'), function (el) {
      el.textContent = n;
    });
  }

  function submitComment(kind, target, form) {
    var nick = form.nick.value.trim();
    var pw = form.pw.value.trim();
    var body = form.body.value.trim();

    if (!nick) return toast("닉네임을 입력해 주세요.", true);
    if (!/^[0-9]{4}$/.test(pw)) return toast("비밀번호는 숫자 4자리입니다.", true);
    if (!body) return toast("댓글 내용을 입력해 주세요.", true);
    var bad = findBanned(nick + " " + body);
    if (bad) return toast("금칙어('" + bad + "')가 포함되어 등록할 수 없습니다.", true);

    var left = cooldownLeft("comment");
    if (left) return toast("연속 작성은 " + left + "초 뒤에 가능합니다.", true);

    var btn = form.querySelector("button[type=submit]");
    if (btn) { btn.disabled = true; btn.textContent = "등록 중…"; }

    var args = kind === "issue"
      ? { p_issue_key: target, p_nickname: nick, p_pw: pw, p_body: body, p_client: CLIENT_ID }
      : { p_post_id: Number(target), p_nickname: nick, p_pw: pw, p_body: body, p_client: CLIENT_ID };
    var fn = kind === "issue" ? "yp_add_issue_comment" : "yp_add_post_comment";

    rpc(fn, args).then(function () {
      markWrite("comment");
      setNick(nick);
      form.body.value = "";
      toast("댓글을 등록했습니다.");
      if (kind === "issue") {
        state.cmtLoaded[target] = false;
        loadComments(target);
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
        if (node) node.remove();
        if (key) { state.cmtLoaded[key] = false; loadComments(key); }
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
        if (node) node.remove();
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
    var el = $(idOf);
    if (el) el.classList.remove("show");
  }

  /* ---------------- delegated events ---------------- */
  document.addEventListener("click", function (e) {
    var t = e.target;

    var vote = t.closest ? t.closest(".vote-btn") : null;
    if (vote) {
      var wrap = vote.closest("[data-vote]");
      if (wrap) castVote(wrap.getAttribute("data-vote"), vote.getAttribute("data-choice"), vote);
      return;
    }

    var exp = t.closest ? t.closest("[data-expand]") : null;
    if (exp) {
      var card = exp.closest(".card");
      if (card) toggleCard(card);
      return;
    }

    var ct = t.closest ? t.closest("[data-cmt-toggle]") : null;
    if (ct) {
      var c2 = ct.closest(".card");
      if (c2) toggleCard(c2, true);
      return;
    }

    var titleEl = t.closest ? t.closest(".card-title") : null;
    if (titleEl) {
      var c3 = titleEl.closest(".card");
      if (c3) toggleCard(c3);
      return;
    }

    var del = t.closest ? t.closest("[data-del-cmt]") : null;
    if (del) { deleteComment(del.getAttribute("data-del-cmt"), del.getAttribute("data-id")); return; }

    var rep = t.closest ? t.closest("[data-report]") : null;
    if (rep) { reportTarget(rep.getAttribute("data-report"), rep.getAttribute("data-id")); return; }

    var closer = t.closest ? t.closest("[data-close]") : null;
    if (closer) { closeModal(closer.getAttribute("data-close")); return; }

    if (t.id === "pw-ov") closeModal("pw-ov");
    if (t.id === "compose-ov") closeModal("compose-ov");
  });

  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (form && form.matches && form.matches("[data-cmt-form]")) {
      e.preventDefault();
      submitComment(form.getAttribute("data-cmt-form"), form.getAttribute("data-target"), form);
    }
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") { closeModal("pw-ov"); closeModal("compose-ov"); }
    if (e.key === "Enter" && document.activeElement && document.activeElement.id === "pw-input") {
      e.preventDefault();
      $("pw-confirm").click();
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
    Array.prototype.forEach.call(document.querySelectorAll(".tabbar .tab"), function (b) {
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
    var tab = e.target.closest ? e.target.closest(".tabbar .tab") : null;
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
      renderCards();
    });

    var input = $("q");
    if (input) {
      var timer;
      input.addEventListener("input", function () {
        clearTimeout(timer);
        timer = setTimeout(function () { state.q = input.value; renderCards(); }, 120);
      });
    }
  }

  /* ---------------- load ---------------- */
  function setStamp(label) {
    var full = $("updated-at"), short = $("updated-at-short");
    var text = String(label || "—");
    var m = text.match(/(\d+)월 (\d+)일 (\d+:\d+)/);
    var compact = m ? m[1] + "." + m[2] + " " + m[3] : text.replace(/\s*\(KST\)/, "");
    if (full) full.textContent = text;
    if (short) short.textContent = compact;
  }

  function loadData(fresh) {
    var url = "data/markets.json?t=" + Date.now();
    return fetch(url, fresh ? { cache: "no-store" } : { cache: "no-cache" })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (data) {
        state.data = data;
        setStamp(data.updated_label || data.updated_at || "—");
        var pill = $("pill-count");
        if (pill) pill.textContent = "오늘의 이슈 " + (data.count || (data.items || []).length) + "개";
        renderFeatured();
        renderCards();
        return data;
      });
  }

  function loadCommentCounts() {
    var keys = (state.data.items || []).map(function (i) { return i.key; });
    if (!keys.length) return Promise.resolve();
    return rpc("yp_comment_counts", { p_keys: keys }).then(function (rows) {
      (rows || []).forEach(function (r) { state.cmtCount[r.issue_key] = Number(r.n || 0); });
      Object.keys(state.cmtCount).forEach(function (k) { updateCounts(k, state.cmtCount[k]); });
      Array.prototype.forEach.call(document.querySelectorAll("[data-cmt-count]"), function (el) {
        var k = el.getAttribute("data-cmt-count");
        el.textContent = state.cmtCount[k] || 0;
      });
    }).catch(function () { /* counts are optional */ });
  }

  function errorState(err) {
    console.error(err);
    setStamp("불러오기 실패");
    var grid = $("grid");
    if (grid) {
      grid.innerHTML = '<div class="empty">데이터를 불러오지 못했습니다.<br>잠시 후 새로고침(↻)을 눌러 주세요.<br>' +
        '<span style="font-size:11.5px;color:#6d7c94">' + esc(err && err.message ? err.message : "") + '</span></div>';
    }
    var c = $("count"); if (c) c.textContent = "—";
  }

  function init() {
    initFilters();
    route();

    var btn = $("refresh");
    if (btn) {
      btn.addEventListener("click", function () {
        btn.classList.add("spinning");
        Promise.all([loadData(true), loadVotes(), loadCommentCounts()])
          .then(function () { toast("최신 데이터로 갱신했습니다"); })
          .catch(function (e) { toast("갱신 실패 · 잠시 후 다시 시도해 주세요", true); errorState(e); })
          .then(function () { btn.classList.remove("spinning"); });
      });
    }

    loadData(false)
      .then(function () {
        return loadVotes().then(function () {
          renderFeatured(); renderCards(); return loadCommentCounts();
        });
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
    loadComments: loadComments, submitComment: submitComment,
    deleteComment: deleteComment, reportTarget: reportTarget, uid: uid
  };
  YP.state = state;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
