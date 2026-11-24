#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
예측판(YECHEUKPAN) — 사생활·스캔들 가십 콘텐츠 제외 필터
=========================================================

마켓의 질문·이벤트 제목·카드 제목에 **사생활 침해·성추문·불륜·가십성 스캔들**
표현이 있으면 사이트에 싣지 않는다. 이유는 두 가지다.

1. 애드센스 정책 — 성적 콘텐츠·가십성 명예훼손 소재는 광고 게재 제한 대상이다.
2. 명예훼손 리스크 — 실명 공인(예: 기업 CEO)의 사생활 의혹을 확률 카드로
   재가공해 노출하면, 근거 없는 주장을 사이트가 유통·증폭시키는 셈이 된다.

## 매칭 규칙

- 영어는 **단어 경계(\\b)** 로만 잡는다. `affair` 규칙이 `foreign affairs` 같은
  정상 표현을 잡지 않도록, 먼저 '면제구(豁免句)'를 지운 뒤 검사한다.
- 한국어는 조사가 붙어도 잡히도록 부분 문자열로 검사한다(예: `불륜을`, `불륜설`).
- 대소문자·전각/반각·연속 공백·유니코드 호환 문자를 정규화한 뒤 검사한다.

사용법(자체 점검):

    python3 scripts/content_filter.py
"""

from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------------------
# 1) 면제구 — 사생활과 무관한 정상 표현. 검사 전에 지운다.
# ---------------------------------------------------------------------------
EN_EXEMPT = [
    # 'foreign affairs'(외교), 'current affairs'(시사) 등은 가십이 아니다.
    r"\b(?:foreign|world|current|public|international|external|internal|"
    r"government|legislative|consumer|veterans|regulatory|corporate|business|"
    r"global|state|home|diplomatic|trade|economic|financial|legal|media|"
    r"medical|student|campus|community|civic|regional|policy|defense|military|"
    r"security|religious|press|political|human)\s+affairs?\b",
    # 'same-sex marriage' 같은 정책 이슈는 사생활 스캔들이 아니다.
    r"\bsame[-\s]sex\b",
    r"\bsex\s+(?:education|discrimination|equality)\b",
    r"\bsexism\b",
    # 'naked short selling'(무차입 공매도)은 금융 용어다.
    r"\bnaked\s+short(?:\s+selling|\s+sellers?|s)?\b",
]

KO_EXEMPT = [
    # 통계·정책 용어로 쓰이는 경우(예: '이혼율')는 제외 대상이 아니다.
    r"이혼율",
    r"이혼\s*통계",
]

# ---------------------------------------------------------------------------
# 2) 차단 패턴
# ---------------------------------------------------------------------------
EN_BLOCK = [
    # 불륜·외도·성적 스캔들
    r"\baffairs?\b",
    r"\binfidelity\b",
    r"\bunfaithful\b",
    r"\bmistress(?:es)?\b",
    r"\bparamour\b",
    r"\bcheat(?:ing|ed|er|ers)\b",
    r"\bcyber[-\s]?sex\b",
    r"\bsext(?:ing|ape)?\b",
    r"\bsex\s*tape\b",
    r"\bsex\b",
    r"\bsexual(?:ly)?\b",
    r"\bporn(?:o|ography|ographic|star)?\b",
    r"\bonlyfans\b",
    r"\bnudes?\b",
    r"\bnaked\b",
    r"\bmasturbat\w*\b",
    r"\bprostitut\w*\b",
    r"\bsexual\s+(?:harassment|assault|misconduct)\b",
    # 이혼·파경
    r"\bdivorc(?:e|es|ed|ing)\b",
    r"\bmarital\s+(?:trouble|strife)\b",
    r"\blove\s+child\b",
    # 가십성 스캔들
    r"\bscandals?\b",
    r"\bsex\s+scandal\b",
    r"\bsecret\s+(?:love\s+)?child\b",
    r"\bcheating\s+scandal\b",
]

KO_BLOCK = [
    # 불륜·외도 ('애인'은 '장애인'에 걸려 제외한다)
    "불륜", "외도", "내연녀", "내연남", "혼외정사", "바람피",
    # 성추문·성적 표현
    "성추문", "성폭행", "성희롱", "성매매", "성관계", "음란", "포르노", "야동", "노출사진",
    # 이혼·가십
    "이혼", "파경", "스캔들", "가십", "사생활", "열애설", "결별설", "불화설",
]

_EN_EXEMPT_RE = re.compile("|".join(EN_EXEMPT), re.I)
_KO_EXEMPT_RE = re.compile("|".join(KO_EXEMPT))
_EN_BLOCK_RE = re.compile("|".join(EN_BLOCK), re.I)
_KO_BLOCK = tuple(KO_BLOCK)


def normalize(text: str) -> str:
    """비교용 정규화: 유니코드 호환 형태 → 소문자 → 공백 정리."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", str(text))
    t = t.replace("\u200b", "").replace("\ufeff", "")
    t = t.lower()
    t = re.sub(r"[\s_]+", " ", t)
    return t.strip()


def blocked_reason(*texts: str) -> str | None:
    """차단 사유(매칭된 표현)를 돌려준다. 통과하면 None."""
    for raw in texts:
        t = normalize(raw)
        if not t:
            continue
        # 면제구를 공백으로 지운 뒤 검사한다('foreign affairs' → '  ').
        en = _EN_EXEMPT_RE.sub(" ", t)
        en = re.sub(r"\s+", " ", en).strip()
        m = _EN_BLOCK_RE.search(en)
        if m:
            return m.group(0)

        ko = _KO_EXEMPT_RE.sub(" ", t)
        for word in _KO_BLOCK:
            if word in ko:
                return word
    return None


def is_blocked(*texts: str) -> bool:
    """하나라도 걸리면 True. (질문·이벤트 제목·카드 제목을 함께 넘긴다.)"""
    return blocked_reason(*texts) is not None


# ---------------------------------------------------------------------------
# 자체 점검 — 실제 오탐/누락 사례를 고정해 둔다.
#   python3 scripts/content_filter.py
# ---------------------------------------------------------------------------
BLOCK_CASES = [
    ("Will Jensen Huang admit to another affair with a woman by December 31?", True),
    ("Will Elon Musk get a divorce in 2026?", True),
    ("Will there be a new cheating scandal in Formula 1?", True),
    ("Will onlyfans be banned in the US?", True),
    ("Will X star in a sex tape?", True),
    ("젠슨 황 admits to another affair", True),   # 제목에 영문이 남은 경우
    ("젠슨 황 불륜 인정, 12월 31일까지?", True),
    ("연예인 A씨 외도 보도 나올까?", True),
    ("이혼 소송 결과는?", True),
    ("성추문 논란으로 사퇴할까?", True),
]

PASS_CASES = [
    ("Will the Fed increase interest rates by 25 bps after the December 2026 meeting?", True),
    ("Will the US hold foreign affairs talks with China in 2026?", True),
    ("Will the Fed's regulatory affairs committee approve the rule?", True),
    ("Will same-sex marriage be legal in Japan by 2027?", True),
    ("Will the SEC ban naked short selling in 2026?", True),
    ("Will 장애인 고용 의무가 강화될까?", True),
    ("Will Bitcoin dip to $50,000 in November?", True),
    ("Will NVIDIA be the largest company in the world by market cap on December 31?", True),
    ("Will Anthropic's valuation hit (HIGH) $2.0T by December 31?", True),
    ("Strait of Hormuz traffic returns to normal by December 31?", True),
    ("이스라엘-이란 휴전, 연말까지 유지?", True),
    ("이혼율이 2% 아래로 떨어질까?", True),      # 통계 용어는 통과
    ("Will Apple be the largest company in the world by market cap on December 31?", True),
]


def _selftest() -> int:
    fails = 0
    for text, want_block in BLOCK_CASES:
        got = is_blocked(text)
        if got != want_block:
            fails += 1
            print(f"  ✗ 차단 실패: {text!r} (기대 {'차단' if want_block else '통과'}, 실제 "
                  f"{'차단' if got else '통과'})")
    for text, want_pass in PASS_CASES:
        reason = blocked_reason(text)
        if want_pass and reason:
            fails += 1
            print(f"  ✗ 오탐: {text!r} — '{reason}' 에 걸림")
    total = len(BLOCK_CASES) + len(PASS_CASES)
    print(f"자체 점검 {total - fails}/{total} 통과")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
