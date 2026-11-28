/* ==========================================================================
   예측판 YECHEUKPAN — 퍼가는 확률 카드(임베드) 코드 복사
   · 이슈 상세 페이지(정적 HTML)와 홈 상세 모달(app.js)의 [data-copy-embed] 버튼이 같이 쓴다.
   · 클립보드 API 가 막힌 브라우저(구형·비보안 컨텍스트)에서는 코드를 선택해 주어
     사용자가 Ctrl+C 로 복사할 수 있게 한다.
   ========================================================================== */
(function () {
  "use strict";

  function textOf(el) {
    return String(el ? el.textContent || "" : "").replace(/^\s+|\s+$/g, "");
  }

  // 복사 실패 시: 코드를 화면에서 선택해 준다(수동 복사 안내)
  function selectNode(el) {
    try {
      var r = document.createRange();
      r.selectNodeContents(el);
      var s = window.getSelection();
      s.removeAllRanges();
      s.addRange(r);
    } catch (e) { /* ignore */ }
  }

  function legacyCopy(txt, done, fail) {
    var ta = null;
    try {
      ta = document.createElement("textarea");
      ta.value = txt;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.top = "-1000px";
      ta.style.left = "0";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      ta.setSelectionRange(0, txt.length);
      var ok = document.execCommand && document.execCommand("copy");
      document.body.removeChild(ta);
      if (ok) { done(); return; }
    } catch (e) {
      if (ta && ta.parentNode) ta.parentNode.removeChild(ta);
    }
    fail();
  }

  function feedback(btn, label, ms) {
    if (btn.getAttribute("data-busy") === "1") return;
    var orig = btn.getAttribute("data-label");
    if (!orig) { orig = btn.textContent; btn.setAttribute("data-label", orig); }
    btn.setAttribute("data-busy", "1");
    btn.textContent = label;
    setTimeout(function () {
      btn.textContent = orig;
      btn.removeAttribute("data-busy");
    }, ms || 1800);
  }

  document.addEventListener("click", function (ev) {
    var t = ev.target;
    var btn = t && t.closest ? t.closest("[data-copy-embed]") : null;
    if (!btn) return;
    var box = document.getElementById(btn.getAttribute("data-copy-embed"));
    if (!box) return;
    ev.preventDefault();

    var txt = textOf(box);
    if (!txt) return;

    function done() { feedback(btn, "복사됨 ✓", 1800); }
    function fail() {
      feedback(btn, "아래 코드를 직접 선택해 복사하세요", 3000);
      selectNode(box);
    }

    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(txt).then(done, function () {
        legacyCopy(txt, done, fail);
      });
    } else {
      legacyCopy(txt, done, fail);
    }
  });
})();
