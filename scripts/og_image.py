#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
예측판(YECHEUKPAN) — 이슈별 OG 이미지(1200×630) 생성
=====================================================================

이슈 하나를 1200×630 PNG로 그린다. SNS·검색 결과·메신저 미리보기에 쓰인다.

  구성
    ① 이슈 한국어 제목
    ② 현재 글로벌 시장 확률(%) — 크게
    ③ 한국 유저(예측판 투표) vs 세계 시장 확률 비교 바·수치
       (투표가 없으면 "한국 유저 첫 투표 대기")
    ④ 출처(Kalshi / Polymarket) + 갱신 주기 + 우측 하단 yecheukpan.kr

- Pretendard(assets/fonts)로 한글을 그린다. 폰트 파일이 없으면 이미지를 만들지 않는다.
- Pillow 가 없는 환경(로컬 표준 라이브러리만 있는 경우)에서도 빌드 자체는 계속되도록
  build_issue_pages.py 가 이 모듈을 선택적으로 불러 쓴다.
"""

from __future__ import annotations

import io
import json
import pathlib
import urllib.request

W, H = 1200, 630
MARGIN = 64

BG = (243, 245, 248)
WHITE = (255, 255, 255)
NAVY = (30, 58, 138)
BLUE = (37, 99, 235)
INK = (25, 31, 40)
INK2 = (78, 89, 104)
MUTED = (107, 118, 132)
LINE = (226, 231, 235)
TRACK = (237, 241, 246)
YES_C = (217, 48, 37)
KALSHI_BG = (234, 244, 254)
KALSHI_TX = (11, 95, 165)
PM_BG = (240, 243, 247)
PM_TX = (78, 89, 104)

ROOT = pathlib.Path(__file__).resolve().parents[1]
FONT_DIR = ROOT / "assets" / "fonts"
VOTE_CACHE = ROOT / "data" / "vote_tally.json"

SUPABASE_URL = "https://fofgulfyrbekirujfjkz.supabase.co"
SUPABASE_KEY = "sb_publishable_FOxu2wBxJVLWf-m4z1C-eQ_B7DoDojY"

CADENCE = {"Kalshi": "2시간마다 갱신", "Polymarket": "1분마다 실시간"}


# ---------------------------------------------------------------------------
# 폰트
# ---------------------------------------------------------------------------
_FONT_CACHE: dict = {}


def fonts_available() -> bool:
    return all((FONT_DIR / f"Pretendard-{w}.otf").exists() for w in ("ExtraBold", "Bold", "Medium"))


def font(weight: str, size: int):
    from PIL import ImageFont  # 지역 import — Pillow 없는 환경 배려

    key = (weight, size)
    if key not in _FONT_CACHE:
        _FONT_CACHE[key] = ImageFont.truetype(str(FONT_DIR / f"Pretendard-{weight}.otf"), size)
    return _FONT_CACHE[key]


def tw(draw, text: str, f) -> int:
    return int(draw.textlength(text, font=f))


# ---------------------------------------------------------------------------
# 문장 줄바꿈 — 공백 우선, 한 덩어리가 넘치면 글자 단위로 자른다
# ---------------------------------------------------------------------------
def wrap(draw, text: str, f, max_w: int, max_lines: int) -> list | None:
    text = " ".join(str(text or "").split())
    if not text:
        return [""]
    lines, cur = [], ""
    for word in text.split(" "):
        cand = (cur + " " + word).strip()
        if tw(draw, cand, f) <= max_w:
            cur = cand
            continue
        if cur:
            lines.append(cur)
            cur = ""
        # 단어 하나가 폭을 넘으면 글자 단위로 쪼갠다.
        while tw(draw, word, f) > max_w:
            cut = len(word)
            while cut > 1 and tw(draw, word[:cut], f) > max_w:
                cut -= 1
            lines.append(word[:cut])
            word = word[cut:]
        cur = word
        if len(lines) >= max_lines:
            return None
    if cur:
        lines.append(cur)
    return lines if len(lines) <= max_lines else None


def fit_title(draw, title: str, max_w: int, max_lines: int = 3):
    for size in (54, 50, 46, 42, 38, 34):
        f = font("ExtraBold", size)
        lines = wrap(draw, title, f, max_w, max_lines)
        if lines:
            return f, lines, size
    f = font("Bold", 30)
    lines = wrap(draw, title, f, max_w, max_lines) or [str(title)[:40]]
    return f, lines, 30


# ---------------------------------------------------------------------------
# 투표 집계 (예측판 유저 투표)
# ---------------------------------------------------------------------------
def fetch_vote_tally(timeout: float = 12.0) -> dict:
    """Supabase RPC yp_vote_tally → {issue_key: {'yes': n, 'no': n}}.

    네트워크가 없으면 마지막으로 받아 둔 data/vote_tally.json 을 쓴다.
    (투표는 천천히 변하므로 조금 오래된 값이어도 '첫 투표 대기'로 잘못 표시하는 것보다 낫다.)
    """
    body = json.dumps({}).encode()
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/rpc/yp_vote_tally",
        data=body,
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            rows = json.loads(r.read().decode("utf-8"))
        tally = {}
        for row in rows or []:
            key = row.get("issue_key")
            if key:
                tally[key] = {"yes": int(row.get("yes") or 0), "no": int(row.get("no") or 0)}
        VOTE_CACHE.parent.mkdir(parents=True, exist_ok=True)
        VOTE_CACHE.write_text(json.dumps(tally, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        return tally
    except Exception as e:  # noqa: BLE001 — 어떤 실패든 캐시로 넘어간다
        print(f"  · 유저 투표 집계를 받지 못했습니다({e.__class__.__name__}) — 저장된 값을 씁니다.")
        try:
            return json.loads(VOTE_CACHE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}


# ---------------------------------------------------------------------------
# 그리기
# ---------------------------------------------------------------------------
def _pill(draw, x_right: int, y: int, text: str, bg, tx, f) -> int:
    """오른쪽 정렬 배지. 그린 왼쪽 x 를 돌려준다."""
    pad_x, h = 16, 40
    w = tw(draw, text, f) + pad_x * 2
    x = x_right - w
    draw.rounded_rectangle([x, y, x_right, y + h], radius=10, fill=bg)
    draw.text((x + pad_x, y + h / 2), text, font=f, fill=tx, anchor="lm")
    return x


def render(it: dict, votes: dict, updated_label: str) -> bytes:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    src = (it.get("source") or "Polymarket")
    is_kalshi = src == "Kalshi"
    cadence = CADENCE.get(src, CADENCE["Polymarket"])
    yes = float(it.get("yes") or 0)
    yes = max(0.0, min(100.0, yes))
    title = " ".join(str(it.get("title") or "").split())

    # ---- 머리: 로고 + 출처/갱신 주기 -------------------------------------
    d.rounded_rectangle([MARGIN, 44, MARGIN + 46, 90], radius=12, fill=NAVY)
    d.text((MARGIN + 23, 67), "예", font=font("ExtraBold", 27), fill=WHITE, anchor="mm")
    d.text((MARGIN + 60, 45), "예측판", font=font("ExtraBold", 30), fill=INK)
    d.text((MARGIN + 60, 80), "YECHEUKPAN", font=font("Bold", 13), fill=MUTED)

    _pill(d, W - MARGIN, 46, f"{src} · {cadence}",
          KALSHI_BG if is_kalshi else PM_BG,
          KALSHI_TX if is_kalshi else PM_TX,
          font("Bold", 19))

    # ---- ① 제목 -----------------------------------------------------------
    tf, tlines, tsize = fit_title(d, title, W - MARGIN * 2, 3)
    lh = int(tsize * 1.24)
    block_h = lh * len(tlines)
    # 제목 블록(120~332) 안에서 세로 가운데 — 한 줄 제목일 때 아래가 비어 보이지 않게
    y = 120 + max(0, (212 - block_h) // 2)
    for ln in tlines:
        d.text((MARGIN, y), ln, font=tf, fill=INK)
        y += lh

    # ---- ② 글로벌 시장 확률 (크게) ---------------------------------------
    num_y = 372
    d.text((MARGIN, num_y - 52), "글로벌 시장 확률 · YES", font=font("Bold", 21), fill=INK2)
    num_txt = f"{yes:.1f}%"
    nf = font("ExtraBold", 116)
    while tw(d, num_txt, nf) > 470 and nf.size > 70:
        nf = font("ExtraBold", nf.size - 6)
    d.text((MARGIN - 4, num_y - 18), num_txt, font=nf, fill=NAVY)
    num_w = tw(d, num_txt, nf)

    # 24시간 변동
    d24 = it.get("change_24h")
    if d24 is not None:
        try:
            d24 = float(d24)
        except (TypeError, ValueError):
            d24 = None
    if d24 is not None:
        flat = abs(d24) < 0.05
        dtxt = "24시간 변동 없음" if flat else ("▲ " if d24 > 0 else "▼ ") + f"{abs(round(d24, 1)):.1f}%p"
        dcol = MUTED if flat else (YES_C if d24 > 0 else BLUE)
        d.text((MARGIN + num_w + 14, num_y + 62), dtxt, font=font("Bold", 22), fill=dcol)
        if not flat:
            d.text((MARGIN + num_w + 14, num_y + 92), "24시간 변동", font=font("Medium", 16), fill=MUTED)

    # ---- ③ 한국 유저 vs 세계 시장 ----------------------------------------
    px, py, pw, ph = 668, 344, W - MARGIN - 668, 208
    d.rounded_rectangle([px, py, px + pw, py + ph], radius=18, fill=WHITE, outline=LINE, width=2)

    d.text((px + 24, py + 20), "한국 유저 vs 세계 시장", font=font("Bold", 21), fill=INK)

    v = votes.get(it.get("key") or "") or {}
    vy, vn = int(v.get("yes") or 0), int(v.get("no") or 0)
    vtot = vy + vn
    kp = (vy / vtot * 100) if vtot else 0.0

    bar_x0 = px + 24
    bar_x1 = px + pw - 24
    bar_w = bar_x1 - bar_x0

    def row(label: str, value: str, pctv: float, ylab: int, color, empty_note: str = ""):
        d.text((bar_x0, ylab), label, font=font("Bold", 17), fill=INK2)
        d.text((bar_x1, ylab), value, font=font("Bold", 17), fill=INK, anchor="ra")
        by = ylab + 26
        d.rounded_rectangle([bar_x0, by, bar_x1, by + 16], radius=8, fill=TRACK)
        if empty_note:
            d.text(((bar_x0 + bar_x1) / 2, by + 8), empty_note, font=font("Medium", 13), fill=MUTED, anchor="mm")
        else:
            fw = max(10, int(bar_w * max(0.0, min(100.0, pctv)) / 100.0))
            d.rounded_rectangle([bar_x0, by, bar_x0 + fw, by + 16], radius=8, fill=color)

    row("세계 시장", f"{yes:.1f}%", yes, py + 58, NAVY)
    if vtot:
        row("한국 유저", f"{kp:.0f}% · {vtot}명", kp, py + 112, BLUE)
    else:
        row("한국 유저", "—", 0.0, py + 112, BLUE, "한국 유저 첫 투표 대기")

    d.text((px + 24, py + ph - 24), "투표는 yecheukpan.kr 홈에서 참여할 수 있습니다",
           font=font("Medium", 13), fill=MUTED)

    # ---- ④ 바닥: 기준 시각 + 주소 ----------------------------------------
    d.line([MARGIN, 566, W - MARGIN, 566], fill=LINE, width=2)
    stamp = (updated_label or "").strip()
    d.text((MARGIN, 584), f"{stamp} 기준 · {cadence}" if stamp else cadence,
           font=font("Medium", 17), fill=MUTED)
    d.text((W - MARGIN, 580), "yecheukpan.kr", font=font("ExtraBold", 26), fill=NAVY, anchor="ra")

    buf = io.BytesIO()
    img.convert("P", palette=Image.ADAPTIVE, colors=128).save(buf, format="PNG", optimize=True)
    return buf.getvalue()
