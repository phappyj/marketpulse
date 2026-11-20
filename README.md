# 마켓펄스 MarketPulse

글로벌 예측시장(Polymarket)의 **공개 확률 데이터를 한국어로 정리해 보여주는 정적 정보 사이트**입니다.
미국 금리 결정, 비트코인 가격 경로, AI 기업가치, 중동·유럽 지정학 리스크를 카드 형태로 보여주고,
각 이슈마다 짧은 배경 해설과 관전 포인트를 붙입니다.

- 라이브: https://phappyj.github.io/marketpulse/
- 호스팅: GitHub Pages (서버비 0원)
- 갱신: GitHub Actions가 **2시간마다** 데이터를 다시 만들어 커밋

## 구조

```
index.html                 메인 화면 (TOP 3 + 카테고리 탭 + 카드 그리드)
about.html                 서비스 소개 · 편집 원칙
privacy.html               개인정보처리방침 (AdSense 대비)
disclaimer.html            면책 고지
404.html                   없는 페이지 안내
assets/style.css           디자인 시스템 (화이트/슬레이트, 모바일 우선)
assets/app.js              markets.json 렌더러 (프레임워크 없음)
assets/favicon.svg         파비콘
data/markets.json          사이트가 읽는 데이터 (자동 생성)
scripts/fetch_markets.py   Polymarket Gamma API → markets.json (표준 라이브러리만 사용)
.github/workflows/update-markets.yml   매 2시간 자동 갱신 워크플로
```

## 데이터 만들기

```bash
python3 scripts/fetch_markets.py            # data/markets.json 갱신
python3 scripts/fetch_markets.py --dry-run  # 파일을 쓰지 않고 확인
```

동작 순서:

1. `economy`, `fed`, `crypto`, `ai`, `tech`, `business`, `geopolitics`, `world`, `big-tech`,
   `finance`, `macro` 태그의 인기 이벤트에서 YES/NO 2지선다 마켓을 모읍니다(약 2,500개).
2. `scripts/fetch_markets.py` 안의 `WATCH` 규칙(한국어 제목 + 해설 + 관전 포인트)에 맞는 마켓을
   카테고리별로 4개씩 고릅니다.
3. 규칙에 맞는 마켓이 모자라면 거래량 기준 자동 선별로 채웁니다(제목은 사전 기반 간이 번역).
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
- 모든 카드에 해설 필수, 출처(Polymarket 공개 API) 명시
- `about` / `privacy` / `disclaimer` 페이지로 정보 제공 목적과 한계를 고지

## 광고(AdSense) 붙일 때

1. AdSense 승인 후 `ca-pub-…` 스크립트를 `index.html`의 `</head>` 앞에 넣습니다.
2. `privacy.html`의 3항(제3자 광고·통계)은 이미 게재 전제로 작성되어 있으니, 실제 도입 시
   Google Analytics 사용 여부만 확인해 문구를 맞추면 됩니다.
3. 광고 단위는 카드 그리드 사이(예: 6번째 카드 뒤)와 상세 페이지 하단을 권장합니다.

## 로컬 미리보기

```bash
python3 -m http.server 8000
# http://localhost:8000
```

`data/markets.json`을 `fetch`로 읽으므로 `file://`로 열면 동작하지 않습니다.
