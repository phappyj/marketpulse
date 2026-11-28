#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
예측판(YECHEUKPAN) 데이터 갱신 스크립트
=========================================

두 곳의 공개 API에서 경제·금리, 코인, AI·빅테크, 글로벌 이슈 마켓을 가져와
한국어 큐레이션 데이터(data/markets.json)를 만든다.

- Polymarket 공개 Gamma API(큐레이션 규칙 WATCH + 자동 선별)
- Kalshi 공개 Trade API(미국 CFTC 인가 예측시장, API 키 없이 조회 가능)
  → KALSHI_SERIES 에 적어 둔 주요 시리즈에서 거래량·미결제 약정이 큰 마켓을 골라
    한국어 제목·해설로 옮긴다. 항목마다 source(Kalshi/Polymarket)를 남긴다.

- 표준 라이브러리만 사용한다(서버·유료 API 없음, GitHub Actions에서 무료 실행).
- 큐레이션 규칙(WATCH)에 매칭되는 마켓을 우선 채우고, 매칭이 모자라면
  자동 선별(auto) 항목으로 최소 8개까지 채운다.
- 사생활·성추문·불륜·가십성 스캔들 표현이 있는 마켓은 후보 단계에서 버린다
  (scripts/content_filter.py — 애드센스 정책·명예훼손 리스크).
- 새로 만든 항목이 8개 미만이면 기존 파일을 덮어쓰지 않는다(사이트 보호).

사용법:  python3 scripts/fetch_markets.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "data" / "markets.json"
KST = timezone(timedelta(hours=9))
ET = ZoneInfo("America/New_York")   # 예측시장 마감은 미국 동부시간 기준으로 표기한다.
API = "https://gamma-api.polymarket.com"
# Kalshi Trade API — 공개 마켓 데이터는 API 키 없이 조회된다(계정·주문 API만 인증 필요).
# 두 호스트는 같은 응답을 주며, 앞의 호스트가 막히면 뒤의 호스트로 재시도한다.
KALSHI_BASES = (
    "https://external-api.kalshi.com/trade-api/v2",
    "https://api.elections.kalshi.com/trade-api/v2",
)
SOURCE_POLYMARKET = "Polymarket"
SOURCE_KALSHI = "Kalshi"
USER_AGENT = "YecheukpanBot/1.0 (Korean market-probability info site; contact: site owner)"

# 카테고리 정의 (프론트엔드 탭과 1:1 대응)
CATEGORIES = [
    {"id": "economy", "label": "경제·금리"},
    {"id": "crypto", "label": "코인·금융"},
    {"id": "ai", "label": "AI·테크"},
    {"id": "global", "label": "글로벌"},
]

# 후보 풀을 모을 때 쓰는 Polymarket 태그
TAG_SOURCES = [
    "economy", "fed", "crypto", "ai", "tech", "business",
    "geopolitics", "world", "big-tech", "finance", "macro",
]

# 대한민국 국내 정치·선거 관련 마켓은 싣지 않는다(운영 원칙).
KOREA_BLOCK = re.compile(
    r"(south\s*korea|korean\s+(president|election|politics)|seoul|kospi|"
    r"national\s+assembly\s+of\s+korea|\bwon\s+usd\b|bank\s+of\s+korea)",
    re.I,
)

# 사생활·성추문·가십성 스캔들 표현은 싣지 않는다(애드센스 정책·명예훼손 리스크).
# 규칙 본문은 scripts/content_filter.py 에 있고, 이슈 페이지 생성 스크립트도 같은 기준을 쓴다.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from content_filter import blocked_reason, is_blocked  # noqa: E402

# 필터에 걸러진 마켓 수(실행 로그로 남긴다).
GOSSIP_DROPPED: list[str] = []

# 자동 선별에서 제외할 스포츠·연예·SNS 잡음
NOISE_BLOCK = re.compile(
    r"(\bvs\.?\b|\bO/U\b|\bSpread:|win on \d{4}-\d{2}-\d{2}|"
    r"\b(?:UFC|NBA|NFL|MLB|NHL|ATP|WTA)\b|Grand Prix|Premier League|Champions League|"
    r"La Liga|Serie A|Super Bowl|Ballon d'Or|tweets? from|"
    r"next (head coach|manager)|American Idol|Grammy|Oscar)",
    re.I,
)

# 마켓 원문에 자주 나오는 고유명사 한국어 표기
GLOSSARY = [
    (r"\bBitcoin\b", "비트코인"), (r"\bBTC\b", "비트코인"), (r"\bEthereum\b", "이더리움"),
    (r"\bETH\b", "이더리움"), (r"\bSolana\b", "솔라나"), (r"\bSatoshi\b", "사토시"),
    (r"\bthe Fed\b", "연준"), (r"\bFed\b", "연준"), (r"\bFOMC\b", "FOMC"),
    (r"\bNVIDIA\b", "엔비디아"), (r"\bNvidia\b", "엔비디아"), (r"\bJensen Huang\b", "젠슨 황"),
    (r"\bJerome Powell\b", "제롬 파월"), (r"\bElon Musk\b", "일론 머스크"), (r"\bSam Altman\b", "샘 올트먼"),
    (r"\bApple\b", "애플"),
    (r"\bMicrosoft\b", "마이크로소프트"), (r"\bGoogle\b", "구글"), (r"\bAlphabet\b", "알파벳"),
    (r"\bAmazon\b", "아마존"), (r"\bMeta\b", "메타"), (r"\bTesla\b", "테슬라"),
    (r"\bOpenAI\b", "오픈AI"), (r"\bAnthropic\b", "앤트로픽"), (r"\bSpaceX\b", "스페이스X"),
    (r"\bTrump\b", "트럼프"), (r"\bPutin\b", "푸틴"), (r"\bZelenskyy?\b", "젤렌스키"),
    (r"\bNetanyahu\b", "네타냐후"), (r"\bIran\b", "이란"), (r"\bIsrael\b", "이스라엘"),
    (r"\bUkraine\b", "우크라이나"), (r"\bRussia\b", "러시아"), (r"\bChina\b", "중국"),
    (r"\bJapan\b", "일본"), (r"\bFrance\b", "프랑스"), (r"\bUnited States\b", "미국"),
    (r"\bStrait of Hormuz\b", "호르무즈 해협"), (r"\bCrude Oil\b", "국제유가"),
    (r"\bGold\b", "금"), (r"\bS&P ?500\b", "S&P500"), (r"\bNasdaq\b", "나스닥"),
]

MONTHS_EN = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], start=1)}


# ---------------------------------------------------------------------------
# 큐레이션 규칙
# ---------------------------------------------------------------------------
# q          : 마켓 질문(영문)에 대한 정규식
# option     : (선택) groupItemTitle 정규식 — 같은 이벤트의 하위 마켓을 구분할 때
# not_q      : (선택) 이 정규식에 걸리면 제외
# title      : 카드에 표시할 한국어 제목
# explain    : '이슈 배경' (2~3문장)
# watch      : '관전 포인트' (1~2문장)
# allow_extreme : 확률이 2% 미만·98% 초과여도 표시 허용
WATCH = [
    # ---------------- 경제·금리 ----------------
    dict(
        key="fed-dec-hike", cat="economy", rank=1, topic="fed-dec",
        q=r"increase interest rates by 25 bps after the December 2026 meeting",
        title="12월 FOMC, 기준금리 0.25%p 인상?",
        explain=(
            "미 연준(Fed)이 12월 8~9일 FOMC 회의에서 정책금리(연방기금금리 상단)를 0.25%p(25bp) "
            "올릴 확률입니다. YES 확률이 90%를 넘는다는 것은 시장 참가자 대다수가 인상을 기정사실로 "
            "보고 있다는 뜻으로, 이미 주가·채권금리·달러에 상당 부분 반영됐을 가능성이 큽니다."
        ),
        watch=(
            "확률이 95% 위로 더 올라가면 '재료 소진' 구간에 가까워지고, 반대로 80% 아래로 밀리면 "
            "인상 기대가 흔들리는 신호입니다. 12월 결과는 한국은행의 내년 1월 금리 판단에도 영향을 줍니다."
        ),
    ),
    dict(
        key="fed-hikes-2026-two", cat="economy", rank=6,
        q=r"Will 2 Fed rate hikes happen in 2026",
        title="2026년 연준 금리 인상, 두 차례?",
        explain=(
            "올해 연준이 기준금리를 두 번(누적 50bp) 올렸는지를 묻는 마켓입니다. 단일 회의 결과보다 "
            "연간 금리 경로를 보여주기 때문에, 채권·성장주 밸류에이션을 판단할 때 더 유용합니다."
        ),
        watch=(
            "12월 FOMC 인상 확률과 이 마켓의 확률이 함께 움직이는지 보세요. 두 확률이 벌어지면 "
            "연내 추가 인상 여부에 대한 기대가 갈리고 있다는 뜻입니다."
        ),
    ),
    dict(
        key="crude-ath", cat="economy", rank=4,
        q=r"Crude Oil reach a new all-time high by December 31",
        title="국제유가, 연말까지 사상 최고치?",
        explain=(
            "원유 선물이 연말 전에 사상 최고가를 다시 쓸 확률입니다. 확률이 한 자릿수에 머문다는 것은 "
            "시장이 유가 급등보다 현 수준 유지나 조정 쪽에 무게를 두고 있다는 뜻입니다."
        ),
        watch=(
            "호르무즈 해협·중동 리스크 마켓과 나란히 보세요. 공급 차질 확률은 오르는데 유가 신고가 "
            "확률이 따라오지 않으면, 시장이 공급 충격을 이미 가격에 반영했다는 해석이 가능합니다."
        ),
    ),
    dict(
        key="fed-dec-hold", cat="economy", rank=2, no_feature=True,
        q=r"no change in Fed interest rates after the December 2026 meeting",
        title="12월 FOMC, 금리 동결?",
        explain=(
            "12월 회의에서 금리를 그대로 두는(동결) 확률입니다. 인상 확률과 동결 확률을 더하면 100%에 "
            "가까워지므로, 두 마켓을 함께 보면 시장이 그리는 12월 결과 분포가 한눈에 들어옵니다."
        ),
        watch=(
            "동결 확률이 5%를 넘어서면 '인상 없이 간다'는 소수 의견이 커지는 신호로 읽을 수 있습니다."
        ),
    ),
    dict(
        key="fed-jan-hike", cat="economy", rank=3,
        q=r"increase interest rates by 25 bps after the January 2027 meeting",
        title="1월 FOMC, 추가 인상?",
        explain=(
            "2027년 1월 회의에서 연준이 기준금리를 0.25%p 더 올릴 확률입니다. 12월 인상이 기정사실화된 "
            "가운데 시장이 '연속 인상'을 어디까지 보는지 보여주는 지표입니다."
        ),
        watch=(
            "12월 인상 확률(92%대)보다 이 확률이 낮다면, 시장은 12월 이후 한 번 쉬어갈 가능성을 더 크게 "
            "보고 있다는 뜻입니다."
        ),
    ),
    dict(
        key="fed-hike-hike-hike", cat="economy", rank=6,
        q=r"Fed hike-hike-hike in the next three decisions",
        title="연준, 12월·1월·3월 연속 인상?",
        explain=(
            "12월·1월·3월 세 차례 회의에서 연준이 모두 금리를 올릴 확률입니다. 단일 회의 확률을 "
            "이어 붙인 '금리 경로' 관점이라, 장기 금리와 달러 방향을 가늠하는 데 쓰입니다."
        ),
        watch=(
            "연속 인상 확률이 34% 안팎이라는 것은 세 번 다 올리기보다 중간에 한 번 쉬어갈 것으로 "
            "보는 참가자가 더 많다는 뜻입니다."
        ),
    ),
    dict(
        key="fed-another-hike", cat="economy", rank=5,
        q=r"Another Fed rate hike in 2026",
        title="2026년 연준, 금리 한 번 더 인상?",
        explain=(
            "올해 남은 기간에 연준이 금리를 한 번 더 올릴 확률입니다. 12월 회의 한 번의 결과를 넘어 "
            "'연내 추가 인상' 가능성을 따로 본다는 점에서 금리 경로 기대를 확인하는 지표입니다."
        ),
        watch=(
            "12월 인상 확률과 거의 같다면 시장은 12월이 마지막 인상이라고 보고 있다는 뜻입니다."
        ),
    ),
    dict(
        key="fed-cuts-2026-zero", cat="economy", rank=7, allow_extreme=True,
        q=r"no Fed rate cuts happen in 2026",
        title="2026년 연준 금리 인하, 0회?",
        explain=(
            "올해 연준이 금리를 한 번도 내리지 않을 확률입니다. 98%대라면 연내 인하 기대가 사실상 "
            "소멸했다는 뜻으로, 위험자산 심리에 부담 요인입니다."
        ),
        watch=(
            "이 확률이 95% 아래로 내려오면 연내 인하 기대가 되살아나는 신호이므로 채권금리 하락과 "
            "함께 확인해 볼 만합니다."
        ),
    ),

    # ---------------- 코인·금융 ----------------
    dict(
        key="btc-60k-dec", cat="crypto", rank=1,
        q=r"Bitcoin dip to \$60,000 by December 31, 2026",
        title="비트코인, 연말까지 6만 달러 아래로?",
        explain=(
            "비트코인이 12월 31일까지 한 번이라도 6만 달러 아래로 내려갈 확률입니다. 가격을 '터치'하는지 "
            "묻는 방식이라 종가가 아니라 장중 저가 기준이라는 점이 중요합니다."
        ),
        watch=(
            "확률이 80%대라는 것은 추가 하락을 기본 시나리오로 본다는 뜻입니다. 50% 아래로 내려가면 "
            "반등 기대가 우세해진 것으로 읽습니다."
        ),
    ),
    dict(
        key="btc-50k-nov", cat="crypto", rank=2,
        q=r"Bitcoin dip to \$50,000 in November",
        title="비트코인, 11월에 5만 달러까지?",
        explain=(
            "11월 안에 5만 달러를 터치할 확률을 묻는 단기 마켓입니다. 만기가 짧을수록 확률 변동이 커서 "
            "단기 변동성 기대를 읽는 데 유용합니다."
        ),
        watch=(
            "한 자릿수 확률이 유지되면 급락에 대비한 헤지 수요가 크지 않다는 뜻입니다."
        ),
    ),
    dict(
        key="satoshi-move", cat="crypto", rank=3, allow_extreme=True,
        q=r"Satoshi move any Bitcoin in 2026",
        title="사토시 지갑, 올해 움직일까?",
        explain=(
            "비트코인 창시자로 알려진 사토시 나카모토의 지갑에서 올해 코인이 이동할 확률입니다. 실제로 "
            "일어나면 시장 전체에 충격을 줄 수 있는 이벤트라 확률은 낮지만 주목도가 높습니다."
        ),
        watch=(
            "2% 안팎이라는 것은 시장이 가능성을 거의 두지 않는다는 뜻입니다. 온체인에서 해당 지갑이 "
            "움직이면 이 확률이 급등합니다."
        ),
    ),
    dict(
        key="eth-3k-dec", cat="crypto", rank=4,
        q=r"Ethereum reach \$3,000 by December 31, 2026",
        title="이더리움, 연말 3,000달러 회복?",
        explain=(
            "이더리움이 연말까지 3,000달러를 다시 넘어설 확률입니다. 비트코인 마켓과 같은 기간으로 "
            "나란히 놓으면 알트코인의 상대 강도를 가늠할 수 있습니다."
        ),
        watch=(
            "이 확률이 비트코인 회복 확률보다 낮게 유지되면 알트코인 약세가 이어지고 있다는 신호입니다."
        ),
    ),

    # ---------------- AI·테크 ----------------
    dict(
        key="anthropic-2t", cat="ai", rank=1,
        q=r"Anthropic's valuation hit \(HIGH\) \$2\.0T by December 31",
        title="앤트로픽 기업가치, 2조 달러 돌파?",
        explain=(
            "AI 기업 앤트로픽이 연말까지 2조 달러 기업가치를 인정받을 확률입니다. 상장(IPO)과 투자 "
            "라운드가 겹쳐 있는 이슈라 AI 밸류에이션 논쟁의 바로미터로 쓰입니다."
        ),
        watch=(
            "1조 7,500억 달러 마켓과 2조 달러 마켓을 함께 보면 시장이 그리는 밸류에이션 분포가 보입니다."
        ),
    ),
    dict(
        key="best-model-google-dec", cat="ai", rank=2,
        q=r"Google have the best AI model at the end of December 2026",
        title="2026년 말 최고 AI 모델은 구글?",
        explain=(
            "연말 기준 가장 성능이 좋은 AI 모델을 보유한 회사를 묻는 마켓입니다. AI 반도체와 빅테크 "
            "주가가 '누가 앞서는가'에 민감하게 반응해, 투자 심리 지표로 유용합니다."
        ),
        watch=(
            "앤트로픽·오픈AI의 확률과 합쳐 보세요. 1위 확률이 한 회사로 쏠릴수록 경쟁 구도가 굳어지고 "
            "있다는 뜻입니다."
        ),
    ),
    dict(
        key="largest-company-apple", cat="ai", rank=3,
        q=r"Apple be the largest company in the world by market cap on December 31",
        title="연말 세계 시총 1위는 애플?",
        explain=(
            "12월 31일 기준 세계 시가총액 1위 기업이 애플일 확률입니다. 엔비디아·마이크로소프트 등 "
            "경쟁사의 확률과 함께 보면 빅테크 순위 경쟁 구도를 읽을 수 있습니다."
        ),
        watch=(
            "엔비디아 확률과의 격차가 벌어지면 AI 랠리 기대가 식고 있다는 신호로 해석할 수 있습니다."
        ),
    ),
    dict(
        key="anthropic-flip-btc", cat="ai", rank=4, allow_extreme=True,
        q=r"Anthropic flip BTC by December 31",
        title="앤트로픽, 비트코인 시총 추월?",
        explain=(
            "앤트로픽의 가치가 비트코인 전체 시가총액을 넘어서는지를 묻는 마켓입니다(원문: 'Will "
            "Anthropic flip BTC by December 31?'). AI 자산과 크립토 자산의 상대적 위상을 보여주는 "
            "상징적인 지표입니다."
        ),
        watch=(
            "99%대 확률은 시장이 이미 기정사실로 본다는 뜻입니다. 이 확률이 내려오면 비트코인 가격이 "
            "빠르게 반등하고 있다는 신호일 수 있습니다."
        ),
    ),

    # ---------------- 글로벌 ----------------
    dict(
        key="israel-iran-ceasefire", cat="global", rank=1,
        q=r"Israel x Iran ceasefire continues through December 31",
        title="이스라엘-이란 휴전, 연말까지 유지?",
        explain=(
            "이스라엘과 이란 간 휴전이 12월 31일까지 이어질 확률입니다. 중동 리스크는 유가·해운 운임·"
            "금리에 동시에 영향을 주기 때문에 글로벌 매크로의 핵심 변수입니다."
        ),
        watch=(
            "60%대라는 것은 휴전 유지와 재확대 가능성이 반반에 가깝다는 뜻입니다. 50% 아래로 내려가면 "
            "위험자산 회피 심리가 커질 수 있습니다."
        ),
    ),
    dict(
        key="russia-ukraine-ceasefire", cat="global", rank=2,
        q=r"Russia x Ukraine ceasefire agreement by December 31, 2026",
        not_q=r"energy",
        title="러시아-우크라이나 휴전 합의, 연말까지?",
        explain=(
            "러시아와 우크라이나가 연말까지 휴전에 합의할 확률입니다. 에너지 가격과 유럽 경기, 곡물 "
            "물가에 직결되는 이슈입니다."
        ),
        watch=(
            "에너지 휴전 마켓과 비슷한 수준이라면 시장은 '부분 합의' 가능성도 낮게 보고 있다는 뜻입니다."
        ),
    ),
    dict(
        key="lepen-france", cat="global", rank=3,
        q=r"Marine Le Pen win the 2027 French presidential election",
        title="2027 프랑스 대선, 르펜 당선?",
        explain=(
            "2027년 프랑스 대통령 선거에서 마린 르펜이 당선될 확률입니다. 유럽 재정·이민 정책과 EU "
            "통합 방향을 가르는 선거라 유럽 자산 투자자들이 주목합니다."
        ),
        watch=(
            "45% 안팎은 접전이라는 뜻입니다. 르펜 확률이 오르면 프랑스 국채 금리와 유로화 변동성도 "
            "함께 움직이는 경향이 있습니다."
        ),
    ),
    dict(
        key="hormuz-normal", cat="global", rank=4,
        q=r"Strait of Hormuz traffic returns to normal by December 31",
        title="호르무즈 해협 통항, 연말 정상화?",
        explain=(
            "호르무즈 해협의 선박 통항이 연말까지 정상으로 돌아올 확률입니다. 전 세계 원유·LNG 해상 "
            "물동량의 길목이라 유가와 해운 운임에 직접 영향을 줍니다."
        ),
        watch=(
            "3%대라는 것은 연내 정상화를 거의 기대하지 않는다는 뜻입니다. 이 확률이 오르면 유가에는 "
            "하락 요인으로 작용합니다."
        ),
    ),
    dict(
        key="us-invade-iran", cat="global", rank=5,
        q=r"U\.S\. invade Iran before 2027",
        title="미국, 2027년 전 이란 침공?",
        explain=(
            "미국이 2027년 이전에 이란을 침공할 확률입니다. 확률 자체는 낮지만, 이 시나리오가 가격에 "
            "반영되기 시작하면 유가·금·방산 자산이 먼저 반응합니다."
        ),
        watch=(
            "한 자릿수 확률이 유지되는지, 아니면 두 자릿수로 올라서는지가 핵심입니다. 휴전 유지 확률과 "
            "반대로 움직이는지 함께 확인하세요."
        ),
    ),
    dict(
        key="trump-out", cat="global", rank=6,
        q=r"Trump out as President before 2027",
        title="트럼프, 2027년 전 대통령직 이탈?",
        explain=(
            "도널드 트럼프 미국 대통령이 2027년 이전에 대통령직에서 물러날 확률입니다. 정치적 리스크를 "
            "'꼬리 위험'으로 가격에 반영하는 대표적인 마켓입니다."
        ),
        watch=(
            "2%대 확률은 시장이 거의 가능성을 두지 않는다는 뜻입니다. 이 확률이 오르면 미국 자산의 "
            "정치 리스크 프리미엄이 커지는 신호입니다."
        ),
    ),
    dict(
        key="putin-out", cat="global", rank=7,
        q=r"Putin out as President of Russia by December 31, 2026",
        title="푸틴, 연내 러시아 대통령직 이탈?",
        explain=(
            "블라디미르 푸틴 러시아 대통령이 연말까지 직에서 물러날 확률입니다. 낮은 확률이지만 러시아 "
            "정세 변화는 에너지·안보 자산에 큰 변동성을 만듭니다."
        ),
        watch=(
            "1%대 확률은 시장이 사실상 배제한다는 뜻입니다."
        ),
    ),
    dict(
        key="spacex-ipo", cat="global", rank=8, allow_extreme=True,
        q=r"SpaceX have the highest IPO Market Cap 2026",
        title="2026년 IPO 시총 1위는 스페이스X?",
        explain=(
            "2026년에 상장한 기업 중 첫날 시가총액 1위가 스페이스X일 확률입니다. 대형 IPO의 상장 규모는 "
            "AI·기술주 수급과 시장 유동성에 영향을 줍니다."
        ),
        watch=(
            "99%대라면 시장이 이미 기정사실로 본다는 뜻입니다. 앤트로픽·오픈AI IPO 마켓과 함께 보면 "
            "올해 상장 시장의 판도가 보입니다."
        ),
    ),
]

MIN_ITEMS = 8
TARGET_PER_CATEGORY = 4


# ---------------------------------------------------------------------------
# HTTP / 유틸
# ---------------------------------------------------------------------------
def http_json(url: str, tries: int = 3, timeout: int = 25):
    last_err = None
    for attempt in range(1, tries + 1):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
            })
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"HTTP {resp.status}")
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
            last_err = exc
            if attempt < tries:
                time.sleep(1.5 * attempt)
    print(f"  ! 요청 실패 {url} :: {last_err}", file=sys.stderr)
    return None


def parse_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_float_opt(value):
    """값이 없으면 None — 화면에서 '데이터 없음'으로 구분 표시하기 위해 쓴다."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def et_date(iso: str) -> str:
    """UTC 타임스탬프를 미국 동부시간 날짜(YYYY-MM-DD)로 바꾼다."""
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(ET)
        # 00:00 정각 종료는 '전날 자정 마감'으로 본다(예: 12/31 23:59 종료와 같은 날짜).
        if dt.hour == 0 and dt.minute == 0 and dt.second == 0:
            dt = dt - timedelta(seconds=60)
        return dt.date().isoformat()
    except ValueError:
        return iso[:10]


def parse_json_list(value):
    if isinstance(value, list):
        return value
    if not value:
        return []
    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []


def norm_market(market: dict, event: dict) -> dict | None:
    """Gamma API 마켓 하나를 내부 표현으로 정규화한다. YES/NO 2지선다만 남긴다."""
    outcomes = parse_json_list(market.get("outcomes"))
    prices = parse_json_list(market.get("outcomePrices"))
    if len(outcomes) != 2 or len(prices) != 2:
        return None
    if [str(o).strip().lower() for o in outcomes] != ["yes", "no"]:
        return None
    if market.get("closed") or not market.get("active", True):
        return None
    if market.get("archived"):
        return None

    yes = parse_float(prices[0])
    if not (0.0 <= yes <= 1.0):
        return None

    question = (market.get("question") or "").strip()
    if not question:
        return None

    tags = []
    for t in (event.get("tags") or []):
        if isinstance(t, dict) and t.get("slug"):
            tags.append(t["slug"])

    return {
        "mid": str(market.get("id")),
        "condition_id": market.get("conditionId") or "",
        "question": question,
        "option": (market.get("groupItemTitle") or "").strip(),
        "event_id": str(event.get("id") or ""),
        "event_title": (event.get("title") or "").strip(),
        "event_slug": (event.get("slug") or "").strip(),
        "yes": yes,
        "no": parse_float(prices[1]),
        "volume_total": parse_float(market.get("volumeNum") or market.get("volume")),
        "volume_24h": parse_float(market.get("volume24hr")),
        "liquidity": parse_float(market.get("liquidityNum") or market.get("liquidity")),
        "end_date": et_date(market.get("endDate") or ""),
        "end_iso": market.get("endDate") or "",
        "change_24h": parse_float(market.get("oneDayPriceChange")) * 100.0,
        "change_1w": parse_float(market.get("oneWeekPriceChange")) * 100.0,
        "change_1m": (lambda v: None if v is None else v * 100.0)(
            parse_float_opt(market.get("oneMonthPriceChange"))),
        "tags": tags,
        "slug": market.get("slug") or "",
    }


def build_pool(events_per_tag: int = 45) -> dict:
    """태그별 인기 이벤트에서 마켓 후보를 모은다. 마켓 id 기준 중복 제거."""
    pool: dict[str, dict] = {}
    for tag in TAG_SOURCES:
        url = (f"{API}/events?tag_slug={urllib.parse.quote(tag)}&closed=false&active=true"
               f"&limit={events_per_tag}&order=volume24hr&ascending=false")
        events = http_json(url)
        if not events:
            continue
        for ev in events:
            for mk in (ev.get("markets") or []):
                row = norm_market(mk, ev)
                if not row:
                    continue
                if KOREA_BLOCK.search(row["question"]) or KOREA_BLOCK.search(row["event_title"]):
                    continue
                gossip = blocked_reason(row["question"], row["event_title"])
                if gossip:
                    if row["question"] not in GOSSIP_DROPPED:
                        GOSSIP_DROPPED.append(row["question"])
                        print(f"  · 가쉽·스캔들 제외('{gossip}'): {row['question'][:80]}")
                    continue
                prev = pool.get(row["mid"])
                if prev is None:
                    row["tags"] = sorted(set(row["tags"] + [tag]))
                    pool[row["mid"]] = row
                else:
                    prev["tags"] = sorted(set(prev["tags"] + [tag]))
                    if row["volume_24h"] > prev["volume_24h"]:
                        prev["volume_24h"] = row["volume_24h"]
        print(f"  · tag {tag}: 누적 후보 {len(pool)}개")
    return pool


def find_market(pool: dict, rule: dict) -> dict | None:
    pattern = re.compile(rule["q"], re.I)
    not_pattern = re.compile(rule["not_q"], re.I) if rule.get("not_q") else None
    best = None
    for row in pool.values():
        if not pattern.search(row["question"]):
            continue
        if not_pattern and not_pattern.search(row["question"]):
            continue
        if is_blocked(row["question"], row["event_title"]):
            continue
        if rule.get("option") and not re.search(rule["option"], row["option"], re.I):
            continue
        if best is None or row["volume_24h"] > best["volume_24h"]:
            best = row
    return best


# ---------------------------------------------------------------------------
# 자동 선별(큐레이션 매칭이 모자랄 때)
# ---------------------------------------------------------------------------
def konglish(text: str) -> str:
    out = text
    for pattern, korean in GLOSSARY:
        out = re.sub(pattern, korean, out)
    return out


MONTH_KO = {
    "january": "1", "february": "2", "march": "3", "april": "4", "may": "5", "june": "6",
    "july": "7", "august": "8", "september": "9", "october": "10", "november": "11", "december": "12",
}


def kdate(text: str) -> str:
    """영문 날짜 표기를 한국어로 바꾼다. 'December 31, 2026' → '2026년 12월 31일'."""
    def rep(m: re.Match) -> str:
        mon = m.group("mon").lower()
        day = int(m.group("day"))
        year = m.group("year")
        if mon not in MONTH_KO:
            return m.group(0)
        return f"{year}년 {MONTH_KO[mon]}월 {day}일" if year else f"{MONTH_KO[mon]}월 {day}일"

    out = re.sub(
        r"\b(?P<mon>January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+(?P<year>\d{4})\b",
        lambda m: f"{m.group('year')}년 {MONTH_KO.get(m.group('mon').lower(), '?')}월",
        text, flags=re.I)
    out = re.sub(
        r"\b(?P<mon>January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+(?P<day>\d{1,2})(?!\d)(?:,\s*(?P<year>\d{4}))?",
        rep, out, flags=re.I)
    # 'by 2026년 12월 31일' 처럼 한국어 날짜 앞에 남은 전치사를 거둔다.
    out = re.sub(r"\s+by\s+(?=\d{4}년)", " ", out)
    # 날짜 없이 홀로 남은 월 이름('in November')도 한국어로 바꾼다.
    out = re.sub(
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\b",
        lambda m: f"{MONTH_KO[m.group(1).lower()]}월", out, flags=re.I)
    return out


def strip_will(text: str) -> str:
    """제목 앞의 'Will '을 덜어 문장을 짧고 자연스럽게 만든다."""
    return re.sub(r"^\s*will\s+(?!there\b)", "", text, flags=re.I)


def auto_title(row: dict) -> str:
    """큐레이션에 없는 새 마켓용 간단 한국어 제목 생성(베스트 에포트)."""
    q = row["question"]
    base = q.rstrip("?")

    # 자주 나오는 문형은 한국어 문장으로 옮긴다.
    m = re.search(r"^(?:will\s+)?(.+?) be the largest company in the world by market cap on (.+)$", base, re.I)
    if m:
        return f"{konglish(strip_will(m.group(1))).strip()}, {kdate(m.group(2))}까지 세계 시가총액 1위?"
    m = re.search(r"^(?:will\s+)?(.+?) announced resignation or removal again by (.+)$", base, re.I)
    if m:
        return f"{konglish(strip_will(m.group(1))).strip()} 퇴진·해임, {kdate(m.group(2))}까지?"

    m = re.search(r"reach[s]? \$([\d,\.]+[KMB]?) (?:by|in|on) (.+)$", base, re.I)
    if m:
        return f"{konglish(strip_will(base[:m.start()])).strip()}, {kdate(m.group(2))}까지 ${m.group(1)} 도달?"
    m = re.search(r"dip to \$([\d,\.]+[KMB]?) (?:by|in|on) (.+)$", base, re.I)
    if m:
        return f"{konglish(strip_will(base[:m.start()])).strip()}, {kdate(m.group(2))}까지 ${m.group(1)} 아래로?"
    m = re.search(r"be above \$([\d,\.]+[KMB]?) on (.+)$", base, re.I)
    if m:
        return f"{konglish(strip_will(base[:m.start()])).strip()}, {kdate(m.group(2))} ${m.group(1)} 이상?"
    title = kdate(konglish(strip_will(base)))
    return title if title.endswith("?") else f"{title}?"


def auto_explain(row: dict, cat_label: str) -> str:
    parts = [
        f"{cat_label} 분야의 글로벌 예측시장 마켓으로, 원문 질문은 \"{row['question']}\"입니다.",
        "표시된 확률은 이 마켓에 참여한 전 세계 참가자들이 매긴 기대값(0~100%)이며, "
        "확률 60%는 '60%의 확률로 일어난다'와 같은 의미로 읽으면 됩니다.",
    ]
    if abs(row["change_24h"]) >= 1:
        direction = "상승" if row["change_24h"] > 0 else "하락"
        parts.append(f"최근 24시간 동안 YES 확률이 {abs(row['change_24h']):.1f}%p {direction}했습니다.")
    return " ".join(parts)


def build_auto(row: dict, cat_id: str) -> dict:
    cat_label = next(c["label"] for c in CATEGORIES if c["id"] == cat_id)
    rule = {
        "key": f"auto-{row['mid']}",
        "cat": cat_id,
        "title": auto_title(row),
        "explain": auto_explain(row, cat_label),
        "watch": (
            "큐레이션 해설이 아직 붙지 않은 마켓입니다. 거래량과 확률 변화 폭을 함께 보면 "
            "시장 참가자들이 얼마나 빠르게 기대를 바꾸는지 가늠할 수 있습니다."
        ),
    }
    item = format_item(rule, row)
    item["auto"] = True
    return item


def pick_auto(pool: dict, cat: str, used: set[str]) -> dict | None:
    """카테고리 태그가 맞고 잡음이 아닌 마켓 중 거래량이 큰 것 하나."""
    tag_map = {
        "economy": {"economy", "fed", "macro", "finance"},
        # 'finance' 공통 태그만 달린 마켓(예: CEO 거취)이 코인 탭에 오지 않도록
        # 코인 탭은 실제 코인 자산 태그만 받는다.
        "crypto": {"crypto", "bitcoin", "ethereum", "crypto-prices"},
        "ai": {"ai", "tech", "big-tech", "business"},
        "global": {"geopolitics", "world", "politics"},
    }[cat]
    best = None
    for row in pool.values():
        if row["mid"] in used:
            continue
        if not (set(row["tags"]) & tag_map):
            continue
        if NOISE_BLOCK.search(row["question"]) or NOISE_BLOCK.search(row["event_title"]):
            continue
        if is_blocked(row["question"], row["event_title"]):
            continue
        if row["yes"] < 0.02 or row["yes"] > 0.98:
            continue
        if row["volume_24h"] < 3000:
            continue
        if best is None or row["volume_24h"] > best["volume_24h"]:
            best = row
    return best


# ---------------------------------------------------------------------------
# 아이템 조립
# ---------------------------------------------------------------------------
def format_item(rule: dict, row: dict) -> dict:
    return {
        "key": rule["key"],
        "category": rule["cat"],
        "rank": rule.get("rank", 90),
        "no_feature": bool(rule.get("no_feature")),
        "title": rule["title"],
        "source": SOURCE_POLYMARKET,
        "source_key": "polymarket",
        "open_interest": None,
        # 브라우저(app.js)가 Gamma API를 직접 호출해 실시간 확률을 덮어쓸 때 쓰는 식별자.
        "mid": row["mid"],
        "slug": row.get("slug", ""),
        "condition_id": row.get("condition_id", ""),
        "question": row["question"],
        "option": row["option"],
        "event_title": row["event_title"],
        "yes": round(row["yes"] * 100, 1),
        "no": round((1 - row["yes"]) * 100, 1),
        "change_24h": round(row["change_24h"], 1),
        "change_1w": round(row["change_1w"], 1),
        "change_1m": None if row.get("change_1m") is None else round(row["change_1m"], 1),
        "volume_24h": int(round(row["volume_24h"])),
        "volume_total": int(round(row["volume_total"])),
        "liquidity": int(round(row["liquidity"])),
        "end_date": row["end_date"],
        "end_iso": row.get("end_iso", ""),
        "explain": rule["explain"],
        "watch": rule.get("watch", ""),
        "auto": False,
    }


def score(item: dict) -> float:
    """TOP 3 선정 점수: 거래량 + 확률이 팽팽할수록 가중."""
    tightness = 1 - abs(item["yes"] - 50) / 50          # 0(한쪽 쏠림) ~ 1(반반)
    return (float(item.get("volume_24h") or 0) + 0.01 * float(item.get("open_interest") or 0)) \
        * (1 + 0.8 * tightness)


def pick_featured(items: list[dict], limit: int = 3) -> list[str]:
    # 해설이 붙은 큐레이션 항목을 먼저, 자동 선별(auto) 항목은 뒤로 — TOP 3는 해설 품질 우선.
    ranked = sorted(items, key=lambda it: (bool(it.get("auto")), not it.get("no_feature"), -score(it)))
    ranked = [it for it in ranked if not it.get("no_feature")]
    chosen, per_cat = [], {}
    # 1차: 카테고리 다양성 확보
    for item in ranked:
        if len(chosen) >= limit:
            break
        if per_cat.get(item["category"], 0) >= 1:
            continue
        chosen.append(item["key"])
        per_cat[item["category"]] = per_cat.get(item["category"], 0) + 1
    # 2차: 남는 자리는 점수 순서대로
    for item in ranked:
        if len(chosen) >= limit:
            break
        if item["key"] not in chosen:
            chosen.append(item["key"])

    # 3차: TOP 3가 한 출처로만 채워졌으면, 다른 출처(보통 Kalshi) 항목 하나를 끼워
    #      '여러 글로벌 지표를 종합한다'는 사실이 첫 화면에서 보이게 한다.
    by_key = {it["key"]: it for it in ranked}
    chosen_items = [by_key[k] for k in chosen if k in by_key]
    sources = {it.get("source") for it in chosen_items}
    if len(chosen_items) >= 2 and len(sources) == 1:
        floor = score(chosen_items[-1]) * 0.25
        alts = [it for it in ranked
                if it["key"] not in chosen and it.get("source") not in sources and score(it) >= floor]
        if alts:
            alt = max(alts, key=score)
            # 자동 선별 항목이 있으면 그 자리를 먼저 내주고, 없으면 마지막 자리를 바꾼다.
            auto_pos = next((i for i in range(len(chosen) - 1, -1, -1)
                             if by_key.get(chosen[i], {}).get("auto")), None)
            chosen[auto_pos if auto_pos is not None else len(chosen) - 1] = alt["key"]
    return chosen


# ---------------------------------------------------------------------------
# Kalshi (미국 CFTC 인가 예측시장) 공개 데이터
# ---------------------------------------------------------------------------
# Kalshi 는 시리즈(series) 단위로 마켓을 열고, 시리즈마다 성격이 다르다.
#  · pick="winner" : 후보가 여럿인 경쟁 마켓(FOMC 결과, 최고 AI 모델, 차기 CEO) → 확률 1위
#  · pick="ladder" : "몇 % 이상" 처럼 임계값이 계단으로 놓인 마켓 → 확률이 50%에 가장 가까운 칸
#  · pick="bucket" : 가격 구간 마켓 → 확률이 가장 높은 구간
# title 함수가 None 을 돌려주면 일반 번역(auto_title)으로 물러난다.
KALSHI_PER_CATEGORY = 3      # 카테고리당 Kalshi 항목 수(기존 Polymarket 4개에 더한다)
KALSHI_PAGE_LIMIT = 200      # /events 한 번에 최대 200개
KALSHI_MAX_PAGES = 10        # 최대 2,000개 이벤트까지 훑는다
KALSHI_TOP_N = 40            # 후보 상위 40개 이벤트
KALSHI_MIN_VOLUME_24H = 1000  # 24시간 거래 계약 수가 이보다 적으면 제외
KALSHI_MAX_SPREAD = 0.10     # 매수·매도 호가 차이가 10%p 이하일 때만 중간값을 확률로 사용
KALSHI_MIN_HORIZON_H = 48    # 15분·1시간짜리 초단기 마켓은 카드·SEO 페이지로 쓰지 않는다

# Kalshi 카테고리 → 예측판 카테고리 (여기에 없는 Sports·Elections·Entertainment 등은 제외)
KALSHI_CATEGORY_MAP = {
    "Economics": "economy",
    "Financials": "crypto",
    "Crypto": "crypto",
    "Science and Technology": "ai",
    "Companies": "ai",
    "World": "global",
    "Politics": "global",
}


def k_usd(raw: str) -> str:
    try:
        n = round(float(str(raw).replace(",", "").replace("$", "")))
    except (TypeError, ValueError):
        return str(raw)
    return f"${n:,}"


def k_num(raw: str) -> str:
    """'3.5%' / '0' 같은 임계값 표기를 그대로 다듬는다."""
    return str(raw).strip()


def k_period(ev: dict) -> str:
    """'CPI YoY in November' / 'In Nov 2026' → '11월'."""
    text = f"{ev.get('title', '')} {ev.get('sub_title', '')}"
    m = re.search(r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
                  r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\b",
                  text, re.I)
    if not m:
        return ""
    name = m.group(1).lower()[:3]
    num = next((v for full, v in MONTHS_EN.items() if full[:3] == name), 0)
    return f"{num}월" if num else ""


def k_quarter(ev: dict) -> str:
    """'Q4 2026' → '2026년 4분기'."""
    m = re.search(r"Q([1-4])\s*(\d{4})", f"{ev.get('title', '')} {ev.get('sub_title', '')}")
    return f"{m.group(2)}년 {m.group(1)}분기" if m else ""


def k_bucket(sub: str) -> str:
    """'20,000 to 24,999.99' → '$20,000~$25,000 구간'."""
    m = re.match(r"\s*([\d,.]+)\s*(?:to|-)\s*([\d,.]+)", sub)
    if m:
        return f"{k_usd(m.group(1))}~{k_usd(m.group(2))} 구간"
    m = re.match(r"\s*([\d,.]+)\s*or (?:below|less)", sub, re.I)
    if m:
        return f"{k_usd(m.group(1))} 이하"
    m = re.match(r"\s*([\d,.]+)\s*or (?:above|more)", sub, re.I)
    if m:
        return f"{k_usd(m.group(1))} 이상"
    return sub


def k_above(sub: str) -> str:
    """'Above $99,999.99' → '$100,000', 'Above 3.5%' → '3.5%', 'Above 25,000' → '25,000'."""
    m = re.match(r"\s*above\s+(.+)$", sub, re.I)
    if not m:
        return k_num(sub)
    val = m.group(1).strip()
    return k_usd(val) if val.startswith("$") else val


def k_below(sub: str) -> str:
    m = re.match(r"\s*below\s+(.+)$", sub, re.I)
    if not m:
        return k_num(sub)
    val = m.group(1).strip()
    return k_usd(val) if val.startswith("$") else val


def k_date_str(text: str) -> str:
    """'Jul 1, 2028' → '2028년 7월 1일', '2028' → '2028년'."""
    text = text.strip()
    if re.fullmatch(r"\d{4}", text):
        return f"{text}년"
    m = re.search(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2}),?\s*(\d{4})", text)
    if not m:
        return text
    num = next((v for full, v in MONTHS_EN.items() if full[:3] == m.group(1).lower()[:3]), 0)
    return f"{m.group(3)}년 {num}월 {int(m.group(2))}일" if num else text


def k_date_key(sub: str):
    """'Before Jul 1, 2028' → (2028, 7, 1), 'Before 2028' → (2028, 12, 31)."""
    m = re.search(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2}),?\s*(\d{4})", sub)
    if m:
        num = next((v for full, v in MONTHS_EN.items() if full[:3] == m.group(1).lower()[:3]), 0)
        return (int(m.group(3)), num, int(m.group(2)))
    m = re.search(r"\b(\d{4})\b", sub)
    return (int(m.group(1)), 12, 31) if m else (9999, 0, 0)


def k_before(sub: str) -> str:
    """'Before Jul 1, 2028' → '2028년 7월 1일'. 그 외에는 원문 그대로."""
    m = re.match(r"\s*before\s+(.+)$", sub, re.I)
    return k_date_str(m.group(1)) if m else k_num(sub)


def k_kr_date(ev: dict) -> str:
    """이벤트 부제 'On Dec 9, 2026' → '2026년 12월 9일'."""
    text = f"{ev.get('sub_title', '')} {ev.get('title', '')}"
    m = re.search(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2}),?\s*(\d{4})", text)
    if not m:
        return k_period(ev)
    num = next((v for full, v in MONTHS_EN.items() if full[:3] == m.group(1).lower()[:3]), 0)
    return f"{m.group(3)}년 {num}월 {int(m.group(2))}일" if num else k_period(ev)


# 시리즈별 한국어 제목·해설 템플릿. 표에 없는 시리즈는 자동 번역(auto_title)으로 넘긴다.
#  · pick="winner" : 후보가 여럿인 경쟁 마켓(FOMC 결과, 최고 AI 모델) → 확률 1위
#  · pick="ladder" : "몇 % 이상" 임계값 계단 → 확률이 50%에 가장 가까운 칸
#  · pick="bucket" : 가격 구간 마켓 → 확률이 가장 높은 구간
#  · pick="soonest": "언제까지" 누적 사다리 → 확률이 두 자릿수가 되는 가장 이른 시점
KALSHI_SERIES = [
    # ---------------- 경제·금리 ----------------
    dict(
        ticker="KXFEDDECISION", cat="economy", pick="winner", topic="fed-dec",
        title=lambda ev, mk: (lambda o: f"{k_period(ev)} FOMC, {o}" if o else None)({
            "Hike 25bps": "금리 0.25%p 인상?", "Fed maintains rate": "금리 동결?",
            "Cut 25bps": "금리 0.25%p 인하?", "Hike >25bps": "0.25%p 넘는 인상?",
            "Cut >25bps": "0.25%p 넘는 인하?",
        }.get((mk.get("yes_sub_title") or "").strip())),
        explain=("미 연준(FOMC)이 이번 회의에서 기준금리를 어느 폭으로 움직일지를 두고 시장 참가자들이 매긴 확률입니다. "
                 "미국 CFTC가 인가한 Kalshi에서 거래되는 마켓으로, 금리·달러·주가 기대가 한 줄로 모이는 지표입니다."),
        watch=("인상 확률이 90%를 넘으면 결과가 이미 가격에 반영된 '재료 소진' 구간에 가깝습니다. "
               "동결·인하 확률이 함께 오르는지 보면 시장이 연준의 다음 수를 어떻게 보는지 알 수 있습니다."),
    ),
    dict(
        ticker="KXFED", cat="economy", pick="ladder",
        title=lambda ev, mk: f"{k_period(ev)} FOMC 뒤 기준금리 {k_above(mk.get('yes_sub_title') or '')} 이상?",
        explain=("FOMC 직후 연방기금금리 상단이 특정 수준을 넘는지를 묻는 마켓입니다. "
                 "임계값별 확률을 늘어놓으면 시장이 그리는 금리 분포가 보입니다."),
        watch=("여러 임계값 가운데 확률이 50%에 가장 가까운 지점이 시장의 중심 예상입니다. "
               "그 값이 회의 때마다 어디로 이동하는지가 핵심입니다."),
    ),
    dict(
        ticker="KXCPIYOY", cat="economy", pick="ladder",
        title=lambda ev, mk: f"{k_period(ev)} 미국 CPI 상승률 {k_above(mk.get('yes_sub_title') or '')} 초과?",
        explain=("미국 소비자물가(CPI) 상승률이 발표 기준으로 특정 수준을 넘는지를 묻는 마켓입니다. "
                 "금리 기대가 CPI 발표 하루에 크게 흔들리기 때문에 매크로 투자자들이 주목합니다."),
        watch=("확률이 50%에 가까운 임계값이 시장의 물가 전망입니다. 발표 전후로 같은 임계값의 확률이 "
               "얼마나 움직였는지 비교해 보세요."),
    ),
    dict(
        ticker="KXRATECUTCOUNT", cat="economy", pick="winner",
        title=lambda ev, mk: (lambda n: f"올해 연준 금리 인하, {n}회?" if n is not None else None)(
            (lambda m: m.group(1) if m else None)(
                re.match(r"\s*Exactly\s+(\d+)\s+cuts?", (mk.get("yes_sub_title") or ""), re.I))),
        explain=("연준이 한 해 동안 금리를 몇 번 내릴지를 묻는 마켓입니다. "
                 "단일 회의 결과를 넘어 연간 금리 경로 전체를 하나의 숫자로 요약합니다."),
        watch=("0회 확률이 98%라면 연내 인하 기대가 사실상 사라진 상태입니다. "
               "이 확률이 내려오면 위험자산 심리가 살아나는 신호로 읽을 수 있습니다."),
    ),
    dict(
        ticker="KXPAYROLLS", cat="economy", pick="ladder",
        title=lambda ev, mk: f"{k_period(ev)} 미국 고용, {k_above(mk.get('yes_sub_title') or '')}명 초과 증가?",
        explain=("미국 비농업 고용지표에서 몇 명 이상의 일자리가 늘었는지를 묻는 마켓입니다. "
                 "고용은 연준이 금리를 정할 때 보는 두 축(물가·고용) 중 하나입니다."),
        watch=("임계값 여러 개 중 확률이 50% 근처인 지점이 시장의 예상 고용치입니다. "
               "발표 뒤 이 확률이 어떻게 재배치되는지가 다음 금리 기대를 보여 줍니다."),
    ),
    dict(
        ticker="KXGDP", cat="economy", pick="ladder",
        title=lambda ev, mk: f"{k_quarter(ev)} 미국 GDP 성장률 {k_above(mk.get('yes_sub_title') or '')} 초과?",
        explain=("미국 실질 GDP 성장률이 분기 기준으로 특정 수준을 넘는지를 묻는 마켓입니다. "
                 "경기 둔화·연착륙 논쟁을 숫자로 확인할 수 있습니다."),
        watch=("2%대 임계값의 확률이 50%를 크게 벗어나면 시장이 경기 방향을 한쪽으로 굳혔다고 볼 수 있습니다."),
    ),
    dict(
        ticker="KXU3", cat="economy", pick="ladder",
        title=lambda ev, mk: f"{k_period(ev)} 미국 실업률 {k_above(mk.get('yes_sub_title') or '')} 초과?",
        explain=("미국 실업률(U-3)이 특정 수준을 넘는지를 묻는 마켓입니다. 고용시장이 식는 속도를 확률로 보여 줍니다."),
        watch=("실업률 임계값 확률이 한 달 새 위로 이동하면 경기 둔화 우려가 커진 것으로 읽습니다."),
    ),

    # ---------------- 코인·금융 ----------------
    dict(
        ticker="KXBTCY", cat="crypto", pick="bucket",
        title=lambda ev, mk: f"{k_kr_date(ev)} 비트코인 가격, {k_bucket(mk.get('yes_sub_title') or '')}?",
        explain=("연말 시점 비트코인 가격이 어느 구간에 있을지를 묻는 Kalshi 마켓입니다. "
                 "구간별 확률을 모두 더하면 시장이 그리는 가격 분포가 됩니다."),
        watch=("확률이 가장 높은 구간이 시장의 중심값입니다. 한 달 전과 비교해 분포가 위·아래 어느 쪽으로 "
               "이동했는지 보세요."),
    ),
    dict(
        ticker="KXBTCMAXY", cat="crypto", pick="ladder",
        title=lambda ev, mk: f"비트코인, 연말까지 {k_above(mk.get('yes_sub_title') or '')} 돌파?",
        explain=("비트코인이 연말까지 어디까지 오를지를 임계값별로 묻는 마켓입니다. "
                 "가장 가까운 임계값의 확률이 곧 '연내 추가 상승 가능성'을 시장이 보는 정도입니다."),
        watch=("가장 낮은 임계값의 확률이 1%대라면 시장은 연내 큰 반등을 거의 기대하지 않는다는 뜻입니다."),
    ),
    dict(
        ticker="KXBTCMINY", cat="crypto", pick="ladder",
        title=lambda ev, mk: f"비트코인, 연내 {k_below(mk.get('yes_sub_title') or '')} 아래로?",
        explain=("비트코인이 연말까지 어디까지 내려갈지를 묻는 마켓입니다. 하방 위험을 확률로 보여 줍니다."),
        watch=("확률이 50%에 가까운 임계값이 시장이 보는 최저점입니다. 이 값이 위로 올라가면 하락 위험을 "
               "더 크게 본다는 뜻입니다."),
    ),
    dict(
        ticker="KXETHY", cat="crypto", pick="bucket",
        title=lambda ev, mk: f"{k_kr_date(ev)} 이더리움 가격, {k_bucket(mk.get('yes_sub_title') or '')}?",
        explain=("연말 시점 이더리움 가격이 어느 구간에 있을지를 묻는 Kalshi 마켓입니다. "
                 "비트코인 마켓과 나란히 보면 알트코인의 상대 강도를 가늠할 수 있습니다."),
        watch=("확률이 가장 높은 구간이 시장의 중심값입니다. 비트코인 분포와 비교해 어느 쪽으로 더 쏠려 있는지 "
               "확인해 보세요."),
    ),
    dict(
        ticker="KXETHMAXY", cat="crypto", pick="ladder",
        title=lambda ev, mk: f"이더리움, 연말까지 {k_above(mk.get('yes_sub_title') or '')} 돌파?",
        explain=("이더리움이 연말까지 어디까지 오를지를 임계값별로 묻는 마켓입니다."),
        watch=("가장 낮은 임계값의 확률이 한 자릿수면 시장은 연내 큰 반등을 거의 보지 않는다는 뜻입니다."),
    ),
    dict(
        ticker="KXETHMINY", cat="crypto", pick="ladder",
        title=lambda ev, mk: f"이더리움, 연내 {k_below(mk.get('yes_sub_title') or '')} 아래로?",
        explain=("이더리움이 연말까지 어디까지 내려갈지를 묻는 마켓입니다."),
        watch=("확률이 50%에 가까운 임계값이 시장이 보는 최저점입니다."),
    ),

    # ---------------- AI·테크 ----------------
    dict(
        ticker="KXLLM1", cat="ai", pick="winner",
        title=lambda ev, mk: f"{k_kr_date(ev)} 기준 최고 AI 모델은 {k_vendor(mk.get('yes_sub_title') or '')}?",
        explain=("월말 또는 연말 기준으로 가장 성능이 좋은 AI를 고르는 Kalshi 마켓입니다. "
                 "AI 모델 순위는 빅테크 주가와 AI 밸류에이션 논쟁에 바로 연결됩니다."),
        watch=("1위 확률이 한 회사로 쏠릴수록 경쟁 구도가 굳어졌다는 뜻입니다. "
               "2위 확률의 변화가 다음 분기 판도를 보여 줍니다."),
    ),
    dict(
        ticker="KXTOPMODEL", cat="ai", pick="winner",
        title=lambda ev, mk: f"{k_period(ev)} 최고 AI 모델은 {k_vendor(mk.get('yes_sub_title') or '')}?",
        explain=("이번 달 가장 성능이 좋은 AI 모델을 고르는 마켓입니다. 모델 순위 변동은 AI 경쟁 구도를 "
                 "가장 빠르게 보여 주는 지표입니다."),
        watch=("1위 확률이 80%를 넘으면 경쟁이 잠시 굳은 상태입니다. 새 모델 발표가 나오면 확률이 급하게 "
               "재배치됩니다."),
    ),
    dict(
        ticker="KXCODINGMODEL", cat="ai", pick="winner",
        title=lambda ev, mk: f"최고 AI 코딩 모델은 {k_vendor(mk.get('yes_sub_title') or '')}?",
        explain=("코딩·개발 작업에서 가장 앞선 AI 모델을 고르는 마켓입니다. 개발자 도구 시장의 판도를 보여 줍니다."),
        watch=("1위 확률과 2위 확률의 격차가 좁아지는지가 경쟁의 방향을 알려 줍니다."),
    ),
    dict(
        ticker="KXSPACEXCOUNT", cat="ai", pick="ladder",
        title=lambda ev, mk: f"스페이스X 올해 발사 횟수, {k_above(mk.get('yes_sub_title') or '')}회 이상?",
        explain=("스페이스X가 올해 몇 번 발사할지를 묻는 마켓입니다. 발사 횟수는 위성 인터넷·우주 수송 사업의 "
                 "진행 속도를 보여 주는 지표입니다."),
        watch=("누적 발사 횟수가 임계값에 가까워질수록 확률이 0 또는 100으로 빠르게 수렴합니다."),
    ),
    dict(
        ticker="KXOPENSHARE", cat="ai", pick="ladder",
        title=lambda ev, mk: f"오픈AI 시장점유율 {k_above(mk.get('yes_sub_title') or '')} 이상?",
        explain=("오픈AI가 AI 시장에서 차지하는 점유율이 특정 수준을 넘는지를 묻는 마켓입니다."),
        watch=("점유율 임계값 확률이 아래로 내려가면 경쟁사가 그만큼 몫을 가져간다는 뜻입니다."),
    ),

    # ---------------- 글로벌 ----------------
    dict(
        ticker="KXHORMUZNORM", cat="global", pick="soonest",
        title=lambda ev, mk: f"호르무즈 해협 통항, {k_before(mk.get('yes_sub_title') or '')}까지 정상화?",
        explain=("호르무즈 해협 통항이 언제 정상으로 돌아올지를 시점별로 묻는 Kalshi 마켓입니다. "
                 "전 세계 원유·LNG 물동량의 길목이라 유가·해운 운임에 직접 영향을 줍니다."),
        watch=("확률이 처음으로 두 자릿수가 되는 시점이 시장이 보는 정상화의 하한선입니다."),
    ),
    dict(
        ticker="KXUSAIRANAGREEMENT", cat="global", pick="soonest",
        title=lambda ev, mk: f"미국-이란 핵 합의, {k_before(mk.get('yes_sub_title') or '')}까지?",
        explain=("미국과 이란의 핵 합의가 언제까지 성사될지를 시점별로 묻는 마켓입니다. "
                 "중동 리스크와 유가에 직접 연결되는 이슈입니다."),
        watch=("합의 확률이 처음으로 두 자릿수가 되는 시점이 시장이 보는 가장 이른 타결 시기입니다."),
    ),
    dict(
        ticker="KXTRUMPOUT27", cat="global", pick="soonest",
        title=lambda ev, mk: f"트럼프, {k_before(mk.get('yes_sub_title') or '')} 전 대통령직 이탈?",
        explain=("도널드 트럼프 미국 대통령이 언제까지 직에서 물러날지를 시점별로 묻는 마켓입니다. "
                 "정치적 꼬리 위험을 가격으로 보여 주는 대표적인 사례입니다."),
        watch=("확률이 처음으로 두 자릿수가 되는 시점이 시장이 보는 가장 이른 이탈 시기입니다."),
    ),
    dict(
        ticker="KXGOVTSHUTDOWN", cat="global", pick="winner",
        title=lambda ev, mk: f"미국 정부 셧다운, {k_kr_date(ev)}?",
        explain=("미국 연방정부가 다시 셧다운(일시 업무정지)되는지를 묻는 마켓입니다. "
                 "정부 지출 협상과 경제지표 발표 일정에 직접 영향을 줍니다."),
        watch=("확률이 30%를 넘나드는지가 협상 교착의 정도를 보여 줍니다."),
    ),
]

VENDOR_KR = {
    "Gemini": "구글 Gemini", "ChatGPT": "오픈AI ChatGPT", "Claude": "앤트로픽 Claude",
    "Grok": "xAI Grok", "Muse": "메타 Muse", "Qwen": "알리바바 Qwen",
    "Ernie": "바이두 Ernie", "DeepSeek": "딥시크", "Llama": "메타 Llama",
}


def k_vendor(sub: str) -> str:
    return VENDOR_KR.get(sub.strip(), sub.strip())


def kalshi_price(mk: dict):
    """YES 확률(0~1). 호가 중간값이 있으면 그것을, 없으면 마지막 체결가를 쓴다."""
    def num(*keys):
        for key in keys:
            v = mk.get(key)
            if v in (None, ""):
                continue
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
        return None

    bid = num("yes_bid_dollars", "yes_bid")
    ask = num("yes_ask_dollars", "yes_ask")
    if bid is not None and bid > 1:   # 구 응답은 센트 단위(0~100)다.
        bid = bid / 100.0
    if ask is not None and ask > 1:
        ask = ask / 100.0
    # 호가 차이가 좁을 때만 중간값을 시장 확률로 쓰고, 넓으면 마지막 체결가로 물러난다.
    if (bid is not None and ask is not None and ask > 0 and ask >= bid
            and ask - bid <= KALSHI_MAX_SPREAD and 0 <= bid < 1 and 0 < ask < 1):
        return (bid + ask) / 2
    last = num("last_price_dollars", "last_price")
    if last is None:
        return None
    if last > 1:
        last = last / 100.0
    return last if 0 < last < 1 else None


def kalshi_volume(mk: dict, key: str, alt: str) -> float:
    for k in (key, alt):
        v = mk.get(k)
        if v in (None, ""):
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return 0.0


def kalshi_heat(mk: dict) -> float:
    """관심도 점수 — 24시간 거래량에 미결제 약정을 조금 얹는다(장기 마켓도 걸러지게)."""
    return kalshi_volume(mk, "volume_24h_fp", "volume_24h") + 0.01 * kalshi_volume(mk, "open_interest_fp", "open_interest")


def kalshi_ok(mk: dict) -> bool:
    if (mk.get("status") or "active") != "active":
        return False
    if (mk.get("market_type") or "binary") != "binary":
        return False
    p = kalshi_price(mk)
    return p is not None and 0.01 < p < 0.99


def pick_kalshi_market(ev: dict, mode: str):
    rows = [mk for mk in (ev.get("markets") or []) if kalshi_ok(mk)]
    if not rows:
        return None
    if mode == "ladder":
        return min(rows, key=lambda mk: (abs(kalshi_price(mk) * 100 - 50), -kalshi_heat(mk)))
    if mode == "soonest":
        # "언제까지" 형 누적 사다리 — 확률이 두 자릿수가 되는 가장 이른 시점을 고른다.
        near = [mk for mk in rows if kalshi_price(mk) >= 0.10]
        pool = near or rows
        return min(pool, key=lambda mk: (k_date_key(mk.get("yes_sub_title") or ""), -kalshi_price(mk)))
    return max(rows, key=lambda mk: (kalshi_price(mk), kalshi_heat(mk)))


def build_kalshi_item(cfg, ev: dict, mk: dict, rank: int) -> dict | None:
    p = kalshi_price(mk)
    if p is None:
        return None
    sub = (mk.get("yes_sub_title") or "").strip()
    title = None
    if cfg:
        try:
            title = cfg["title"](ev, mk)
        except (KeyError, TypeError, ValueError):
            title = None
    title = (title or "").strip()
    if not title:
        title = auto_title({"question": mk.get("title") or "", "option": sub})
    question = (mk.get("title") or "").strip()
    if not question:
        return None

    cat_id = (cfg or {}).get("cat") or KALSHI_CATEGORY_MAP.get(ev.get("category") or "") or "global"
    cat_label = next((c["label"] for c in CATEGORIES if c["id"] == cat_id), "글로벌")

    prev = None
    for k in ("previous_price_dollars", "previous_price"):
        if mk.get(k) not in (None, ""):
            try:
                prev = float(mk[k])
            except (TypeError, ValueError):
                prev = None
            if prev is not None and prev > 1:
                prev = prev / 100.0
            break

    close_iso = mk.get("close_time") or ""
    return {
        "key": "kalshi-" + str(mk.get("ticker") or "").lower(),
        "category": cat_id,
        "rank": rank,
        "no_feature": False,
        "title": title,
        # 브라우저 60초 실시간 조회는 Polymarket 전용이다(Kalshi 는 CORS 미허용 → 저장값 사용).
        "mid": "",
        "slug": "",
        "condition_id": "",
        "kalshi_ticker": mk.get("ticker") or "",
        "source": SOURCE_KALSHI,
        "source_key": "kalshi",
        "question": question,
        "option": sub,
        "event_title": ev.get("title") or "",
        "yes": round(p * 100, 1),
        "no": round((1 - p) * 100, 1),
        "change_24h": None if prev is None else round((p - prev) * 100, 1),
        "change_1w": None,
        "change_1m": None,
        "volume_24h": int(round(kalshi_volume(mk, "volume_24h_fp", "volume_24h"))),
        "volume_total": int(round(kalshi_volume(mk, "volume_fp", "volume"))),
        "liquidity": None,
        "open_interest": int(round(kalshi_volume(mk, "open_interest_fp", "open_interest"))),
        "end_date": et_date(close_iso),
        "end_iso": close_iso,
        "explain": (cfg or {}).get("explain") or (
            f"{cat_label} 분야의 글로벌 공개 시장 마켓입니다. 원문 질문은 \"{question}\"입니다. "
            "표시된 확률은 이 마켓 참가자들이 매긴 기대값(0~100%)입니다."),
        "watch": (cfg or {}).get("watch") or (
            "확률 변화 폭과 거래량을 함께 보면 시장 참가자들이 얼마나 빠르게 기대를 바꾸는지 "
            "가늠할 수 있습니다."),
        "auto": cfg is None,
    }


KALSHI_BY_TICKER = {c["ticker"]: c for c in KALSHI_SERIES}


def kalshi_get(path: str):
    """Kalshi 공개 API 호출 — 앞 호스트가 막히면 예비 호스트로 재시도."""
    for base in KALSHI_BASES:
        data = http_json(base + path, tries=2, timeout=20)
        if data:
            return data
    return None


def kalshi_events() -> list[dict]:
    """공개 /events 를 커서로 넘기며 상태 open 이벤트를 모은다(키 불필요)."""
    out: list[dict] = []
    cursor = ""
    for _ in range(KALSHI_MAX_PAGES):
        path = (f"/events?status=open&with_nested_markets=true&limit={KALSHI_PAGE_LIMIT}")
        if cursor:
            path += "&cursor=" + urllib.parse.quote(cursor)
        data = kalshi_get(path)
        if not data:
            break
        out.extend(data.get("events") or [])
        cursor = data.get("cursor") or ""
        if not cursor:
            break
        time.sleep(0.3)          # 과호출 방지
    return out


def kalshi_series_events() -> list[dict]:
    """템플릿에 적어 둔 주요 시리즈는 따로 한 번씩 더 조회한다.

    /events 기본 정렬은 최신·선거 이벤트가 상위에 몰려 금리·코인 마켓이 페이지 밖으로
    밀리는 경우가 있어, 사이트에 꼭 필요한 시리즈는 series_ticker 로 직접 확인한다.
    """
    out: list[dict] = []
    for cfg in KALSHI_SERIES:
        data = kalshi_get(f"/events?series_ticker={cfg['ticker']}"
                          f"&status=open&with_nested_markets=true&limit=20")
        if data:
            out.extend(data.get("events") or [])
    return out


def kalshi_close_dt(mk: dict):
    iso = mk.get("close_time") or ""
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None


def fetch_kalshi(taken_topics: set[str]) -> list[dict]:
    """Kalshi 공개 이벤트를 훑어 카테고리별 주요 마켓을 고른다.

    - /events?status=open&with_nested_markets=true&limit=200 (커서 페이지네이션)
    - KALSHI_CATEGORY_MAP 에 있는 카테고리만 사용
    - 이벤트 24시간 거래량 합계가 KALSHI_MIN_VOLUME_24H 미만이면 제외
    - 확률은 호가 차이가 KALSHI_MAX_SPREAD 이하일 때 중간값, 아니면 마지막 체결가
    - 48시간 안에 끝나는 초단기 마켓은 카드·이슈 페이지로 쓰지 않는다
    """
    events = kalshi_events()
    extra = kalshi_series_events()
    if extra:
        seen = {ev.get("event_ticker") for ev in events}
        events.extend(ev for ev in extra if ev.get("event_ticker") not in seen)
    if not events:
        print("  ! Kalshi 이벤트를 받지 못했습니다.", file=sys.stderr)
        return []
    print(f"  · 공개 이벤트 {len(events)}개 수집(주요 시리즈 포함)")

    now = datetime.now(timezone.utc)
    cand: list[dict] = []
    for ev in events:
        cat = KALSHI_CATEGORY_MAP.get(ev.get("category") or "")
        if not cat:
            continue
        live = [mk for mk in (ev.get("markets") or [])
                if (mk.get("status") or "active") in ("active", "open")
                and (mk.get("market_type") or "binary") == "binary"]
        if not live:
            continue
        vol = sum(kalshi_volume(mk, "volume_24h_fp", "volume_24h") for mk in live)
        if vol < KALSHI_MIN_VOLUME_24H:
            continue
        closes = [kalshi_close_dt(mk) for mk in live]
        closes = [c for c in closes if c]
        close_dt = min(closes) if closes else None
        if close_dt and (close_dt - now) < timedelta(hours=KALSHI_MIN_HORIZON_H):
            continue

        priced = [(kalshi_price(mk), mk) for mk in live]
        priced = [(p, mk) for p, mk in priced if p is not None]
        if not priced:
            continue

        cfg = KALSHI_BY_TICKER.get(ev.get("series_ticker") or "")
        mode = cfg.get("pick") if cfg else None
        if mode:
            mk = pick_kalshi_market(ev, mode)
            if not mk:
                continue
        else:
            mk = max(priced, key=lambda pm: (pm[0], kalshi_heat(pm[1])))[1]

        blob = " ".join([mk.get("title") or "", ev.get("title") or "", mk.get("yes_sub_title") or ""])
        if KOREA_BLOCK.search(blob):
            continue
        gossip = blocked_reason(mk.get("title") or "", ev.get("title") or "")
        if gossip:
            print(f"  · 가쉽·스캔들 제외('{gossip}'): {ev.get('event_ticker')}")
            continue
        if NOISE_BLOCK.search(blob):
            continue
        if cfg and cfg.get("topic"):
            if cfg["topic"] in taken_topics:
                print(f"  · 같은 이슈가 이미 있음({cfg['topic']}): {cfg['ticker']}")
                continue
            taken_topics.add(cfg["topic"])

        item = build_kalshi_item(cfg, ev, mk, rank=20)
        if not item:
            continue
        # 한국어 제목·해설이 붙지 않은 항목(번역 실패)은 카드로 내보내지 않는다.
        if not re.search(r"[가-힣]", item["title"]):
            continue
        item["event_ticker"] = ev.get("event_ticker") or ""
        item["series_ticker"] = ev.get("series_ticker") or item["event_ticker"].split("-")[0]
        item["category"] = cat
        item["_vol"] = vol
        cand.append(item)

    # 같은 시리즈(예: 월별 '최고 AI 모델')가 여러 회차로 잡히면 거래량이 큰 회차만 남긴다.
    best: dict[str, dict] = {}
    for it in cand:
        key = (it["series_ticker"], it["category"])
        prev = best.get(key)
        if prev is None or (it.get("_vol") or 0) > (prev.get("_vol") or 0):
            best[key] = it
    cand = list(best.values())

    # 카테고리별로 24시간 거래량 상위 KALSHI_PER_CATEGORY 개를 고른다(합계 최대 KALSHI_TOP_N).
    picked: list[dict] = []
    for cat in CATEGORIES:
        rows = [it for it in cand if it["category"] == cat["id"]]
        rows.sort(key=lambda it: -(it.get("_vol") or 0))
        for i, it in enumerate(rows[:KALSHI_PER_CATEGORY]):
            it["rank"] = 20 + i
            it.pop("_vol", None)
            picked.append(it)
            print(f"  · {it['category']}: {it['title']} (YES {it['yes']}%)")
    return picked[:KALSHI_TOP_N]


def heat(item: dict) -> float:
    """카드 정렬용 관심도 — Polymarket 은 24시간 거래량, Kalshi 는 여기에 미결제 약정을 조금 더한다."""
    return float(item.get("volume_24h") or 0) + 0.01 * float(item.get("open_interest") or 0)


def build(items: list[dict], pool_size: int) -> dict:
    now = datetime.now(KST)
    featured = pick_featured(items, 3)
    for item in items:
        item["featured"] = item["key"] in featured
        item["featured_rank"] = featured.index(item["key"]) + 1 if item["key"] in featured else None

    order = {c["id"]: i for i, c in enumerate(CATEGORIES)}
    items.sort(key=lambda it: (order[it["category"]], it.get("rank", 90),
                               0 if it["featured"] else 1, -heat(it)))
    counts = {c["id"]: sum(1 for it in items if it["category"] == c["id"]) for c in CATEGORIES}
    sources = [
        {"key": "kalshi", "label": SOURCE_KALSHI,
         "count": sum(1 for it in items if it.get("source") == SOURCE_KALSHI),
         "note": "미국 CFTC 인가 공개 예측시장"},
        {"key": "polymarket", "label": SOURCE_POLYMARKET,
         "count": sum(1 for it in items if it.get("source") == SOURCE_POLYMARKET),
         "note": "글로벌 공개 예측시장"},
    ]

    return {
        "schema": 1,
        "site": "예측판 YECHEUKPAN",
        "updated_at": now.isoformat(timespec="seconds"),
        "updated_at_utc": now.astimezone(timezone.utc).isoformat(timespec="seconds"),
        "updated_label": now.strftime("%Y년 %-m월 %-d일 %H:%M") + " (KST)",
        "source": "Kalshi · Polymarket 공개 API",
        "sources": [s for s in sources if s["count"]],
        "source_note": "시장이 매긴 확률 데이터를 한국어로 정리했습니다. "
                       "베팅·거래 기능은 제공하지 않습니다.",
        "pool_size": pool_size,
        "count": len(items),
        "categories": [dict(c, count=counts[c["id"]]) for c in CATEGORIES],
        "featured": featured,
        "items": items,
    }


def build_static_pages() -> None:
    """데이터를 저장한 뒤 이슈별 정적 페이지와 sitemap.xml을 다시 만든다.

    GitHub Actions에서는 다음 커밋 단계가 생성물을 함께 실을 수 있도록 스테이징까지 한다.
    (워크플로우 파일을 고치지 않고도 매 갱신마다 페이지가 최신으로 유지된다.)
    """
    script = Path(__file__).resolve().parent / "build_issue_pages.py"
    if not script.exists():
        print("  · 이슈 페이지 생성 스크립트가 없어 건너뜁니다.", file=sys.stderr)
        return
    try:
        r = subprocess.run([sys.executable, str(script)], cwd=str(ROOT))
        if r.returncode != 0:
            print(f"  ! 이슈 페이지 생성 실패(코드 {r.returncode}) — 데이터만 갱신합니다.", file=sys.stderr)
            return
    except OSError as e:
        print(f"  ! 이슈 페이지 생성 실패: {e}", file=sys.stderr)
        return
    if os.environ.get("GITHUB_ACTIONS") == "true":
        try:
            # data/markets.json 은 일부러 스테이징하지 않는다. 워크플로우가 그 파일의
            # 변경 여부로 커밋 여부를 판단하므로, 미리 stage 하면 '변경 없음'으로 조기 종료된다.
            subprocess.run(["git", "add", "-A", "issues", "sitemap.xml"],
                           cwd=str(ROOT), check=True)
            print("  · 생성물 스테이징 완료(issues/, sitemap.xml)")
        except (OSError, subprocess.CalledProcessError) as e:
            print(f"  ! git add 실패: {e}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="파일을 쓰지 않고 결과만 출력")
    args = ap.parse_args()

    print("[1/5] Polymarket 공개 API에서 후보 마켓 수집")
    pool = build_pool()
    if not pool:
        print("! 후보를 하나도 받지 못했습니다. 기존 파일을 유지합니다.", file=sys.stderr)
        return 1
    print(f"  → 후보 {len(pool)}개")

    print("[2/5] 큐레이션 매칭")
    items, used = [], set()
    for cat in CATEGORIES:
        rules = sorted([r for r in WATCH if r["cat"] == cat["id"]], key=lambda r: r["rank"])
        taken = 0
        for rule in rules:
            if taken >= TARGET_PER_CATEGORY:
                break
            row = find_market(pool, rule)
            if not row:
                print(f"  - {rule['key']}: 매칭 없음")
                continue
            if not rule.get("allow_extreme") and (row["yes"] < 0.02 or row["yes"] > 0.98):
                print(f"  - {rule['key']}: 확률 극단값({row['yes']:.3f}) 제외")
                continue
            items.append(format_item(rule, row))
            used.add(row["mid"])
            taken += 1

    print("[3/5] 부족한 카테고리 자동 선별")
    for cat in CATEGORIES:
        have = sum(1 for it in items if it["category"] == cat["id"])
        while have < TARGET_PER_CATEGORY:
            row = pick_auto(pool, cat["id"], used)
            if not row:
                break
            items.append(build_auto(row, cat["id"]))
            used.add(row["mid"])
            have += 1

    # 이미 실린 Polymarket 이슈와 같은 주제(topic)는 Kalshi 에서 다시 싣지 않는다.
    taken_topics = {r["topic"] for r in WATCH
                    if r.get("topic") and any(it["key"] == r["key"] for it in items)}
    print("[4/5] Kalshi 공개 API에서 마켓 수집(미국 CFTC 인가)")
    kalshi_items = fetch_kalshi(taken_topics)
    if kalshi_items:
        print(f"  → Kalshi {len(kalshi_items)}개 합치기")
        items.extend(kalshi_items)
    else:
        print("  ! Kalshi 항목을 하나도 받지 못했습니다 — Polymarket 데이터로만 계속합니다.",
              file=sys.stderr)

    # 마지막 안전망 — 카드 제목·해설까지 포함해 한 번 더 검사한다.
    kept = []
    for it in items:
        reason = blocked_reason(it.get("title", ""), it.get("question", ""),
                                it.get("event_title", ""))
        if reason:
            print(f"  · 가쉽·스캔들 제외('{reason}'): {it.get('key')} — {it.get('title')}", file=sys.stderr)
            continue
        kept.append(it)
    items = kept

    if len(items) < MIN_ITEMS:
        print(f"! 새 항목이 {len(items)}개뿐입니다(최소 {MIN_ITEMS}). 기존 파일을 유지합니다.",
              file=sys.stderr)
        return 1

    data = build(items, len(pool))
    print(f"[5/5] {len(items)}개 항목 / TOP3: {', '.join(data['featured'])}")
    print("  → 출처: " + ", ".join(f"{s['label']} {s['count']}개" for s in data["sources"]))

    if args.dry_run:
        print(json.dumps(data, ensure_ascii=False, indent=1)[:2000])
        return 0

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(OUT_PATH)
    print(f"  → {OUT_PATH.relative_to(ROOT)} 저장 완료")

    print("      이슈별 정적 페이지 · sitemap.xml 생성")
    build_static_pages()
    return 0


if __name__ == "__main__":
    sys.exit(main())
