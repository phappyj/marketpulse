# 예측판 YECHEUKPAN

**시장이 매긴 확률로 읽는 경제·코인·AI 데이터 사이트**입니다. 미국 CFTC 인가 **Kalshi**와 Polymarket 등 글로벌 공개 시장의 확률을 한국어 해설과 함께 보여주고, 이슈마다 한줄 투표와 댓글로 의견을 모읍니다.
미국 금리 결정, 비트코인 가격 경로, AI 기업가치, 중동·유럽 지정학 리스크를 카드로 보여주고, 그 위에
`👍 YES 간다 / 👎 NO 꺾인다` 투표와 자유 수다방을 얹었습니다. 베팅·거래 기능은 제공하지 않습니다.

- 라이브: https://yecheukpan.kr/
- 준비 중 도메인: `yecheukpan.kr` (가비아 등록 완료 후 GitHub Pages 커스텀 도메인으로 연결 예정)
- 호스팅: GitHub Pages (정적) + Supabase (커뮤니티 DB, 서울 리전)
- 데이터 갱신: GitHub Actions가 **2시간마다** `data/markets.json` 재생성

## 화면 구성

| 탭 | 내용 |
| --- | --- |
| 실시간 예측판 | TOP 3 + 카테고리 필터 + 이슈 카드(시장 확률, 한줄 투표, 댓글) |
| 자유 수다방 | 말머리(금리·증시 / 코인 / AI·빅테크 / 자유) 게시판, 글·댓글 |
| 이슈 해설 | 숫자를 읽는 네 가지 규칙, 여론과 시장 확률의 차이, 운영 원칙, FAQ |

## 구조

```
index.html                 메인 (탭 3개: 실시간 예측판 / 자유 수다방 / 이슈 해설)
about.html                 서비스 소개 · 편집 원칙
privacy.html               개인정보처리방침
terms.html                 이용약관
disclaimer.html            면책 고지
404.html                   없는 페이지 안내
assets/style.css           디자인 시스템 (다크 커뮤니티형, 모바일 우선)
assets/config.js           Supabase 프로젝트 URL · 공개(publishable) 키
assets/app.js              데이터 렌더 · 한줄 투표 · 이슈 댓글
assets/community.js        자유 수다방 (목록 · 글쓰기 · 상세 · 댓글)
assets/favicon.svg         파비콘
data/markets.json          사이트가 읽는 데이터 (자동 생성)
db/schema.sql              Supabase 스키마 (테이블 · RLS · RPC)
scripts/fetch_markets.py   Kalshi · Polymarket 공개 API → markets.json (표준 라이브러리만 사용)
scripts/build_issue_pages.py  이슈별 SEO 페이지 · sitemap.xml 생성
scripts/build_pages.py     문서 페이지(about/privacy/terms/disclaimer) 생성 (404.html은 직접 관리)
.github/workflows/update-markets.yml   매 2시간 자동 갱신 워크플로
```

## 커뮤니티 백엔드 (Supabase)

- 프로젝트: `yecheukpan` (리전 ap-northeast-2 서울)
- 테이블은 모두 `yp_` 접두어로 분리: `yp_posts`, `yp_comments`, `yp_votes`, `yp_reports`, `yp_banned_words`
- **읽기**는 RLS 정책(`hidden = false and report_count < 3`)이 적용된 컬럼만 공개되고,
  `pw_hash`는 컬럼 권한에서 제외되어 공개 키로 읽을 수 없습니다.
- **쓰기**는 전부 `SECURITY DEFINER` RPC로만 허용됩니다.
  - `yp_vote`, `yp_vote_tally`, `yp_my_votes`
  - `yp_add_issue_comment`, `yp_add_post_comment`, `yp_issue_comments`, `yp_comment_counts`
  - `yp_add_post`, `yp_list_posts`, `yp_get_post`
  - `yp_delete_comment`, `yp_delete_post` (4자리 비밀번호 = bcrypt 검증)
  - `yp_report` (1인 1회, 3회 누적 시 자동 숨김)
- 서버 측 안전장치: 금칙어 검사(`yp_banned_words`), 15초 쿨다운, 1시간 30건 한도, 길이 제한
- 비밀번호는 `crypt(pw, gen_salt('bf'))` 해시로만 저장됩니다.

스키마를 다시 적용하려면 Supabase SQL Editor에서 `db/schema.sql`을 실행합니다(재실행 안전).

## 데이터 만들기

```bash
python3 scripts/fetch_markets.py            # data/markets.json 갱신
python3 scripts/fetch_markets.py --dry-run  # 파일을 쓰지 않고 확인
python3 scripts/build_pages.py              # 문서 페이지 재생성
```

1. `economy`, `fed`, `crypto`, `ai`, `tech`, `business`, `geopolitics`, `world`, `big-tech`,
   `finance`, `macro` 태그의 인기 이벤트에서 YES/NO 2지선다 마켓을 모읍니다(약 2,500개).
2. `scripts/fetch_markets.py`의 `WATCH` 규칙(한국어 제목 + 해설 + 관전 포인트)에 맞는 마켓을
   카테고리별로 4개씩 고릅니다.
3. 규칙에 맞는 마켓이 모자라면 거래량 기준 자동 선별로 채웁니다.
4. 새 항목이 8개 미만이면 **기존 파일을 덮어쓰지 않습니다**(API 장애 시 사이트 보호).

### 해설을 추가하려면

`scripts/fetch_markets.py`의 `WATCH` 리스트에 항목을 추가합니다.

```python
dict(
    key="my-issue", cat="economy", rank=5,          # cat: economy | crypto | ai | global
    q=r"정규식으로_마켓_질문_매칭",                  # 예: r"Bitcoin dip to \$60,000 by December 31"
    title="카드에 보일 한국어 제목",
    explain="이슈 배경 2~3문장",
    watch="관전 포인트 1~2문장",
),
```

## 운영 원칙 (법적·정책 안전선)

- 베팅·거래·입금·회원가입 기능 **없음**, 예측시장/베팅 사이트로 가는 **링크·제휴 코드 없음**
- 국내 정치·선거 관련 마켓은 수집 단계에서 제외 (`KOREA_BLOCK`)
- 커뮤니티: 도박·사설 토토·리딩방·텔레그램·레퍼럴·욕설은 금칙어 필터로 차단, 신고 3회 시 자동 숨김
- 모든 카드에 해설 필수, 카드마다 **출처 배지(Kalshi / Polymarket)** 표시
- Kalshi는 공개 API가 브라우저 교차 출처 요청을 허용하지 않아(Origin 헤더 → 403) 60초 실시간 조회에서 제외하고 저장값을 유지한다
- `about` / `privacy` / `terms` / `disclaimer` 페이지로 정보 제공 목적과 한계를 고지

## 로컬 미리보기

```bash
python3 -m http.server 8000
# http://localhost:8000
```

`data/markets.json`과 Supabase RPC를 `fetch`로 호출하므로 `file://`로 열면 동작하지 않습니다.
