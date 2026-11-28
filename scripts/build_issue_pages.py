#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
예측판(YECHEUKPAN) — 이슈별 정적 SEO 페이지 + sitemap.xml 생성 스크립트
=====================================================================

data/markets.json 을 읽어 이슈마다 검색 유입용 정적 페이지를 만든다.

  issues/{slug}.html   이슈 상세 페이지 (제목·설명·canonical·OG·GA4·AdSense·해설·내부 링크)
  issues/index.html    이슈 전체 목록(허브) — 크롤러가 모든 상세 페이지로 들어오는 경로
  sitemap.xml          홈·안내 페이지 + 이슈 허브 + 모든 이슈 페이지

- 표준 라이브러리만 사용한다(GitHub Actions에서 추가 설치 없이 실행).
- 사라진 이슈의 HTML 파일은 지우지 않고, 같은 이슈의 새 주소(또는 /issues/ 목록)로
  넘기는 안내 페이지로 바꾼다. 검색·블로그·X에 남은 구 주소가 404가 되지 않게 한다.
- 베팅·도박 유도 표현은 쓰지 않는다. 공개 확률·해설·내부 링크만 담는다.

사용법:  python3 scripts/build_issue_pages.py [--dry-run]
"""

from __future__ import annotations

import argparse
import html
import json
import pathlib
import re
import sys
from datetime import date, datetime

ROOT = pathlib.Path(__file__).resolve().parents[1]

# 사생활·성추문·가십성 스캔들 필터(scripts/content_filter.py) — 수집 스크립트와 같은 기준.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from content_filter import blocked_reason  # noqa: E402
DATA_PATH = ROOT / "data" / "markets.json"
ISSUES_DIR = ROOT / "issues"
OG_DIR = ROOT / "og"
INDEX_PATH = ROOT / "index.html"
SITEMAP_PATH = ROOT / "sitemap.xml"

# 이슈별 OG 이미지 생성기(scripts/og_image.py) — Pillow·Pretendard 가 없으면 조용히 건너뛴다.
try:
    import og_image  # noqa: E402
except Exception:  # noqa: BLE001
    og_image = None

SITE = "https://yecheukpan.kr"
SITE_NAME = "예측판 YECHEUKPAN"

# 출처별 갱신 주기 — Kalshi(2시간 저장값)와 Polymarket(1분 실시간)을 섞지 않는다.
FRESH_TXT = {"Kalshi": "2시간마다 갱신", "Polymarket": "1분마다 실시간 갱신"}
GA_ID = "G-D0QGKN71ZE"
ADSENSE = "ca-pub-3318185141094112"

CAT_ICON = {"economy": "📉", "crypto": "🪙", "ai": "🤖", "global": "🌍"}
CAT_LABEL = {"economy": "경제·금리", "crypto": "코인·금융", "ai": "AI·테크", "global": "글로벌"}
CAT_ORDER = ["economy", "crypto", "ai", "global"]

E = html.escape


# ---------------------------------------------------------------------------
# 값 포맷
# ---------------------------------------------------------------------------
def money(n) -> str:
    """app.js의 money()와 같은 표기($9.3M)."""
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "—"
    if n >= 1e9:
        return "$" + ("%.1f" % (n / 1e9) if n >= 1e10 else "%.2f" % (n / 1e9)).rstrip("0").rstrip(".") + "B"
    if n >= 1e6:
        return "$" + ("%.1f" % (n / 1e6) if n >= 1e7 else "%.2f" % (n / 1e6)).rstrip("0").rstrip(".") + "M"
    if n >= 1e3:
        return "$" + ("%.1f" % (n / 1e3)).rstrip("0").rstrip(".") + "K"
    return "$" + str(round(n))


def vol_txt(n, it: dict) -> str:
    """거래량 표기 — Kalshi 는 계약 수, Polymarket 은 금액."""
    if (it or {}).get("source") == "Kalshi":
        try:
            n = float(n)
        except (TypeError, ValueError):
            return "—"
        if n >= 1e8:
            return f"{n / 1e8:.1f}".rstrip("0").rstrip(".") + "억계약"
        if n >= 1e4:
            return f"{n / 1e4:.1f}".rstrip("0").rstrip(".") + "만계약"
        return f"{round(n):,}계약"
    return money(n)


def source_of(it: dict) -> str:
    return (it or {}).get("source") or "Polymarket"


def src_tag(it: dict) -> str:
    """카드·상세에 붙는 출처 배지."""
    s = source_of(it)
    return f'<span class="src-tag {"kalshi" if s == "Kalshi" else "pm"}">{E(s)}</span>'


def num1(v) -> str:
    try:
        return "%.1f" % float(v)
    except (TypeError, ValueError):
        return "—"


def delta_txt(v) -> str:
    """+3.0%p / -1.2%p / 데이터 없음"""
    if v is None:
        return "데이터 없음"
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "데이터 없음"
    if abs(v) < 0.05:
        return "변동 없음"
    return ("+" if v > 0 else "−") + num1(abs(v)) + "%p"


def delta_cls(v) -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "na"
    if v > 0.05:
        return "up"
    if v < -0.05:
        return "down"
    return "flat"


def end_kr(iso: str) -> str:
    """2026-12-09 → 2026년 12월 9일"""
    if not iso:
        return "—"
    try:
        d = date.fromisoformat(iso[:10])
    except ValueError:
        return iso
    return f"{d.year}년 {d.month}월 {d.day}일"


def days_left(iso: str) -> str:
    if not iso:
        return ""
    try:
        d = date.fromisoformat(iso[:10])
    except ValueError:
        return ""
    diff = (d - date.today()).days
    if diff < 0:
        return "마감"
    if diff == 0:
        return "오늘 마감"
    return f"D-{diff}"


def slug_of(item: dict) -> str:
    """이슈 key → 파일명. app.js의 issueSlug()와 같은 규칙."""
    raw = str(item.get("key") or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    if not s:
        s = "issue-" + str(item.get("mid") or "0")
    return s


def pretty_title(t: str) -> str:
    """표시용 제목 정리 — 중복 공백·앞뒤 기호 제거."""
    t = re.sub(r"\s+", " ", str(t or "")).strip()
    return t


# ---------------------------------------------------------------------------
# 사라진 이슈 페이지 → 404 대신 "새 주소로 이동" 안내
# ---------------------------------------------------------------------------
# 2시간마다 자동 갱신하면서 마켓이 빠지거나 slug가 바뀌면 구 주소가 사라진다.
# 그때 파일을 지우면 검색엔진·블로그·X에 남은 링크가 404가 되므로,
# 같은 이슈의 새 주소(없으면 /issues/ 목록)로 넘기는 얇은 안내 페이지를 남긴다.
STUB_TARGET_META = 'name="yp-redirect-target"'
STUB_LABEL_META = 'name="yp-redirect-label"'
MAX_REDIRECT_STUBS = 200


def stub_target_of(doc: str) -> str | None:
    """이미 안내 페이지면 넘길 대상 파일명("" = 목록)을, 아니면 None."""
    m = re.search(r'<meta name="yp-redirect-target" content="([^"]*)"', doc)
    return m.group(1) if m else None


def stub_label_of(doc: str) -> str:
    m = re.search(r'<meta name="yp-redirect-label" content="([^"]*)"', doc)
    return pretty_title(html.unescape(m.group(1))) if m else ""


def issue_title_of(doc: str) -> str:
    """이슈 상세 페이지의 <title>{제목} — {확률}% 실시간 확률 | 예측판</title>에서 제목만."""
    m = re.search(r"<title>(.*?)</title>", doc, re.S)
    if not m:
        return ""
    t = html.unescape(m.group(1)).strip()
    m2 = re.match(r"^(.*?)\s+—\s+[\d.]+%\s*실시간 확률\s*\|\s*예측판$", t, re.S)
    if m2:
        return pretty_title(m2.group(1))
    return pretty_title(t.split(" | ")[0].split(" — ")[0])


def render_redirect_stub(target: str, label: str) -> str:
    """구 주소를 살리는 안내 페이지. target은 issues/ 안의 파일명(""이면 목록)."""
    href = f"/issues/{target}" if target else "/issues/"
    label = pretty_title(label)
    title = (f"{label} — 주소 안내 | 예측판" if label else "주소 안내 | 예측판")
    if target:
        lead = "이 이슈 페이지는 주소가 바뀌었습니다. 잠시 후 새 주소로 자동 이동합니다."
        btn = "새 주소로 이동"
        extra = '<a class="btn ghost" href="/issues/">이슈 전체 목록</a>'
    else:
        lead = ("이 이슈는 예측판 목록에서 내려갔습니다. 최신 확률과 다른 이슈는 "
                "이슈 전체 목록에서 확인하시면 됩니다. 잠시 후 자동으로 이동합니다.")
        btn = "이슈 전체 보기"
        extra = ""
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{E(title)}</title>
<meta name="robots" content="noindex,follow">
<meta name="theme-color" content="#F3F5F8">
<meta name="yp-redirect-target" content="{E(target)}">
<meta name="yp-redirect-label" content="{E(label)}">
<link rel="canonical" href="{SITE}{href}">
<meta http-equiv="refresh" content="0; url={href}">
<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;800&display=swap">
<link rel="stylesheet" href="/assets/style.css?v=20261128emb">
<!-- Google tag (gtag.js) — GA4 -->
<script async src="https://www.googletagmanager.com/gtag/js?id={GA_ID}"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('js', new Date());
  gtag('config', '{GA_ID}');
</script>
</head>
<body>
<header class="site-header">
  <div class="wrap hd-top">
    <a class="logo" href="/" aria-label="예측판 홈">
      <span class="logo-mark" aria-hidden="true">예</span>
      <span class="logo-txt"><b>예측판</b><i>YECHEUKPAN</i></span>
    </a>
    <nav class="hd-tabs" aria-label="예측판 메뉴">
      <a class="tab" href="/#/live">오늘의 확률</a>
      <a class="tab" href="/#/talk">자유 수다방</a>
      <a class="tab" href="/#/guide">이슈 해설</a>
    </nav>
  </div>
</header>
<main class="wrap">
  <article class="page">
    <div class="page-in">
    <h1>이슈 페이지가 이동했습니다</h1>
    <p class="page-meta">{E(label) if label else "이슈 전체 목록"}</p>
    <p>{lead}</p>
    <p style="margin-top:16px;display:flex;gap:8px;flex-wrap:wrap">
      <a class="btn primary" href="{href}">{btn}</a>
      <a class="btn" href="/#/live">실시간 예측판</a>
      {extra}
    </p>
    </div>
  </article>
</main>
<script>
(function () {{
  var dest = {json.dumps(href)};
  var moved = false;
  function go() {{ if (!moved) {{ moved = true; location.replace(dest); }} }}
  try {{
    gtag("event", "issue_page_redirect", {{
      from_path: location.pathname, to_path: dest,
      event_callback: go, event_timeout: 1200
    }});
  }} catch (e) {{}}
  setTimeout(go, 1200);
}})();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# 머리말 / 꼬리말 (모든 페이지가 같은 화이트·딥네이비 톤을 쓴다)
# ---------------------------------------------------------------------------
def head(title: str, desc: str, canonical: str, og_type: str = "article",
         extra_ld: str = "", published: str = "", og_image: str = "",
         og_alt: str = "") -> str:
    # 이슈 페이지는 이슈 전용 OG 이미지(1200×630)를 미리보기 카드로 쓴다.
    if og_image:
        og_img = (
            f'<meta property="og:image" content="{E(og_image)}">\n'
            f'<meta property="og:image:width" content="1200">\n'
            f'<meta property="og:image:height" content="630">\n'
            f'<meta property="og:image:type" content="image/png">\n'
            f'<meta property="og:image:alt" content="{E(og_alt or title)}">\n'
            '<meta name="twitter:card" content="summary_large_image">\n'
            f'<meta name="twitter:image" content="{E(og_image)}">\n'
            f'<meta name="twitter:image:alt" content="{E(og_alt or title)}">'
        )
    else:
        og_img = ('<meta name="twitter:card" content="summary">')
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{E(title)}</title>
<meta name="description" content="{E(desc)}">
<link rel="canonical" href="{E(canonical)}">
<meta name="robots" content="index,follow,max-image-preview:large">
<meta name="author" content="예측판">
<meta name="theme-color" content="#F3F5F8">
<meta name="google-site-verification" content="ThA5brScxksH1QMuJqSvX_Ec9ifUwkPqka6uS9mI-PQ" />
<meta name="naver-site-verification" content="cc59fdda09927e7f07209eee2b067ef3844a3022" />
<meta property="og:type" content="{E(og_type)}">
<meta property="og:site_name" content="{SITE_NAME}">
<meta property="og:locale" content="ko_KR">
<meta property="og:title" content="{E(title)}">
<meta property="og:description" content="{E(desc)}">
<meta property="og:url" content="{E(canonical)}">
{og_img}
<meta name="twitter:title" content="{E(title)}">
<meta name="twitter:description" content="{E(desc)}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;800&display=swap">
<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="/assets/style.css?v=20261128emb">
<script src="/assets/embed.js?v=20261128emb" defer></script>
<script type="application/ld+json">
{extra_ld}
</script>
<!-- Google AdSense -->
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={ADSENSE}" crossorigin="anonymous"></script>
<!-- Google tag (gtag.js) — GA4 -->
<script async src="https://www.googletagmanager.com/gtag/js?id={GA_ID}"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('js', new Date());
  gtag('config', '{GA_ID}');
</script>
</head>
<body>

<header class="site-header">
  <div class="wrap hd-top">
    <a class="logo" href="/" aria-label="예측판 홈">
      <span class="logo-mark" aria-hidden="true">예</span>
      <span class="logo-txt"><b>예측판</b><i>YECHEUKPAN</i></span>
    </a>
    <nav class="hd-tabs" aria-label="예측판 메뉴">
      <a class="tab" href="/#/live">오늘의 확률</a>
      <a class="tab" href="/#/talk">자유 수다방</a>
      <a class="tab" href="/#/guide">이슈 해설</a>
    </nav>
    <div class="hd-right">
      <a class="btn sm" href="/issues/">이슈 전체</a>
    </div>
  </div>
</header>
"""


FOOT = """
<footer class="site-footer">
  <div class="wrap footer-inner">
    <div class="footer-top">
      <div class="footer-brand">
        <a class="logo" href="/">
          <span class="logo-mark" aria-hidden="true">예</span>
          <span class="logo-txt"><b>예측판</b><i>YECHEUKPAN</i></span>
        </a>
        <p>시장이 매긴 확률 데이터를 한국어 해설과 함께 정리하는 정보 커뮤니티입니다.
          베팅·거래·투자 권유를 목적으로 하지 않습니다.</p>
      </div>
      <nav class="footer-links" aria-label="사이트 정보">
        <a href="/">홈</a>
        <a href="/issues/">이슈 전체</a>
        <a href="/about.html">서비스 소개</a>
        <a href="/privacy.html">개인정보처리방침</a>
        <a href="/terms.html">이용약관</a>
        <a href="/disclaimer.html">면책 고지</a>
      </nav>
    </div>
    <div class="footer-legal">
      <p><strong>데이터 출처</strong> · Kalshi(미국 CFTC 인가)·Polymarket 등 글로벌 공개 시장. 확률은 해당 시장 참가자들이 매긴 값이며,
        예측판이 계산하거나 보증하는 값이 아닙니다.</p>
      <p>© 2026 YECHEUKPAN. All rights reserved.</p>
    </div>
  </div>
</footer>

</body>
</html>
"""


# ---------------------------------------------------------------------------
# 본문 조각
# ---------------------------------------------------------------------------
def reading_blocks(it: dict) -> str:
    """숫자를 문장으로 푸는 해설 문단(템플릿 + 실제 수치)."""
    yes = float(it.get("yes") or 0)
    d24, d1w, d1m = it.get("change_24h"), it.get("change_1w"), it.get("change_1m")
    v24 = float(it.get("volume_24h") or 0)
    vtot = float(it.get("volume_total") or 0)
    liq = float(it.get("liquidity") or 0)
    claim = pretty_title(it.get("title", "")).rstrip("?")

    out = []
    out.append(
        f'<p>YES {num1(yes)}%는 시장 참가자들이 <strong>“{E(claim)}”</strong> 쪽에 지금 매기고 있는 '
        f'기대값입니다. 100명 중 {int(round(yes))}명이 그렇게 생각한다는 뜻이 아니라, 이 확률에 값을 매긴 '
        '사람들의 평균적인 기대가 그 정도라는 의미에 가깝습니다. 그래서 이 숫자는 여론조사보다 '
        '<strong>가격</strong>처럼 움직입니다.</p>'
    )

    # 변동 해석
    if d1m is not None and abs(float(d1m)) >= 3:
        one_month = (f'한 달 전과 비교하면 {delta_txt(d1m)} 움직였습니다. '
                     '한 달 단위 변화는 이 이슈를 둘러싼 전제 자체가 바뀌었는지 보여 주는 지표로 읽으면 좋습니다.')
    elif d1m is not None:
        one_month = f'한 달 전과 비교한 변화는 {delta_txt(d1m)}로, 큰 흐름의 전환 없이 비슷한 수준을 유지하고 있습니다.'
    else:
        one_month = '한 달 단위 변화는 제공되는 데이터가 없어 24시간·1주 흐름으로 판단해야 합니다.'

    if abs(float(d24 or 0)) >= 5:
        short = (f'최근 24시간 변동이 {delta_txt(d24)}로 짧은 기간에 크게 움직였습니다. '
                 '이런 경우에는 뉴스나 발표 하나에 반응한 것일 수 있으므로, 하루치 숫자만으로 추세를 단정하기는 이릅니다.')
    elif abs(float(d24 or 0)) >= 1:
        short = (f'최근 24시간 변동은 {delta_txt(d24)}, 1주 변동은 {delta_txt(d1w)}입니다. '
                 '완만한 방향성이라면 기존 기대가 조금씩 조정되는 구간으로 볼 수 있습니다.')
    else:
        short = (f'최근 24시간 변동은 {delta_txt(d24)}, 1주 변동은 {delta_txt(d1w)}로 거의 제자리입니다. '
                 '확률이 굳어져 있다는 뜻이며, 이 상태에서는 새로운 재료가 나올 때 방향이 한 번에 틀어질 수 있습니다.')
    out.append(f'<p>{short} {one_month}</p>')

    # 거래량 해석
    if v24 >= 1_000_000:
        vol = (f'24시간 거래량 {vol_txt(v24, it)}·누적 {vol_txt(vtot, it)}은 이 이슈에 시장의 관심과 자금이 '
               '상당히 실려 있다는 뜻입니다. 참여자가 많을수록 확률이 한두 사람의 움직임에 흔들릴 여지는 줄어듭니다.')
    elif v24 >= 100_000:
        vol = (f'24시간 거래량은 {vol_txt(v24, it)}, 누적 거래량은 {vol_txt(vtot, it)}입니다. '
               '활발한 편이지만 큰 이슈에 비하면 얇은 시장이므로, 확률 1~2%p 차이를 과도하게 해석할 필요는 없습니다.')
    else:
        vol = (f'24시간 거래량은 {vol_txt(v24, it)} 수준으로 적은 편입니다. 거래량이 얇은 마켓은 소수 참가자의 주문만으로도 '
               '확률이 크게 출렁이므로, 숫자의 절대값보다 방향과 흐름 위주로 보시길 권합니다.')
    if liq:
        vol += f' 현재 호가 유동성은 {money(liq)} 수준입니다.'
    out.append(f'<p>{vol}</p>')

    # 마감 해석
    dl = days_left(it.get("end_date", ""))
    if dl.startswith("D-") and dl[2:].isdigit() and int(dl[2:]) <= 14:
        out.append(
            f'<p>마감은 <strong>{E(end_kr(it.get("end_date", "")))}</strong>({E(dl)})로 임박했습니다. '
            '마감이 가까워질수록 확률은 실제 결과에 가까운 값으로 수렴하는 경향이 있지만, '
            '판정 기준(종가인지 장중 터치인지, 어떤 발표를 근거로 하는지)에 따라 같은 사건도 확률이 달라질 수 있습니다. '
            '아래 <strong>원문 질문</strong>을 함께 확인하세요.</p>'
        )
    else:
        out.append(
            f'<p>마감은 <strong>{E(end_kr(it.get("end_date", "")))}</strong>'
            + (f'({E(dl)})' if dl else "") +
            '입니다. 남은 기간이 길수록 새 정보에 따라 확률이 크게 바뀔 수 있으므로, '
            '하루치 변동보다 1주·1개월 흐름을 함께 보는 편이 안정적입니다.</p>'
        )

    return "\n      ".join(out)


def summary_line(it: dict) -> str:
    """페이지 첫머리에 놓는 한 줄 요약(검색 결과 스니펫·본문 도입부 공용)."""
    yes = float(it.get("yes") or 0)
    title = pretty_title(it.get("title", "")).rstrip("?")
    if yes >= 85:
        tone = "시장 참가자 대다수가 사실상 기정사실로 보고 있는 구간입니다"
    elif yes >= 65:
        tone = "가능성 쪽으로 기울었지만 반대 여지도 남아 있는 구간입니다"
    elif yes >= 35:
        tone = "찬반이 팽팽해 방향을 단정하기 어려운 구간입니다"
    elif yes >= 15:
        tone = "가능성은 낮게 보지만 변수는 남아 있는 구간입니다"
    else:
        tone = "시장은 사실상 어렵다고 보고 있는 구간입니다"
    return (f"<strong>{E(title)}</strong> — 시장이 매긴 YES 확률은 <strong>{num1(yes)}%</strong>로, {tone}. "
            f"24시간 {delta_txt(it.get('change_24h'))}, 마감 {E(end_kr(it.get('end_date', '')))}.")


def issue_card_row(it: dict, slug: str) -> str:
    cls = delta_cls(it.get("change_24h"))
    return (
        f'<li><a href="/issues/{slug}.html">'
        f'<span class="ip-r-t">{E(pretty_title(it.get("title", "")))}</span>'
        f'<span class="ip-r-v">{src_tag(it)} {num1(it.get("yes"))}%'
        f'<i class="{cls}">{delta_txt(it.get("change_24h"))}</i></span>'
        f'</a></li>'
    )


# ---------------------------------------------------------------------------
# 퍼가는 확률 카드(임베드) — /embed.html?id={slug}
# ---------------------------------------------------------------------------
def embed_snippet(slug: str, title: str) -> str:
    """블로그에 붙일 <iframe> 한 줄. 높이는 180px 고정, 너비는 넣는 곳에 맞춘다."""
    alt = f"{pretty_title(title)} — 예측판 확률 카드"
    return (
        f'<iframe src="{SITE}/embed.html?id={slug}" width="100%" height="180" '
        'style="max-width:520px;border:0;overflow:hidden" '
        f'title="{E(alt)}" loading="lazy" scrolling="no"></iframe>'
    )


def embed_section(it: dict, slug: str) -> str:
    """이슈 상세 페이지의 '퍼가기' 박스 — 미리보기 + 복사할 코드 + 복사 버튼."""
    title = pretty_title(it.get("title", ""))
    code = embed_snippet(slug, title)
    cid = f"emb-code-{slug}"
    return f"""
      <section class="ip-sec" id="share">
        <h2>이 확률 카드 퍼가기 <span class="ip-cnt">임베드</span></h2>
        <div class="emb-box">
          <div class="emb-prev">
            <iframe src="/embed.html?id={E(slug)}" width="100%" height="180"
                    title="퍼가기 카드 미리보기" loading="lazy" scrolling="no"></iframe>
          </div>
          <p class="emb-desc">블로그·카페·노션처럼 HTML을 붙일 수 있는 곳에 아래 코드를 넣으면
            이 이슈의 YES 확률과 24시간 변동이 담긴 카드가 표시됩니다. 카드를 누르면 예측판의 이 이슈 페이지로 이동합니다.</p>
          <pre class="emb-code" id="{E(cid)}">{html.escape(code)}</pre>
          <p class="emb-actions">
            <button class="btn primary sm" type="button" data-copy-embed="{E(cid)}">임베드 코드 복사</button>
            <a class="btn sm" href="/embed.html?id={E(slug)}" target="_blank" rel="noopener">카드만 열어 보기 ↗</a>
          </p>
          <p class="emb-small">가로는 넣는 곳 너비에 맞춰 늘어나고 세로는 180px 고정입니다.
            카드 숫자는 예측판 홈처럼 Polymarket은 1분마다 실시간으로 갱신되고,
            Kalshi는 공개 API가 브라우저 교차 출처 요청을 허용하지 않아 예측판 저장값(2시간마다 갱신)을 씁니다.
            카드에는 광고·추적 스크립트를 넣지 않습니다.</p>
        </div>
      </section>
"""


def related_pick(items: list, cur: dict, same_cat: int = 4, other_cat: int = 4):
    """같은 카테고리 우선 + 다른 카테고리에서 거래량 순으로 내부 링크 후보를 고른다."""
    rest = [x for x in items if x.get("key") != cur.get("key")]
    same = [x for x in rest if x.get("category") == cur.get("category")]
    same.sort(key=lambda x: -(float(x.get("volume_24h") or 0)))
    others = [x for x in rest if x.get("category") != cur.get("category")]
    others.sort(key=lambda x: -(float(x.get("volume_24h") or 0)))
    picked, seen = [], set()
    for group, limit in ((same, same_cat), (others, other_cat)):
        n = 0
        for x in group:
            if n >= limit:
                break
            k = x.get("key")
            if k in seen:
                continue
            seen.add(k)
            picked.append(x)
            n += 1
    return same[:same_cat], [x for x in picked if x.get("category") != cur.get("category")]


# ---------------------------------------------------------------------------
# 이슈 상세 페이지
# ---------------------------------------------------------------------------
def render_issue(it: dict, items: list, data: dict, slug_map: dict) -> str:
    slug = slug_map[it["key"]]
    cat = it.get("category", "")
    cat_label = CAT_LABEL.get(cat, "기타")
    cat_icon = CAT_ICON.get(cat, "")
    title = pretty_title(it.get("title", ""))
    yes, no = float(it.get("yes") or 0), float(it.get("no") or 0)
    canonical = f"{SITE}/issues/{slug}.html"
    og_url = f"{SITE}/og/{slug}.png"
    updated_day = (data.get("updated_at") or "")[:10]

    page_title = f"{title} — 시장 확률 {num1(yes)}% | 예측판"
    d24, d1w, d1m = it.get("change_24h"), it.get("change_1w"), it.get("change_1m")
    desc = (
        f"{title.rstrip('?').strip()}에 대해 시장 참여자들이 매긴 확률은 현재 {num1(yes)}%입니다. "
        "최근 변화와 배경을 한국어로 해설합니다."
    )

    ld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebPage",
                "@id": canonical,
                "url": canonical,
                "name": page_title,
                "headline": title,
                "description": desc,
                "inLanguage": "ko-KR",
                "dateModified": data.get("updated_at") or "",
                "isPartOf": {"@type": "WebSite", "name": SITE_NAME, "url": SITE + "/"},
                "publisher": {"@type": "Organization", "name": "YECHEUKPAN", "url": SITE + "/"},
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "예측판", "item": SITE + "/"},
                    {"@type": "ListItem", "position": 2, "name": "이슈 전체", "item": SITE + "/issues/"},
                    {"@type": "ListItem", "position": 3, "name": title, "item": canonical},
                ],
            },
        ],
    }

    same, others = related_pick(items, it)
    same_html = "\n        ".join(
        issue_card_row(x, slug_map[x["key"]]) for x in same if x["key"] in slug_map
    ) or "<li>해당 카테고리에 다른 이슈가 없습니다.</li>"
    other_html = "\n        ".join(
        issue_card_row(x, slug_map[x["key"]]) for x in others if x["key"] in slug_map
    ) or "<li>다른 카테고리 이슈를 준비 중입니다.</li>"

    dl = days_left(it.get("end_date", ""))
    auto_note = (
        '<p class="ip-small">이 항목은 공개 마켓 중 거래량이 큰 이슈를 자동으로 골라 실은 것입니다. '
        '해설은 자동으로 생성되며, 원문 질문을 함께 확인하시길 권합니다.</p>'
        if it.get("auto") else ""
    )

    src = source_of(it)
    fresh = FRESH_TXT.get(src, FRESH_TXT["Polymarket"])
    fresh_cls = "kalshi" if src == "Kalshi" else "pm"

    body = f"""
<main class="wrap">
  <nav class="ip-crumb" aria-label="페이지 위치">
    <a href="/">예측판 홈</a><span aria-hidden="true">›</span><a href="/issues/">이슈 전체</a>
    <span aria-hidden="true">›</span><em>{E(cat_label)}</em>
  </nav>

  <article class="page ip-page">
    <div class="page-in">

      <header class="ip-head">
        <span class="ctag {E(cat)}">{cat_icon} {E(cat_label)}</span>
        {src_tag(it)}
        <h1>{E(title)}</h1>
        <p class="ip-meta-line">
          <span>마감 <b>{E(end_kr(it.get("end_date", "")))}</b>{f' · {E(dl)}' if dl else ''}</span>
          <span>데이터 기준 <b>{E(data.get("updated_label") or "")}</b></span>
          <span>출처 <b>{E(src)} 공개 데이터</b> · {E(fresh)}</span>
        </p>
      </header>

      <div class="ip-prob">
        <div class="ip-prob-main">
          <span class="ip-lb">🌐 글로벌 시장 확률 · YES</span>
          <span class="fresh-tag {fresh_cls}">{E(fresh)}</span>
          <div class="ip-num">{num1(yes)}<small>%</small></div>
          <span class="ip-no">NO <b>{num1(no)}%</b></span>
        </div>
        <div class="ip-prob-side">
          <span class="gauge ip-gauge"><i style="width:{max(2, min(100, yes)):.1f}%"></i></span>
          <ul class="ip-deltas">
            <li><span>24시간</span><b class="{delta_cls(d24)}">{delta_txt(d24)}</b></li>
            <li><span>1주</span><b class="{delta_cls(d1w)}">{delta_txt(d1w)}</b></li>
            <li><span>1개월</span><b class="{delta_cls(d1m)}">{delta_txt(d1m)}</b></li>
          </ul>
        </div>
      </div>

      <p class="ip-summary">{summary_line(it)}</p>

      <table class="ip-facts">
        <caption>거래·마감 정보</caption>
        <tbody>
          <tr><th>24시간 거래량</th><td>{vol_txt(it.get("volume_24h"), it)}</td>
              <th>누적 거래량</th><td>{vol_txt(it.get("volume_total"), it)}</td></tr>
          <tr><th>{'미결제 약정' if source_of(it) == 'Kalshi' else '호가 유동성'}</th>
              <td>{f"{int(it.get('open_interest') or 0):,}계약" if source_of(it) == 'Kalshi' else money(it.get("liquidity"))}</td>
              <th>마감일</th><td>{E(end_kr(it.get("end_date", "")))} <span class="ip-mut">(미국 동부시간 기준)</span></td></tr>
        </tbody>
      </table>

      <section class="ip-sec">
        <h2>이슈 배경</h2>
        <p>{E(it.get("explain") or "공개 마켓 데이터를 바탕으로 정리한 이슈입니다.")}</p>
      </section>

      <section class="ip-sec">
        <h2>관전 포인트</h2>
        <p>{E(it.get("watch") or "확률 변화 폭과 거래량을 함께 보면 시장 참가자들의 기대가 얼마나 빠르게 바뀌는지 가늠할 수 있습니다.")}</p>
        {auto_note}
      </section>

      <section class="ip-sec">
        <h2>이 확률을 읽는 법</h2>
        {reading_blocks(it)}
      </section>

      <section class="ip-sec">
        <h2>원문 질문 · 판정 기준</h2>
        <blockquote class="ip-quote">
          <p lang="en">{E(it.get("question") or "")}</p>
          {f'<p class="ip-opt">선택지 · {E(it.get("option"))}</p>' if it.get("option") else ''}
        </blockquote>
        <p class="ip-small">마켓의 판정 기준(종가 기준인지 장중 터치 기준인지, 어떤 기관 발표를 근거로 하는지)에 따라
          같은 사건도 확률이 달라질 수 있습니다. 숫자를 비교할 때는 원문 질문과 마감일을 함께 확인하세요.</p>
      </section>

{embed_section(it, slug)}

      <section class="ip-sec">
        <h2>{E(cat_label)} 다른 이슈</h2>
        <ul class="ip-related">
        {same_html}
        </ul>
      </section>

      <section class="ip-sec">
        <h2>함께 보면 좋은 이슈</h2>
        <ul class="ip-related">
        {other_html}
        </ul>
      </section>

      <div class="ip-note">
        <p><strong>안내</strong> · 예측판은 글로벌 공개 시장의 확률을 한국어로 정리하는 정보 사이트입니다.
          회원가입·입금·베팅·거래 기능이 없고, 예측시장이나 관련 사이트로 연결되는 링크도 제공하지 않습니다.
          확률은 결과를 보장하지 않으며 투자 판단의 근거가 될 수 없습니다. 자세한 내용은
          <a href="/disclaimer.html">면책 고지</a>를 참고하세요.</p>
        <p class="ip-small">이 페이지의 수치는 {E(data.get("updated_label") or "")} 기준 저장 데이터이며,
          2시간마다 자동으로 새로 만들어집니다. 홈에서는 같은 이슈를 1분 단위 실시간 확률로 볼 수 있습니다.
          {'Kalshi 항목은 공개 API가 브라우저 교차 출처 요청을 허용하지 않아 저장값을 그대로 표시하며, 1분마다 실시간으로 갱신되는 Polymarket 항목과 숫자가 다를 수 있습니다.' if it.get('source') == 'Kalshi' else ''}</p>
      </div>

      <p class="ip-actions">
        <a class="btn primary" href="/#/live">홈에서 실시간 확률 보기</a>
        <a class="btn" href="/issues/">이슈 전체 목록</a>
        <a class="btn ghost" href="#share">이 카드 퍼가기</a>
      </p>

    </div>
  </article>
</main>
"""
    return head(page_title, desc, canonical, "article",
                json.dumps(ld, ensure_ascii=False, indent=2),
                og_image=og_url, og_alt=f"{title} — 글로벌 시장 확률 {num1(yes)}%") + body + FOOT


# ---------------------------------------------------------------------------
# 이슈 허브(/issues/)
# ---------------------------------------------------------------------------
def render_hub(items: list, data: dict, slug_map: dict) -> str:
    canonical = f"{SITE}/issues/"
    title = "이슈 전체 — 금리·코인·AI·글로벌 시장 확률 목록 | 예측판"
    desc = (
        f"예측판이 정리한 시장 확률 이슈 {len(items)}개의 목록입니다. "
        "미국 금리, 비트코인·이더리움, AI 기업가치, 중동·유럽 이슈의 공개 확률과 24시간 변동을 한눈에 보고 상세 해설로 이동하세요."
    )
    ld = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": title,
        "url": canonical,
        "description": desc,
        "inLanguage": "ko-KR",
        "isPartOf": {"@type": "WebSite", "name": SITE_NAME, "url": SITE + "/"},
        "dateModified": data.get("updated_at") or "",
    }

    blocks = []
    for cat in CAT_ORDER:
        group = [x for x in items if x.get("category") == cat]
        if not group:
            continue
        rows = "\n        ".join(issue_card_row(x, slug_map[x["key"]]) for x in group)
        blocks.append(f"""
      <section class="ip-sec">
        <h2>{CAT_ICON.get(cat, "")} {E(CAT_LABEL[cat])} <span class="ip-cnt">{len(group)}개</span></h2>
        <ul class="ip-related">
        {rows}
        </ul>
      </section>""")

    body = f"""
<main class="wrap">
  <nav class="ip-crumb" aria-label="페이지 위치">
    <a href="/">예측판 홈</a><span aria-hidden="true">›</span><em>이슈 전체</em>
  </nav>

  <article class="page ip-page">
    <div class="page-in">
      <header class="ip-head">
        <h1>이슈 전체</h1>
        <p class="ip-meta-line">
          <span>총 <b>{len(items)}개</b> 이슈</span>
          <span>데이터 기준 <b>{E(data.get("updated_label") or "")}</b></span>
          <span>출처 <b>Kalshi · Polymarket 공개 데이터</b></span>
        </p>
      </header>

      <p>금리·코인·AI·글로벌 이슈마다 Kalshi·Polymarket 등 글로벌 공개 시장 참가자들이 매긴 YES 확률과 24시간 변동을 정리했습니다.
        이슈를 누르면 배경 해설, 1주·1개월 변화, 거래량·마감일, 원문 질문까지 담은 상세 페이지로 이동합니다.
        홈(<a href="/">yecheukpan.kr</a>)에서는 같은 이슈를 1분 단위 실시간 확률과 한줄 투표로 볼 수 있습니다.</p>
      {"".join(blocks)}

      <div class="ip-note">
        <p><strong>안내</strong> · 예측판은 글로벌 공개 시장의 확률을 한국어로 정리하는 정보 사이트입니다.
          베팅·거래·입금 기능이 없고, 예측시장이나 관련 사이트로 연결되는 링크도 제공하지 않습니다.
          확률은 결과를 보장하지 않습니다. <a href="/disclaimer.html">면책 고지</a></p>
      </div>

      <p class="ip-actions">
        <a class="btn primary" href="/#/live">홈에서 실시간 확률 보기</a>
        <a class="btn ghost" href="/about.html">서비스 소개</a>
      </p>
    </div>
  </article>
</main>
"""
    return head(title, desc, canonical, "website", json.dumps(ld, ensure_ascii=False, indent=2)) + body + FOOT


# ---------------------------------------------------------------------------
# 이슈별 OG 이미지(og/{slug}.png, 1200×630)
# ---------------------------------------------------------------------------
def build_og_images(items: list, slug_map: dict, data: dict) -> int:
    """이슈마다 SNS·검색 미리보기용 OG 이미지를 만든다. 쓸 수 없는 환경이면 0."""
    if og_image is None or not og_image.fonts_available():
        print("  · OG 이미지 생성기를 쓰지 못합니다(Pillow 또는 Pretendard 폰트 없음) — 기존 이미지를 유지합니다.")
        return 0
    OG_DIR.mkdir(parents=True, exist_ok=True)
    votes = og_image.fetch_vote_tally()
    keep, made = set(), 0
    for it in items:
        name = f"{slug_map[it['key']]}.png"
        keep.add(name)
        try:
            png = og_image.render(it, votes, data.get("updated_label") or "")
        except Exception as e:  # noqa: BLE001 — 한 장이 실패해도 나머지는 만든다
            print(f"  ! OG 이미지 생성 실패({it.get('key')}): {e}")
            continue
        p = OG_DIR / name
        if p.exists() and p.read_bytes() == png:
            continue
        p.write_bytes(png)
        made += 1
    # 지금 목록에 없는 이슈의 이미지는 정리 (남겨 두면 og/ 가 계속 쌓인다)
    for old in OG_DIR.glob("*.png"):
        if old.name not in keep:
            old.unlink()
    print(f"  · OG 이미지 {len(keep)}장 (이번에 새로 쓴 것 {made}장)")
    return len(keep)


def sync_index_count(count: int) -> None:
    """index.html 첫 화면의 '오늘의 이슈 N개'를 실제 이슈 수와 맞춘다.

    JS 가 데이터를 불러오면 바로 고쳐지지만, 그 전 몇 초·크롤러가 읽는 초기 HTML 에
    옛 숫자가 남지 않도록 빌드할 때 같이 바꿔 둔다.
    """
    try:
        doc = INDEX_PATH.read_text(encoding="utf-8")
    except OSError:
        return
    new, n = re.subn(
        r'(<span class="cnt" id="pill-count">)오늘의 이슈 [\d,]+개(</span>)',
        lambda m: f"{m.group(1)}오늘의 이슈 {count}개{m.group(2)}",
        doc, count=1,
    )
    if n and new != doc:
        INDEX_PATH.write_text(new, encoding="utf-8")
        print(f"  · index.html 초기 문구 → 오늘의 이슈 {count}개")


# ---------------------------------------------------------------------------
# sitemap.xml
# ---------------------------------------------------------------------------
def render_sitemap(items: list, data: dict, slug_map: dict) -> str:
    last = (data.get("updated_at") or "")[:10] or date.today().isoformat()
    urls = [
        (SITE + "/", "hourly", "1.0", last),
        (SITE + "/issues/", "hourly", "0.9", last),
        (SITE + "/about.html", "monthly", "0.6", ""),
        (SITE + "/terms.html", "yearly", "0.4", ""),
        (SITE + "/privacy.html", "yearly", "0.3", ""),
        (SITE + "/disclaimer.html", "yearly", "0.3", ""),
    ]
    for x in items:
        urls.append((f"{SITE}/issues/{slug_map[x['key']]}.html", "hourly", "0.8", last))

    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, freq, prio, mod in urls:
        out.append("  <url>"
                   f"<loc>{E(loc)}</loc>"
                   + (f"<lastmod>{mod}</lastmod>" if mod else "")
                   + f"<changefreq>{freq}</changefreq><priority>{prio}</priority></url>")
    out.append("</urlset>")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="파일을 쓰지 않고 결과만 확인")
    args = ap.parse_args()

    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    items = [x for x in (data.get("items") or []) if x.get("key")]
    if not items:
        print("! markets.json 에 이슈가 없습니다. 아무것도 만들지 않습니다.", flush=True)
        return 1

    # 데이터가 오래됐을 때를 대비한 안전망 — 사생활·가십 항목은 페이지·사이트맵에서 뺀다.
    # 목록에서 빠지면 아래 '사라진 이슈 페이지 정리'가 해당 HTML도 지운다.
    clean = []
    for it in items:
        reason = blocked_reason(it.get("title", ""), it.get("question", ""),
                                it.get("event_title", ""))
        if reason:
            print(f"  · 가쉽·스캔들 제외('{reason}'): {it.get('key')} — {it.get('title')}")
            continue
        clean.append(it)
    items = clean
    if not items:
        print("! 필터를 지나 남은 이슈가 없습니다. 아무것도 만들지 않습니다.", flush=True)
        return 1

    order = {c: i for i, c in enumerate(CAT_ORDER)}
    items.sort(key=lambda x: (order.get(x.get("category"), 9), x.get("rank", 90),
                              -(float(x.get("volume_24h") or 0))))

    # slug 충돌 방지
    slug_map, used = {}, set()
    for it in items:
        s = slug_of(it)
        base, n = s, 2
        while s in used:
            s = f"{base}-{n}"
            n += 1
        used.add(s)
        slug_map[it["key"]] = s

    pages = {f"{slug_map[it['key']]}.html": render_issue(it, items, data, slug_map) for it in items}
    pages["index.html"] = render_hub(items, data, slug_map)
    sitemap = render_sitemap(items, data, slug_map)

    print(f"이슈 {len(items)}개 → 페이지 {len(pages)}개 (+ sitemap.xml)")
    for it in items:
        print(f"  - issues/{slug_map[it['key']]}.html  ← {it.get('title')}")

    if args.dry_run:
        print("(dry-run: 파일을 쓰지 않았습니다)")
        return 0

    ISSUES_DIR.mkdir(parents=True, exist_ok=True)
    for name, html_doc in pages.items():
        (ISSUES_DIR / name).write_text(html_doc, encoding="utf-8")

    # 이슈별 OG 이미지 + index.html 초기 문구의 이슈 수 동기화
    build_og_images(items, slug_map, data)
    sync_index_count(len(items))

    # 사라진 이슈 페이지 정리 — 지우지 않고 "새 주소로 이동" 안내 페이지로 바꾼다.
    # (검색엔진·블로그·X에 남은 구 주소가 404가 되지 않도록)
    by_title = {pretty_title(it.get("title", "")): slug_map[it["key"]] for it in items}
    stubs: list[pathlib.Path] = []
    removed = 0

    def stub_target(label: str, prev: str | None) -> str:
        t = by_title.get(pretty_title(label))
        if t and f"{t}.html" in pages:
            return f"{t}.html"
        if prev and prev in pages:
            return prev
        return ""

    for p in sorted(ISSUES_DIR.glob("*.html")):
        if p.name in pages or p.name == "index.html":
            continue
        try:
            doc = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        prev = stub_target_of(doc)
        label = stub_label_of(doc) if prev is not None else issue_title_of(doc)
        target = stub_target(label, prev)
        if not label and prev is None:
            p.unlink()
            removed += 1
            continue
        p.write_text(render_redirect_stub(target, label), encoding="utf-8")
        stubs.append(p)

    # 쌓인 안내 페이지는 최대 개수까지만 남긴다(오래된 것부터 정리).
    if len(stubs) > MAX_REDIRECT_STUBS:
        stubs.sort(key=lambda x: x.stat().st_mtime)
        cut = len(stubs) - MAX_REDIRECT_STUBS
        for p in stubs[:cut]:
            p.unlink()
            removed += 1
        stubs = stubs[cut:]

    if stubs:
        print(f"  · 구 주소 안내 페이지 {len(stubs)}개 유지(0건이면 404 안 됨)")
    if removed:
        print(f"  · 정리한 페이지 {removed}개")

    SITEMAP_PATH.write_text(sitemap, encoding="utf-8")
    print(f"  → sitemap.xml ({len(items) + 6}개 URL)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
