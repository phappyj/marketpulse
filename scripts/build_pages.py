#!/usr/bin/env python3
# 예측판 정적 문서 페이지 생성 스크립트 (about/privacy/terms/disclaimer/404)
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]

HEAD = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="https://yecheukpan.kr/{slug}">
<meta name="theme-color" content="#F3F5F8">
<meta property="og:type" content="website">
<meta property="og:site_name" content="예측판 YECHEUKPAN">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<link rel="icon" href="assets/favicon.svg" type="image/svg+xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;800&display=swap">
<link rel="stylesheet" href="assets/style.css?v=20261120m">
<!-- Google AdSense -->
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-3318185141094112" crossorigin="anonymous"></script>
</head>
<body>

<header class="site-header">
  <div class="wrap hd-top">
    <a class="logo" href="./" aria-label="예측판 홈">
      <span class="logo-mark" aria-hidden="true">예</span>
      <span class="logo-txt"><b>예측판</b><i>YECHEUKPAN</i></span>
    </a>
    <nav class="hd-tabs" aria-label="예측판 메뉴">
      <a class="tab" href="./#/live">실시간 예측판</a>
      <a class="tab" href="./#/talk">자유 수다방</a>
      <a class="tab" href="./#/guide">이슈 해설</a>
    </nav>
    <div class="hd-right">
      <a class="btn sm" href="./">홈으로</a>
    </div>
  </div>
</header>

<main class="wrap">
  <article class="page">
    <div class="page-in">
"""

FOOT = """    </div>
  </article>
</main>

<footer class="site-footer">
  <div class="wrap footer-inner">
    <div class="footer-top">
      <div class="footer-brand">
        <a class="logo" href="./">
          <span class="logo-mark" aria-hidden="true">예</span>
          <span class="logo-txt"><b>예측판</b><i>YECHEUKPAN</i></span>
        </a>
        <p>글로벌 예측시장의 공개 확률 데이터를 한국어 해설과 함께 정리하는 정보 커뮤니티입니다.
          베팅·거래·투자 권유를 목적으로 하지 않습니다.</p>
      </div>
      <nav class="footer-links" aria-label="사이트 정보">
        <a href="./">홈</a>
        <a href="about.html">서비스 소개</a>
        <a href="privacy.html">개인정보처리방침</a>
        <a href="terms.html">이용약관</a>
        <a href="disclaimer.html">면책 고지</a>
      </nav>
    </div>
    <div class="footer-legal">
      <p>© 2026 YECHEUKPAN. All rights reserved.</p>
    </div>
  </div>
</footer>

</body>
</html>
"""

ABOUT = """    <h1>서비스 소개</h1>
    <p class="page-meta">예측판(YECHEUKPAN) · 최종 수정 2026년 11월 20일</p>

    <p>예측판은 <strong>전 세계 예측시장에서 거래되는 확률 데이터를 한국어로 정리해 보여주고,
      그 위에 독자들의 판단을 모으는 정보 커뮤니티</strong>입니다. 미국의 금리 결정, 비트코인의 가격,
      AI 기업의 몸값, 중동과 유럽의 정치·외교 이슈처럼 숫자로 기대를 말할 수 있는 주제를 골라
      확률이 실제로 무엇을 뜻하는지 해설과 함께 제공합니다.</p>

    <div class="panel">
      <h3>왜 만들었나</h3>
      <p>주식·환율·금리 뉴스는 넘쳐나지만, “시장 참가자들이 지금 이 사건을 몇 % 확률로 보고 있는가”를
        한눈에 정리해 주는 한국어 콘텐츠는 드뭅니다. 해외 예측시장에는 그런 데이터가 공개되어 있지만
        영어로, 그리고 시장 화면 형태로만 존재합니다. 예측판은 그 숫자를 <strong>읽을 수 있는 문장과 해설</strong>로
        바꾸고, 거기에 <strong>국내 독자들의 한줄 투표와 토론</strong>을 얹는 일을 합니다.</p>
    </div>

    <h2>무엇을 보여주나요</h2>
    <ul>
      <li><strong>시장 YES / NO 확률</strong> — 해당 사건이 일어날 것이라고 전 세계 참가자들이 매긴 기대값(%)입니다.</li>
      <li><strong>24시간·누적 거래량</strong> — 그 확률에 얼마나 많은 돈과 관심이 실렸는지를 보여줍니다. 거래량이 적으면 확률이 쉽게 흔들립니다.</li>
      <li><strong>마감일</strong> — 사건이 판정되는 시점입니다. 미국 동부시간 기준 마감일을 한국어로 표기합니다.</li>
      <li><strong>24시간 변동</strong> — 직전 24시간 동안 확률이 몇 %p 움직였는지 표시합니다.</li>
      <li><strong>이슈 배경 &amp; 관전 포인트</strong> — 행을 펼치면 왜 이 이슈가 중요한지, 무엇을 보면 좋은지 짧은 해설이 나옵니다.</li>
      <li><strong>한줄 투표 · 댓글</strong> — 이슈마다 <em>👍 YES / 👎 NO</em> 버튼으로 한 번에 의견을 남기고, 근거를 댓글로 나눌 수 있습니다.</li>
    </ul>

    <h2>세 개의 탭</h2>
    <table>
      <thead><tr><th>탭</th><th>내용</th></tr></thead>
      <tbody>
        <tr><td>실시간 예측판</td><td>오늘의 주요 예측 TOP 3와 전체 이슈 목록. 행마다 시장 확률·한줄 투표·댓글 수가 함께 표시되고, 행을 누르면 해설이 펼쳐집니다.</td></tr>
        <tr><td>자유 수다방</td><td>금리·증시 / 코인 / AI·빅테크 / 자유 말머리로 글과 댓글을 나누는 게시판입니다.</td></tr>
        <tr><td>이슈 해설</td><td>숫자를 읽는 네 가지 규칙, 예측판 여론과 시장 확률의 차이, 커뮤니티 운영 원칙, FAQ.</td></tr>
      </tbody>
    </table>

    <h2>카테고리</h2>
    <table>
      <thead><tr><th>카테고리</th><th>다루는 주제</th></tr></thead>
      <tbody>
        <tr><td>경제·금리</td><td>미 연준(Fed)의 금리 결정, 연간 인상·인하 횟수, 국제유가 등 매크로 지표</td></tr>
        <tr><td>코인·금융</td><td>비트코인·이더리움 가격 경로, 온체인 상징 이벤트, 주요 금융 이슈</td></tr>
        <tr><td>AI·테크</td><td>AI 기업의 기업가치와 상장(IPO), 빅테크 시가총액 순위, AI 모델 경쟁</td></tr>
        <tr><td>글로벌</td><td>중동·유럽의 지정학 리스크, 휴전·분쟁, 주요국 선거, 해상 물류</td></tr>
      </tbody>
    </table>

    <h2>데이터는 어떻게 들어오나요</h2>
    <p>Polymarket이 공개하는 무료 API(Gamma API)에서 경제·금리, 코인, AI·테크, 글로벌 태그의 마켓을
      수집합니다. 그중 <strong>한국어 해설이 준비된 이슈를 우선 선별</strong>하고, 부족한 카테고리는 거래량 기준으로
      자동 보충합니다. 선별이 끝나면 <code>data/markets.json</code> 파일로 저장되고, 이 사이트는 그 파일을 읽어
      화면을 그립니다. 갱신은 <strong>2시간마다 자동</strong>으로 이뤄지며, 상단의 ‘업데이트 시각’이 마지막 갱신 시점입니다.</p>

    <h2>커뮤니티는 어떻게 운영되나요</h2>
    <ol>
      <li><strong>회원가입이 없습니다.</strong> 닉네임과 4자리 비밀번호만으로 글과 댓글을 남기고, 같은 비밀번호로 직접 삭제합니다.</li>
      <li><strong>도박·불법 금융 홍보를 차단합니다.</strong> 사설 토토·카지노·리딩방·텔레그램·레퍼럴 등 금칙어는
        화면과 서버 양쪽에서 걸러집니다.</li>
      <li><strong>도배를 막습니다.</strong> 한 브라우저에서 15초 안에 다시 쓰면 등록되지 않습니다.</li>
      <li><strong>신고를 받습니다.</strong> 신고가 3회 누적된 글·댓글은 자동으로 가려집니다.</li>
      <li><strong>비밀번호는 해시로만 저장합니다.</strong> 원문은 어디에도 남지 않으며, 외부에 공개되지 않습니다.</li>
    </ol>

    <h2>편집 원칙</h2>
    <ol>
      <li><strong>정보만 제공합니다.</strong> 베팅·거래·입금·회원가입 기능을 제공하지 않고, 예측시장이나 베팅
        사이트로 연결되는 링크·제휴 코드도 넣지 않습니다.</li>
      <li><strong>국내 정치·선거는 다루지 않습니다.</strong> 경제·금융·기술·국제 이슈로 범위를 한정합니다.</li>
      <li><strong>해설 없는 숫자는 싣지 않습니다.</strong> 모든 이슈에는 짧은 배경 설명과 관전 포인트가 붙습니다.</li>
      <li><strong>출처를 밝힙니다.</strong> 모든 확률은 Polymarket 공개 데이터에서 왔으며, 예측판이 계산하거나
        보증하는 값이 아닙니다.</li>
      <li><strong>틀릴 수 있음을 인정합니다.</strong> 확률은 예측이 아니라 가격입니다. 자세한 내용은
        <a href="disclaimer.html">면책 고지</a>를 참고하세요.</li>
    </ol>

    <h2>한계</h2>
    <p>예측시장의 확률은 참가자 구성과 유동성에 따라 달라집니다. 거래량이 적은 마켓은 소수 참가자의 의견이
      과도하게 반영될 수 있고, 마감이 임박하면 변동성이 커집니다. 또한 마켓의 판정 기준(예: 종가 기준인지
      장중 터치 기준인지)에 따라 같은 사건도 확률이 달라질 수 있으므로, 펼친 해설의 <strong>원문 질문</strong>을 함께
      확인하시길 권합니다. 커뮤니티의 투표와 댓글은 참고 의견일 뿐 시장 확률이나 투자 판단을 대체하지 않습니다.</p>

    <h2>문의</h2>
    <p>데이터 오류 제보, 해설 보완 요청, 게시물 신고·삭제 요청은 저장소 이슈로 남겨 주세요:
      <a href="https://github.com/phappyj/marketpulse/issues" rel="noopener">github.com/phappyj/marketpulse/issues</a><br>
      서비스 주소는 <strong>yecheukpan.kr</strong>입니다.</p>

    <a class="back" href="./">← 예측판 홈으로</a>
"""

PRIVACY = """    <h1>개인정보처리방침</h1>
    <p class="page-meta">시행일: 2026년 11월 20일 · 최종 수정: 2026년 11월 20일</p>

    <p>예측판(이하 “사이트”)은 이용자의 개인정보를 소중하게 생각합니다. 본 방침은 사이트가 어떤 정보를
      어떤 목적으로 다루고, 이용자가 어떤 권리를 가지는지 설명합니다.</p>

    <h2>1. 수집하는 정보</h2>
    <p>사이트는 <strong>회원가입 절차가 없으며</strong>, 이름·전화번호·주민등록번호처럼 이용자를 직접 식별하는 정보를
      요구하지 않습니다. 커뮤니티 기능(한줄 투표, 댓글, 수다방)을 이용할 때 다음 정보가 저장됩니다.</p>
    <table>
      <thead><tr><th>항목</th><th>목적</th><th>비고</th></tr></thead>
      <tbody>
        <tr><td>닉네임 (이용자가 입력)</td><td>게시물·댓글 작성자 표시</td><td>실명일 필요 없음</td></tr>
        <tr><td>4자리 비밀번호</td><td>본인 글·댓글 삭제 확인</td><td>복호화 불가능한 해시로만 저장, 원문 미보관</td></tr>
        <tr><td>글·댓글 내용</td><td>커뮤니티 게시</td><td>이용자가 직접 삭제 가능</td></tr>
        <tr><td>브라우저 식별값</td><td>중복 투표 방지, 도배 방지, 신고 중복 방지</td><td>무작위로 생성된 값(개인 식별 불가), 브라우저 저장소에 보관</td></tr>
        <tr><td>접속 기록(IP 등)</td><td>서비스 운영·보안</td><td>호스팅·데이터베이스 사업자가 자동 기록</td></tr>
      </tbody>
    </table>

    <h2>2. 브라우저 저장소(쿠키·로컬스토리지)</h2>
    <p>사이트 자체는 추적 쿠키를 사용하지 않습니다. 다만 광고 게재를 위해 Google AdSense가 쿠키를 사용할 수 있습니다(8항 참고).
      중복 투표 방지와 도배 방지를 위해
      <strong>무작위 식별값</strong>을 브라우저의 로컬스토리지에 저장합니다. 이 값은 이름·이메일과 연결되지 않으며,
      브라우저 저장소를 지우면 새 값이 생성됩니다. 저장소를 차단하면 투표·댓글 작성이 제한될 수 있습니다.</p>

    <h2>3. 처리 위탁 및 국외 이전</h2>
    <p>커뮤니티 데이터는 다음 사업자의 클라우드 데이터베이스에 저장됩니다.</p>
    <ul>
      <li><strong>Supabase Inc.</strong> — 데이터베이스 호스팅. 프로젝트 리전: 대한민국(서울, AWS ap-northeast-2)</li>
      <li><strong>GitHub, Inc.</strong> — 정적 웹 페이지 호스팅(GitHub Pages)</li>
    </ul>
    <p>위 사업자는 서비스 제공에 필요한 범위에서만 데이터를 처리하며, 이용자의 개인정보를 판매하지 않습니다.</p>

    <h2>4. 보유 및 이용 기간</h2>
    <p>게시물과 댓글은 <strong>이용자가 삭제할 때까지</strong> 보관됩니다. 신고 3회로 가려진 글은 화면에 노출되지 않으나,
      운영 확인을 위해 기록이 남을 수 있습니다. 브라우저 식별값은 이용자가 브라우저 저장소를 지우면 즉시 사라집니다.</p>

    <h2>5. 이용자의 권리</h2>
    <ul>
      <li>본인이 작성한 글·댓글은 작성 시 입력한 4자리 비밀번호로 <strong>언제든지 직접 삭제</strong>할 수 있습니다.</li>
      <li>비밀번호를 잊은 경우, 저장소 이슈로 게시물 주소와 함께 삭제를 요청할 수 있습니다.</li>
      <li>브라우저 설정에서 저장소를 삭제해 식별값을 초기화할 수 있습니다.</li>
    </ul>

    <h2>6. 아동의 개인정보</h2>
    <p>사이트는 만 14세 미만 아동을 대상으로 하지 않으며, 아동의 개인정보를 의도적으로 수집하지 않습니다.</p>

    <h2>7. 안전성 확보 조치</h2>
    <p>사이트는 HTTPS로만 제공되며, 비밀번호는 단방향 해시(bcrypt)로 저장됩니다. 데이터베이스에는 행 수준 보안(RLS)
      정책을 적용해, 공개 키만으로는 비밀번호 해시를 읽거나 다른 사람의 글을 수정할 수 없습니다.</p>

    <h2>8. 제3자 광고 및 통계 도구</h2>
    <p>사이트는 Google AdSense를 통해 광고를 게재합니다. Google은 제3자 공급업체로서 쿠키를 사용해 이용자가 이 사이트나
      다른 사이트를 방문한 기록을 바탕으로 광고를 표시할 수 있습니다. 맞춤 광고는
      <a href="https://adssettings.google.com" rel="noopener">Google 광고 설정</a> 또는
      <a href="https://www.aboutads.info" rel="noopener">www.aboutads.info</a>에서 해제할 수 있으며,
      Google의 광고 쿠키 사용에 대한 자세한 내용은 Google 광고 정책 페이지에서 확인할 수 있습니다.
      이 밖에 사이트가 직접 운영하는 통계·추적 도구는 사용하지 않습니다.</p>

    <h2>9. 방침의 변경</h2>
    <p>본 방침이 변경되는 경우 이 페이지에 변경 내용과 시행일을 게시합니다.</p>

    <h2>10. 문의</h2>
    <p>개인정보 처리와 관련한 문의·삭제 요청은 저장소 이슈로 남겨 주세요:
      <a href="https://github.com/phappyj/marketpulse/issues" rel="noopener">github.com/phappyj/marketpulse/issues</a></p>

    <a class="back" href="./">← 예측판 홈으로</a>
"""

TERMS = """    <h1>이용약관</h1>
    <p class="page-meta">시행일: 2026년 11월 20일</p>

    <p>본 약관은 예측판(이하 “사이트”)이 제공하는 정보 및 커뮤니티 서비스의 이용 조건을 정합니다.
      사이트를 이용하면 본 약관에 동의한 것으로 봅니다.</p>

    <h2>제1조 (목적)</h2>
    <p>이 약관은 사이트가 제공하는 글로벌 예측 확률 정보, 이슈 해설, 한줄 투표, 댓글, 자유 수다방 서비스의
      이용에 관한 권리·의무와 책임 사항을 정하는 것을 목적으로 합니다.</p>

    <h2>제2조 (서비스의 내용)</h2>
    <ol>
      <li>사이트는 공개 API로 수집한 예측시장 확률·거래량 데이터를 한국어 해설과 함께 제공합니다.</li>
      <li>이용자는 이슈별 한줄 투표와 댓글, 자유 수다방 게시글·댓글로 의견을 남길 수 있습니다.</li>
      <li>사이트는 <strong>베팅·거래·입금 대행·투자 자문</strong>을 제공하지 않으며, 관련 사이트로 연결되는 링크나
        제휴 코드를 게재하지 않습니다.</li>
    </ol>

    <h2>제3조 (이용 자격과 참여 방식)</h2>
    <ol>
      <li>별도의 회원가입 없이 누구나 정보를 열람할 수 있습니다.</li>
      <li>글·댓글 작성 시 닉네임과 4자리 비밀번호를 입력하며, 비밀번호는 삭제 권한 확인에만 사용됩니다.</li>
      <li>비밀번호 관리 책임은 이용자에게 있으며, 분실로 인한 삭제 불가는 운영자가 보상하지 않습니다.</li>
      <li>만 14세 미만은 보호자의 동의 없이 게시 활동을 할 수 없습니다.</li>
    </ol>

    <h2>제4조 (이용자의 의무와 금지행위)</h2>
    <p>이용자는 다음 행위를 해서는 안 됩니다.</p>
    <ol>
      <li>도박·사설 토토·카지노·베팅 사이트, 투자 리딩방, 텔레그램·오픈채팅·레퍼럴 등 <strong>불법·상업적 홍보</strong></li>
      <li>욕설·비방·혐오·차별 표현, 타인의 명예를 훼손하는 내용</li>
      <li>허위 사실이나 확인되지 않은 정보를 사실인 것처럼 유포하는 행위</li>
      <li>타인의 개인정보(실명·연락처·계좌 등)를 무단으로 게시하는 행위</li>
      <li>자동화된 수단으로 대량 게시하거나 서비스 운영을 방해하는 행위</li>
      <li>특정 자산의 매수·매도를 직접 권유하거나 수익을 보장하는 문구로 타인을 유인하는 행위</li>
      <li>관련 법령과 본 약관, 사이트의 운영 원칙을 위반하는 행위</li>
    </ol>

    <h2>제5조 (게시물의 관리)</h2>
    <ol>
      <li>게시물의 저작권은 작성자에게 있습니다. 작성자는 사이트가 서비스를 제공하기 위해 게시물을
        화면에 표시·저장하는 것을 허락합니다.</li>
      <li>사이트는 금칙어 필터로 도박·홍보·욕설 표현을 자동 차단하며, 신고가 3회 누적된 글·댓글은
        자동으로 가려집니다.</li>
      <li>사이트는 제4조를 위반한 게시물을 사전 통지 없이 가리거나 삭제할 수 있습니다.</li>
      <li>이용자는 본인이 작성한 글·댓글을 4자리 비밀번호로 직접 삭제할 수 있습니다.</li>
    </ol>

    <h2>제6조 (정보의 성격과 한계)</h2>
    <p>표시되는 확률은 예측시장 참가자들이 매긴 기대값이며 결과를 보장하지 않습니다. 커뮤니티의 투표·댓글은
      작성자의 개인 의견으로 사이트의 견해가 아닙니다. 자세한 내용은 <a href="disclaimer.html">면책 고지</a>를 따릅니다.</p>

    <h2>제7조 (서비스의 변경·중단)</h2>
    <p>사이트는 운영상·기술상 필요에 따라 서비스의 전부 또는 일부를 변경하거나 중단할 수 있습니다.
      외부 API 정책 변경, 호스팅 장애 등으로 데이터 갱신이 지연될 수 있습니다.</p>

    <h2>제8조 (책임의 제한)</h2>
    <p>사이트는 정보 제공 및 커뮤니티 운영의 범위에서 성실히 노력하되, 데이터의 지연·오류·누락, 이용자 게시물,
      서비스 중단으로 발생한 손해에 대해 법령이 허용하는 범위에서 책임을 지지 않습니다. 이용자가 게시한 내용으로
      발생한 분쟁은 해당 이용자가 책임집니다.</p>

    <h2>제9조 (준거법 및 분쟁 해결)</h2>
    <p>본 약관은 대한민국 법률에 따라 해석되며, 분쟁이 발생할 경우 운영자의 주소지를 관할하는 법원을
      제1심 법원으로 합니다.</p>

    <h2>제10조 (약관의 변경)</h2>
    <p>약관이 변경되는 경우 이 페이지에 변경 내용과 시행일을 게시합니다. 변경 후 계속 이용하면 변경된 약관에
      동의한 것으로 봅니다.</p>

    <a class="back" href="./">← 예측판 홈으로</a>
"""

DISCLAIMER = """    <h1>면책 고지</h1>
    <p class="page-meta">시행일: 2026년 11월 20일</p>

    <div class="panel">
      <p style="margin:0"><strong>요약:</strong> 예측판은 정보 제공 사이트입니다. 베팅·거래·투자 자문이 아니며,
        확률은 참가자들의 기대를 모은 ‘가격’일 뿐 결과를 보장하지 않습니다. 투자 판단과 그 결과에 대한 책임은
        이용자 본인에게 있습니다.</p>
    </div>

    <h2>1. 정보 제공 목적</h2>
    <p>본 사이트의 모든 콘텐츠는 일반적인 정보 제공과 교육을 목적으로 작성되었습니다. 특정 주식·채권·가상자산·
      원자재·파생상품의 매수·매도, 또는 예측시장·베팅 참여를 권유하는 내용이 아닙니다.</p>

    <h2>2. 투자 자문이 아닙니다</h2>
    <p>예측판은 금융투자업자나 투자자문업자가 아니며, 자본시장과 금융투자업에 관한 법률상 투자 자문·일임
      서비스를 제공하지 않습니다. 본 사이트의 내용을 근거로 한 투자 결정은 이용자의 판단이며, 그 결과에 대해
      운영자는 책임을 지지 않습니다.</p>

    <h2>3. 확률의 성격</h2>
    <ul>
      <li>표시된 확률은 전 세계 예측시장 참가자들이 매긴 <strong>기대값</strong>이며, 발생 가능성에 대한 통계적 보증이 아닙니다.</li>
      <li>확률 90%인 사건도 실제로 일어나지 않을 수 있고, 확률 10%인 사건도 일어날 수 있습니다.</li>
      <li>확률은 거래에 따라 실시간으로 변하며, 스프레드·수수료·유동성에 따라 실제 기대와 차이가 날 수 있습니다.</li>
      <li>동일한 사건이라도 마켓의 판정 기준(종가 기준/장중 터치 기준, 판정 출처 등)에 따라 확률이 달라집니다.</li>
    </ul>

    <h2>4. 데이터의 정확성·완전성</h2>
    <p>사이트는 외부 공개 API에서 받은 데이터를 2시간마다 자동으로 정리합니다. 통신 장애·API 변경·마켓 종료 등으로
      <strong>일부 데이터가 지연되거나 누락되거나 잘못 표시될 수 있습니다.</strong> 운영자는 데이터의 정확성·완전성·
      최신성을 보증하지 않으며, 오류를 발견하면 이슈를 통해 제보해 주시면 확인 후 수정합니다.</p>

    <h2>5. 커뮤니티 게시물</h2>
    <p>한줄 투표, 댓글, 수다방 게시글은 이용자의 개인 의견이며 예측판의 견해가 아닙니다. 사이트는 금칙어 필터와
      신고 기능으로 도박·홍보·욕설을 걸러내지만, 모든 게시물을 사전 검수하지는 않습니다. 게시물의 신뢰성 판단과
      그에 따른 결정은 이용자 책임입니다.</p>

    <h2>6. 베팅·도박과의 관계</h2>
    <p>예측판은 베팅·도박·예측시장 참여를 위한 서비스가 아닙니다. 사이트 내에는 <strong>회원가입·입금·베팅·
      거래 기능이 없고, 관련 사이트로 연결되는 링크나 제휴 코드도 제공하지 않습니다.</strong> 본 사이트는
      데이터를 제공하는 예측시장 운영사와 제휴·후원 관계가 없습니다. 커뮤니티에서 도박·사설 토토·리딩방을
      홍보하는 글은 금칙어 필터로 차단되며, 발견 즉시 가려집니다.</p>

    <h2>7. 콘텐츠의 범위</h2>
    <p>국내 정치·선거 관련 이슈는 다루지 않습니다. 해설은 공개된 시장 데이터를 바탕으로 한 일반적인 배경 설명이며,
      사실관계는 기사·공식 발표 등 별도 출처를 통해 확인하시길 권합니다.</p>

    <h2>8. 손해배상의 제한</h2>
    <p>운영자는 본 사이트의 이용 또는 이용할 수 없음으로 인해 발생한 직접·간접·특별·결과적 손해에 대해
      책임을 지지 않습니다. 이는 데이터 오류, 서비스 중단, 이용자 게시물, 외부 링크로 인한 손해를 포함합니다.</p>

    <h2>9. 준거법</h2>
    <p>본 고지는 대한민국 법률에 따라 해석되며, 분쟁이 발생할 경우 운영자의 주소지를 관할하는 법원을
      제1심 법원으로 합니다.</p>

    <h2>10. 문의</h2>
    <p>콘텐츠 정정 요청은 저장소 이슈로 남겨 주세요:
      <a href="https://github.com/phappyj/marketpulse/issues" rel="noopener">github.com/phappyj/marketpulse/issues</a></p>

    <a class="back" href="./">← 예측판 홈으로</a>
"""

PAGES = [
    ("about.html", "서비스 소개 — 예측판(YECHEUKPAN)",
     "예측판은 전 세계 예측시장의 공개 확률을 한국어 해설과 함께 정리하고, 이슈별 한줄 투표·댓글로 의견을 나누는 정보 커뮤니티입니다.", ABOUT),
    ("privacy.html", "개인정보처리방침 — 예측판(YECHEUKPAN)",
     "예측판의 개인정보처리방침입니다. 회원가입 없는 커뮤니티에서 수집하는 정보, 보관 기간, 이용자의 권리를 설명합니다.", PRIVACY),
    ("terms.html", "이용약관 — 예측판(YECHEUKPAN)",
     "예측판 서비스 이용약관입니다. 정보 제공 범위, 커뮤니티 참여 방식, 금지행위와 게시물 관리 원칙을 안내합니다.", TERMS),
    ("disclaimer.html", "면책 고지 — 예측판(YECHEUKPAN)",
     "예측판의 면책 고지입니다. 본 사이트는 정보 제공 목적이며 투자·베팅 권유가 아닙니다. 데이터의 한계와 책임 범위를 안내합니다.", DISCLAIMER),
]

for slug, title, desc, body in PAGES:
    html = HEAD.format(title=title, desc=desc, slug=slug) + body + "\n" + FOOT
    (ROOT / slug).write_text(html, encoding="utf-8")
    print("wrote", slug)

# 404
n404 = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>페이지를 찾을 수 없습니다 — 예측판</title>
<meta name="robots" content="noindex">
<meta name="theme-color" content="#F3F5F8">
<link rel="icon" href="assets/favicon.svg" type="image/svg+xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;800&display=swap">
<link rel="stylesheet" href="assets/style.css?v=20261120m">
<!-- Google AdSense -->
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-3318185141094112" crossorigin="anonymous"></script>
</head>
<body>
<header class="site-header">
  <div class="wrap hd-top">
    <a class="logo" href="./" aria-label="예측판 홈">
      <span class="logo-mark" aria-hidden="true">예</span>
      <span class="logo-txt"><b>예측판</b><i>YECHEUKPAN</i></span>
    </a>
    <nav class="hd-tabs" aria-label="예측판 메뉴">
      <a class="tab" href="./#/live">실시간 예측판</a>
      <a class="tab" href="./#/talk">자유 수다방</a>
      <a class="tab" href="./#/guide">이슈 해설</a>
    </nav>
  </div>
</header>
<main class="wrap">
  <article class="page">
    <div class="page-in">
    <h1>페이지를 찾을 수 없습니다</h1>
    <p class="page-meta">404 Not Found</p>
    <p>주소가 바뀌었거나 삭제된 페이지입니다. 아래에서 다시 시작해 보세요.</p>
    <p style="margin-top:16px;display:flex;gap:8px;flex-wrap:wrap">
      <a class="btn primary" href="./#/live">실시간 예측판</a>
      <a class="btn" href="./#/talk">자유 수다방</a>
      <a class="btn ghost" href="./#/guide">이슈 해설</a>
    </p>
    </div>
  </article>
</main>
</body>
</html>
"""
(ROOT / "404.html").write_text(n404, encoding="utf-8")
print("wrote 404.html")
