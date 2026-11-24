#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
예측판(YECHEUKPAN) 데이터 갱신 스크립트
=========================================

Polymarket의 공개 Gamma API에서 경제·금리, 코인, AI·빅테크, 글로벌 이슈 마켓을
가져와 한국어 큐레이션 데이터(data/markets.json)를 만든다.

- 표준 라이브러리만 사용한다(서버·유료 API 없음, GitHub Actions에서 무료 실행).
- 큐레이션 규칙(WATCH)에 매칭되는 마켓을 우선 채우고, 매칭이 모자라면
  자동 선별(auto) 항목으로 최소 8개까지 채운다.
- 새로 만든 항목이 8개 미만이면 기존 파일을 덮어쓰지 않는다(사이트 보호).

사용법:  python3 scripts/fetch_markets.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import re
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
USER_AGENT = "YecheukpanBot/1.0 (Korean prediction-market info site; contact: site owner)"

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

# 자동 선별에서 제외할 스포츠·연예·SNS 잡음
NOISE_BLOCK = re.compile(
    r"(\bvs\.?\b|\bO/U\b|\bSpread:|win on \d{4}-\d{2}-\d{2}|"
    r"UFC|NBA|NFL|MLB|NHL|ATP|WTA|Grand Prix|Premier League|Champions League|"
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
        key="fed-dec-hike", cat="economy", rank=1,
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
        "crypto": {"crypto", "finance"},
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
    return item["volume_24h"] * (1 + 0.8 * tightness)


def pick_featured(items: list[dict], limit: int = 3) -> list[str]:
    ranked = sorted(items, key=lambda it: (not it.get("no_feature"), -score(it)))
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
    return chosen


def build(items: list[dict], pool_size: int) -> dict:
    now = datetime.now(KST)
    featured = pick_featured(items, 3)
    for item in items:
        item["featured"] = item["key"] in featured
        item["featured_rank"] = featured.index(item["key"]) + 1 if item["key"] in featured else None

    order = {c["id"]: i for i, c in enumerate(CATEGORIES)}
    items.sort(key=lambda it: (order[it["category"]], it.get("rank", 90),
                               0 if it["featured"] else 1, -it["volume_24h"]))
    counts = {c["id"]: sum(1 for it in items if it["category"] == c["id"]) for c in CATEGORIES}

    return {
        "schema": 1,
        "site": "예측판 YECHEUKPAN",
        "updated_at": now.isoformat(timespec="seconds"),
        "updated_at_utc": now.astimezone(timezone.utc).isoformat(timespec="seconds"),
        "updated_label": now.strftime("%Y년 %-m월 %-d일 %H:%M") + " (KST)",
        "source": "Polymarket Gamma 공개 API",
        "source_note": "글로벌 예측시장의 공개 확률 데이터를 한국어로 정리했습니다. "
                       "베팅·거래 기능은 제공하지 않습니다.",
        "pool_size": pool_size,
        "count": len(items),
        "categories": [dict(c, count=counts[c["id"]]) for c in CATEGORIES],
        "featured": featured,
        "items": items,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="파일을 쓰지 않고 결과만 출력")
    args = ap.parse_args()

    print("[1/4] Polymarket 공개 API에서 후보 마켓 수집")
    pool = build_pool()
    if not pool:
        print("! 후보를 하나도 받지 못했습니다. 기존 파일을 유지합니다.", file=sys.stderr)
        return 1
    print(f"  → 후보 {len(pool)}개")

    print("[2/4] 큐레이션 매칭")
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

    print("[3/4] 부족한 카테고리 자동 선별")
    for cat in CATEGORIES:
        have = sum(1 for it in items if it["category"] == cat["id"])
        while have < TARGET_PER_CATEGORY:
            row = pick_auto(pool, cat["id"], used)
            if not row:
                break
            items.append(build_auto(row, cat["id"]))
            used.add(row["mid"])
            have += 1

    if len(items) < MIN_ITEMS:
        print(f"! 새 항목이 {len(items)}개뿐입니다(최소 {MIN_ITEMS}). 기존 파일을 유지합니다.",
              file=sys.stderr)
        return 1

    data = build(items, len(pool))
    print(f"[4/4] {len(items)}개 항목 / TOP3: {', '.join(data['featured'])}")

    if args.dry_run:
        print(json.dumps(data, ensure_ascii=False, indent=1)[:2000])
        return 0

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(OUT_PATH)
    print(f"  → {OUT_PATH.relative_to(ROOT)} 저장 완료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
