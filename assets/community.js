/* ==========================================================================
   예측판 YECHEUKPAN — 자유 수다방 (게시판)
   ·글 목록(말머리 필터·공지 고정), 글쓰기 모달, 글 상세·댓글, 사이드 최신글
   ========================================================================== */
(function () {
  "use strict";

  var YP = window.YP || {};
  var U = YP.util;
  if (!U) return;
  var $ = function (id) { return document.getElementById(id); };
  var esc = U.esc;

  var CAT = { rate: "금리·증시", coin: "코인", ai: "AI·빅테크", free: "자유" };
  var TAGCLS = { rate: "economy", coin: "crypto", ai: "ai", free: "free", notice: "free" };
  var state = { cat: "all", posts: [], currentId: null };

  function isNotice(p) { return p && (p.nickname === "예측판" || String(p.id) === "1"); }

  function dateText(iso) {
    var d = new Date(iso);
    if (isNaN(d.getTime())) return "";
    var now = new Date();
    var same = d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth() && d.getDate() === now.getDate();
    if (same) {
      var hh = d.getHours(), mm = d.getMinutes();
      return (hh < 10 ? "0" + hh : hh) + ":" + (mm < 10 ? "0" + mm : mm);
    }
    return (d.getMonth() + 1) + "." + d.getDate();
  }

  /* ---------------- list ---------------- */
  function rowHTML(p) {
    var n = Number(p.comment_count || 0);
    var notice = isNotice(p);
    return '' +
      '<div class="post-row' + (notice ? " notice" : "") + '" data-post-id="' + p.id + '" role="button" tabindex="0">' +
        (notice
          ? '<span class="notice-tag">공지</span>'
          : '<span class="tag ' + (TAGCLS[p.category] || "free") + '">' + esc(CAT[p.category] || "자유") + '</span>') +
        '<span class="title">' + esc(p.title) + (n ? ' <span class="cmt-n">[' + n + ']</span>' : '') + '</span>' +
        '<span class="by">' + esc(p.nickname) + '</span>' +
        '<span class="date">' + esc(dateText(p.created_at)) + '</span>' +
        '<span class="meta-m">' + esc(p.nickname) + ' · ' + esc(U.relTime(p.created_at)) + '</span>' +
      '</div>';
  }

  function renderList() {
    var list = $("post-list");
    if (!list) return;
    var all = state.posts || [];
    var notices = all.filter(isNotice);
    var rows = all.filter(function (p) { return !isNotice(p); });
    if (state.cat !== "all") {
      rows = rows.filter(function (p) { return p.category === state.cat; });
    }
    rows = notices.concat(rows);
    list.innerHTML = rows.length
      ? rows.map(rowHTML).join("")
      : '<div class="empty"><b>아직 이 말머리에 글이 없습니다.</b>첫 글을 남겨 보세요.</div>';
    var c = $("talk-count");
    if (c) c.textContent = rows.length + "개 글";
  }

  function loadList() {
    var list = $("post-list");
    if (list && !state.posts.length) list.innerHTML = '<div class="loading">불러오는 중…</div>';
    return U.rpc("yp_list_posts", { p_category: "all", p_limit: 80 })
      .then(function (rows) {
        state.posts = rows || [];
        renderList();
      })
      .catch(function (e) {
        if (list) list.innerHTML = '<div class="empty"><b>글 목록을 불러오지 못했습니다.</b>' +
          '<span style="font-size:11.5px;color:#8B95A1">' + esc(U.errMsg(e)) + '</span></div>';
        var c = $("talk-count"); if (c) c.textContent = "—";
      });
  }

  /* ---------------- sidebar: 최신글 ---------------- */
  function renderSidebar(posts) {
    var el = $("side-talk");
    if (!el) return;
    var rows = (posts || []).slice(0, 5);
    if (!rows.length) {
      el.innerHTML = '<li class="empty">아직 글이 없습니다. 첫 글을 남겨 보세요.</li>';
      return;
    }
    el.innerHTML = rows.map(function (p) {
      var n = Number(p.comment_count || 0);
      return '<li data-side-post="' + p.id + '" title="' + esc(p.title) + '">' +
          '<span class="ti">' + esc(p.title) + (n ? ' <b>[' + n + ']</b>' : '') + '</span>' +
          '<span class="mt"><i>' + esc(isNotice(p) ? "공지" : (CAT[p.category] || "자유")) + '</i>' +
            esc(p.nickname) + ' · ' + esc(U.relTime(p.created_at)) + '</span>' +
        '</li>';
    }).join("");
  }

  function loadSidebar() {
    return U.rpc("yp_list_posts", { p_category: "all", p_limit: 5 })
      .then(renderSidebar)
      .catch(function () {
        var el = $("side-talk");
        if (el) el.innerHTML = '<li class="empty">최신글을 불러오지 못했습니다.</li>';
      });
  }

  function showList() {
    var lv = $("talk-list-view"), pv = $("talk-view");
    if (!lv || !pv) return;
    lv.hidden = false; pv.hidden = true; pv.innerHTML = "";
    state.currentId = null;
    if (!state.posts.length) loadList();
  }

  /* ---------------- post view ---------------- */
  function postHTML(data) {
    var p = data.post, cs = data.comments || [];
    return '' +
      '<div class="board post-view">' +
        '<button class="crumb" type="button" data-back-list>← 자유 수다방 목록</button>' +
        '<div class="pv-head">' +
          '<div class="line1">' +
            (isNotice(p) ? '<span class="notice-tag">공지</span>'
                         : '<span class="tag ' + (TAGCLS[p.category] || "free") + '">' + esc(CAT[p.category] || "자유") + '</span>') +
          '</div>' +
          '<h2>' + esc(p.title) + '</h2>' +
          '<div class="pv-meta"><b>' + esc(p.nickname) + '</b><span>' + esc(U.relTime(p.created_at)) + '</span>' +
            '<span style="margin-left:auto;display:flex;gap:9px">' +
              '<button type="button" class="link-btn" data-report="post" data-id="' + p.id + '">신고</button>' +
              (isNotice(p) ? "" : '<button type="button" class="link-btn danger" data-del-post="' + p.id + '">삭제</button>') +
            '</span>' +
          '</div>' +
        '</div>' +
        '<div class="pv-body">' + esc(p.body) + '</div>' +
        '<div class="cmt-box">' +
          '<div class="cmt-head">💬 댓글 <span class="n">' + cs.length + '</span></div>' +
          '<div class="cmt-list">' +
            (cs.length ? cs.map(function (c) { return U.cmtHTML("post", c); }).join("")
                       : '<div class="hintline" style="padding:4px 2px">첫 댓글을 남겨 보세요.</div>') +
          '</div>' +
          U.cmtFormHTML("post", p.id) +
        '</div>' +
      '</div>';
  }

  function openPost(id, opts) {
    var lv = $("talk-list-view"), pv = $("talk-view");
    if (!pv) return;
    U.setTab("talk", { noHash: !!(opts && opts.fromHash) });
    lv.hidden = true; pv.hidden = false;
    pv.innerHTML = '<div class="loading">글을 불러오는 중…</div>';
    state.currentId = String(id);
    U.rpc("yp_get_post", { p_id: Number(id) })
      .then(function (data) {
        if (!data || !data.post) {
          pv.innerHTML = '<div class="empty"><b>삭제되었거나 없는 글입니다.</b>' +
            '<button class="btn" type="button" data-back-list style="margin-top:10px">목록으로</button></div>';
          return;
        }
        pv.innerHTML = postHTML(data);
        if (!opts || !opts.fromHash) {
          var hash = "#/talk/post/" + id;
          if (location.hash !== hash) history.replaceState(null, "", hash);
        }
        window.scrollTo({ top: 0, behavior: "auto" });
      })
      .catch(function (e) {
        pv.innerHTML = '<div class="empty"><b>글을 불러오지 못했습니다.</b>' +
          '<span style="font-size:11.5px;color:#8B95A1">' + esc(U.errMsg(e)) + '</span></div>';
      });
  }

  function refreshPost(id) {
    if (String(state.currentId) !== String(id)) return;
    openPost(id, { fromHash: true });
  }

  function deletePost(id) {
    U.askPassword("글을 삭제합니다. 작성할 때 입력한 4자리 비밀번호를 넣어 주세요.", function (pw) {
      if (!/^[0-9]{4}$/.test(pw)) return U.toast("비밀번호는 숫자 4자리입니다.", true);
      U.rpc("yp_delete_post", { p_id: Number(id), p_pw: pw }).then(function () {
        U.toast("글을 삭제했습니다.");
        state.posts = [];
        state.currentId = null;
        history.replaceState(null, "", "#/talk");
        showList();
        loadList();
        loadSidebar();
      }).catch(function (e) { U.toast(U.errMsg(e), true); });
    });
  }

  /* ---------------- compose ---------------- */
  function openCompose() {
    var ov = $("compose-ov");
    if (!ov) return;
    var nickInput = $("pf-nick");
    if (nickInput && !nickInput.value) nickInput.value = U.nick ? U.nick() : "";
    ov.classList.add("show");
    setTimeout(function () { var t = $("pf-title"); if (t) t.focus(); }, 60);
  }

  function submitPost(e) {
    e.preventDefault();
    var cat = $("pf-category").value;
    var nick = $("pf-nick").value.trim();
    var title = $("pf-title").value.trim();
    var body = $("pf-body").value.trim();
    var pw = $("pf-pw").value.trim();

    if (!nick) return U.toast("닉네임을 입력해 주세요.", true);
    if (!/^[0-9]{4}$/.test(pw)) return U.toast("비밀번호는 숫자 4자리입니다.", true);
    if (title.length < 2) return U.toast("제목을 2자 이상 입력해 주세요.", true);
    if (!body) return U.toast("본문을 입력해 주세요.", true);

    var bad = U.findBanned(nick + " " + title + " " + body);
    if (bad) return U.toast("금칙어('" + bad + "')가 포함되어 등록할 수 없습니다.", true);

    var left = U.cooldownLeft("post");
    if (left) return U.toast("연속 작성은 " + left + "초 뒤에 가능합니다.", true);

    var btn = $("pf-submit");
    btn.disabled = true; btn.textContent = "등록 중…";

    U.rpc("yp_add_post", {
      p_category: cat, p_title: title, p_body: body,
      p_nickname: nick, p_pw: pw, p_client: U.clientId
    }).then(function (r) {
      U.markWrite("post");
      if (U.setNick) U.setNick(nick);
      U.closeModal("compose-ov");
      $("compose-form").reset();
      U.toast("글을 등록했습니다.");
      state.posts = [];
      state.cat = "all";
      Array.prototype.forEach.call(document.querySelectorAll("#talk-tabs .chip-btn"), function (c) {
        c.setAttribute("aria-pressed", c.getAttribute("data-cat") === "all" ? "true" : "false");
      });
      showList();
      loadList();
      loadSidebar();
      if (r && r.id) openPost(r.id);
    }).catch(function (err) {
      U.toast(U.errMsg(err), true);
    }).then(function () {
      btn.disabled = false; btn.textContent = "등록";
    });
  }

  /* ---------------- events ---------------- */
  document.addEventListener("click", function (e) {
    var t = e.target;

    if (t.closest && t.closest("#btn-write")) { openCompose(); return; }

    var back = t.closest ? t.closest("[data-back-list]") : null;
    if (back) {
      history.replaceState(null, "", "#/talk");
      showList();
      return;
    }

    var del = t.closest ? t.closest("[data-del-post]") : null;
    if (del) { deletePost(del.getAttribute("data-del-post")); return; }

    var side = t.closest ? t.closest("[data-side-post]") : null;
    if (side) { openPost(side.getAttribute("data-side-post")); return; }

    var chip = t.closest ? t.closest("#talk-tabs .chip-btn") : null;
    if (chip) {
      Array.prototype.forEach.call(document.querySelectorAll("#talk-tabs .chip-btn"), function (c) {
        c.setAttribute("aria-pressed", c === chip ? "true" : "false");
      });
      state.cat = chip.getAttribute("data-cat");
      renderList();
      return;
    }

    var row = t.closest ? t.closest(".post-row") : null;
    if (row) { openPost(row.getAttribute("data-post-id")); return; }
  });

  document.addEventListener("keydown", function (e) {
    var row = document.activeElement;
    if (row && row.classList && row.classList.contains("post-row") && (e.key === "Enter" || e.key === " ")) {
      e.preventDefault();
      openPost(row.getAttribute("data-post-id"));
    }
  });

  document.addEventListener("submit", function (e) {
    if (e.target && e.target.id === "compose-form") submitPost(e);
  });

  function refreshCurrent() {
    if (state.currentId) openPost(state.currentId, { fromHash: true });
  }

  YP.community = {
    showList: showList,
    openPost: openPost,
    refreshPost: refreshPost,
    refreshCurrent: refreshCurrent,
    loadList: loadList,
    loadSidebar: loadSidebar
  };

  /* 목록 밖(예: 첫 화면)에서도 사이드 최신글을 먼저 채웁니다. */
  loadSidebar();

  /* app.js가 먼저 실행되면 수다방 초기화를 놓칠 수 있으므로 여기서 한 번 더 확인합니다. */
  var pane = $("pane-talk");
  if (pane && !pane.hidden) {
    var m = (location.hash || "").match(/^#\/talk\/post\/(\d+)/);
    if (m) openPost(m[1], { fromHash: true });
    else showList();
  }
})();
