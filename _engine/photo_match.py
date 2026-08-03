# -*- coding: utf-8 -*-
"""제목·카피에 가장 잘 맞는 사진을 고르고, 매칭이 약하면 스스로 문제를 제기하는 모듈.

왜 필요했나 (2026-08-03, 사용자 지적 "하이닉스 폭락왔다 썸네일 이미지 매칭 최악"):
  기존에는 기사 JSON이 photo_category 를 직접 찍어주면 그 안에서 '날짜·순번 기반
  순환'으로만 골랐다. 순환은 돌려쓰기를 막을 뿐 '이 기사에 맞는가'는 아무도 안 봤다.
  그래서 카테고리를 잘못 찍으면(또는 안 찍으면) 엉뚱한 사진이 조용히 나갔다.

여기서 하는 일:
  1) 사진마다 '검색 가능한 텍스트'(검색어·원제·카테고리·용도·파일명)를 모은다
  2) 기사 텍스트(제목+썸네일 카피)에서 개념 키워드를 뽑는다 (한글 -> 영문 개념 사전)
  3) 둘을 대조해 점수를 매기고, 최고점 사진과 '왜 골랐는지'를 함께 돌려준다
  4) 점수가 기준 미만이면 경고를 남긴다 -> build_report 에 실려 사람이 잡을 수 있다

점수는 '의미 이해'가 아니라 키워드 대조다. 완벽한 판단이 아니라
'명백한 미스매치를 걸러내는 그물'로 쓴다. 최종 판단은 사람의 육안 검수다.
"""

import json
import os
import re

INDEX_PATH = os.path.join("assets", "photos", "index.json")

# 한글 개념 -> 사진 메타데이터(영문)에서 찾을 단어들.
# 왼쪽 키가 기사 텍스트에 나오면, 오른쪽 단어를 가진 사진에 점수를 준다.
CONCEPTS = {
    "반도체": ["semiconductor", "chip", "wafer", "cleanroom", "microchip", "circuit"],
    "메모리": ["memory", "ram", "dram", "module", "semiconductor"],
    "하이닉스": ["memory", "ram", "dram", "semiconductor", "hynix"],
    "삼성전자": ["samsung", "smartphone", "electronics", "device"],
    "스마트폰": ["smartphone", "mobile", "device", "electronics"],
    "가전": ["appliance", "electronics", "home", "display"],

    "수출": ["export", "port", "container", "terminal", "cargo", "crane", "busan"],
    "무역": ["export", "port", "container", "terminal", "cargo", "trade"],
    "관세": ["export", "port", "container", "cargo", "trade"],

    "부동산": ["apartment", "real estate", "housing", "residential", "construction"],
    "아파트": ["apartment", "residential", "high rise", "housing"],
    "전세": ["apartment", "residential", "housing"],
    "월세": ["apartment", "residential", "housing"],
    "청약": ["apartment", "construction", "housing"],

    "금리": ["interest rate", "bank", "central bank", "finance", "money"],
    "한국은행": ["bank of korea", "central bank", "bank", "interest rate"],
    "대출": ["bank", "loan", "money", "finance", "interest"],
    "예금": ["bank", "savings", "money", "deposit", "vault"],
    "적금": ["savings", "money", "coins", "bank"],
    "통장": ["savings", "money", "coins", "cash", "bank"],
    "은행": ["bank", "teller", "vault", "counter"],

    "주식": ["stock", "exchange", "trading", "ticker", "market"],
    "증시": ["stock", "exchange", "trading", "ticker", "market"],
    "코스피": ["stock", "exchange", "trading", "ticker", "market"],
    "코스닥": ["stock", "exchange", "trading", "ticker", "market"],
    "상장": ["stock", "exchange", "trading", "market"],
    "배당": ["stock", "exchange", "trading", "money"],

    "비트코인": ["bitcoin", "cryptocurrency", "blockchain", "coins", "crypto"],
    "코인": ["bitcoin", "cryptocurrency", "blockchain", "coins", "crypto"],
    "가상자산": ["bitcoin", "cryptocurrency", "blockchain", "crypto"],
    "이더리움": ["cryptocurrency", "blockchain", "crypto", "coins"],

    "환율": ["currency", "exchange", "dollar", "foreign exchange", "won"],
    "달러": ["dollar", "currency", "exchange", "cash"],
    "원화": ["won", "currency", "banknote", "cash"],

    "물가": ["grocery", "supermarket", "produce", "market", "prices", "shopping"],
    "소비": ["grocery", "supermarket", "shopping", "market", "consumer"],
    "장바구니": ["grocery", "supermarket", "shopping", "produce", "cart"],
    "마트": ["supermarket", "grocery", "shelves", "shopping"],

    "정부": ["government", "complex", "parliament", "assembly", "official"],
    "정책": ["government", "complex", "parliament", "assembly", "official"],
    "지원금": ["government", "complex", "official", "money"],
    "예산": ["government", "complex", "assembly", "official"],
    "국회": ["parliament", "assembly", "government", "national assembly"],
    "세금": ["government", "official", "money", "complex"],

    "연금": ["senior", "elderly", "retirement", "old people"],
    "노후": ["senior", "elderly", "retirement", "old people"],
    "고령": ["senior", "elderly", "retirement", "old people"],
    "은퇴": ["senior", "elderly", "retirement"],

    "미국": ["wall street", "new york", "dollar", "stock exchange"],
    "월가": ["wall street", "new york", "stock exchange"],
    "나스닥": ["wall street", "new york", "stock exchange", "trading"],
    "연준": ["wall street", "central bank", "dollar", "interest rate"],

    "자동차": ["car", "automobile", "vehicle", "manufacturing", "showroom"],
    "현대차": ["hyundai", "car", "automobile", "manufacturing"],
    "기아": ["kia", "car", "automobile", "showroom"],
    "네이버": ["office", "technology", "workspace", "it company"],
    "카카오": ["messaging", "mobile", "startup", "office", "chat"],
    "월급": ["office", "money", "cash", "savings"],
    "일자리": ["office", "workspace", "manufacturing"],
    "고용": ["office", "workspace", "manufacturing"],
}

# 개념 -> 사진 카테고리 직결 매핑.
#
# 왜 필요한가: 사진 메타의 영문 '검색어'에만 기대면 취약하다. 실제로 인덱스를
# 복구(reindex)한 사진 109장은 검색어가 유실돼 파일명·카테고리만 남았고,
# 그 결과 '코스피' 기사가 주식증시 사진을 0점으로 평가해 엉뚱한 사진이 뽑혔다.
# 한글 개념과 우리 카테고리 체계를 직접 이어두면 메타가 부실해도 매칭이 선다.
CONCEPT_CATEGORIES = {
    "반도체": "반도체", "메모리": "SK하이닉스", "하이닉스": "SK하이닉스",
    "삼성전자": "삼성전자", "스마트폰": "삼성전자", "가전": "LG",
    "수출": "수출무역", "무역": "수출무역", "관세": "수출무역",
    "부동산": "부동산", "아파트": "부동산", "전세": "부동산",
    "월세": "부동산", "청약": "부동산",
    "금리": "금리통화", "한국은행": "금리통화",
    "대출": "은행", "예금": "은행", "은행": "은행",
    "적금": "통장", "통장": "통장", "월급": "통장",
    "주식": "주식증시", "증시": "주식증시", "코스피": "주식증시",
    "코스닥": "주식증시", "상장": "주식증시", "배당": "주식증시",
    "비트코인": "가상자산", "코인": "가상자산", "가상자산": "가상자산",
    "이더리움": "가상자산",
    "환율": "환율", "달러": "환율", "원화": "금리통화",
    "물가": "물가소비", "소비": "물가소비", "장바구니": "물가소비",
    "마트": "물가소비",
    "정부": "경제정책", "정책": "경제정책", "지원금": "경제정책",
    "예산": "경제정책", "국회": "경제정책", "세금": "경제정책",
    "연금": "노년층", "노후": "노년층", "고령": "노년층", "은퇴": "노년층",
    "미국": "글로벌경제", "월가": "글로벌경제", "나스닥": "글로벌경제",
    "연준": "글로벌경제",
    "자동차": "현대차", "현대차": "현대차", "기아": "기아",
    "네이버": "네이버", "카카오": "카카오",
}

# 이 단어가 제목·카피에 있으면 '종목 등락' 기사다 -> 사진보다 stock_thumbnail(차트)이 정답.
VOLATILITY_WORDS = ["폭락", "급락", "폭등", "급등", "신고가", "신저가", "하한가", "상한가",
                    "떡락", "떡상", "곤두박질", "반토막", "급반등", "패닉셀"]

MIN_SCORE = 3.0        # 이 밑이면 '매칭 약함'으로 경고한다
STRONG_SCORE = 8.0     # 이 이상이면 확실한 매칭


def _load_index():
    try:
        with open(INDEX_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def photo_text(fname, meta):
    """사진 한 장의 '검색 가능한 텍스트'를 한 덩어리로 만든다."""
    parts = [fname]
    if isinstance(meta, dict):
        for key in ("검색어", "credit", "카테고리", "용도", "title"):
            v = meta.get(key)
            if v:
                parts.append(str(v))
    return " ".join(parts).lower()


def photo_category_of(fname):
    """사진이 속한 카테고리. index 에 없으면 파일명 접두어로 유추한다."""
    meta = _load_index().get(fname)
    if isinstance(meta, dict) and meta.get("카테고리"):
        return meta["카테고리"]
    return fname.split("_")[0]


def article_concepts(text):
    """기사 텍스트에서 등장한 개념 키워드를 뽑는다(긴 키워드 우선)."""
    found = []
    for key in sorted(CONCEPTS, key=len, reverse=True):
        if key in text:
            found.append(key)
    return found


def score_photo(fname, meta, text, concepts, category_hint=None):
    """사진 한 장이 이 기사에 얼마나 맞는지 점수. 높을수록 좋다.

    - 카테고리 직접 일치(예: 기사에 '반도체', 사진 카테고리도 '반도체')는 크게 가산
    - 개념 사전의 영문 단어가 사진 메타에 있으면 가산
    - 기사에 없는 엉뚱한 사진은 자연히 0점에 수렴한다"""
    ptext = photo_text(fname, meta)
    cat = (meta.get("카테고리") if isinstance(meta, dict) else None) or fname.split("_")[0]
    score = 0.0
    hits = []

    # 1) 기사 텍스트에 사진 카테고리명이 그대로 등장 (가장 강한 신호)
    if cat and cat in text:
        score += 6.0
        hits.append(f"카테고리 '{cat}' 직접 언급")

    # 2) 호출부가 카테고리를 지정했으면 그 안의 사진을 우대
    if category_hint and cat == category_hint:
        score += 5.0
        hits.append(f"지정 카테고리 '{category_hint}'")

    # 3) 개념이 가리키는 카테고리와 사진 카테고리가 일치하면 강하게 가산.
    #    사진 메타(영문 검색어)가 부실해도 이 경로로 매칭이 선다.
    for c in concepts:
        if CONCEPT_CATEGORIES.get(c) == cat:
            score += 4.0
            hits.append(f"{c}->{cat}")
            break

    # 4) 개념 사전 대조. 개념 하나당 한 번만 가산한다(중복 가산 방지).
    #    index.json 에는 '용도: 수출·무역·물류 주제' 처럼 한글 설명도 들어있으므로
    #    한글 개념어가 그대로 박혀 있으면 영문 유의어보다 확실한 신호로 본다 —
    #    이걸 안 보면 port_terminal.jpg 같은 정답 사진이 저점을 받아 오탐이 난다.
    for c in concepts:
        if c in ptext:
            score += 3.0
            hits.append(f"{c}(한글 일치)")
            continue
        for word in CONCEPTS[c]:
            if word in ptext:
                score += 1.5
                hits.append(f"{c}~{word}")
                break

    return score, hits


def rank_photos(text, category_hint=None, exclude=None):
    """기사 텍스트에 맞는 사진을 점수순으로 정렬해 돌려준다.

    반환: [(파일명, 점수, [근거]), ...]  (점수 높은 순)"""
    idx = _load_index()
    exclude = exclude or set()
    concepts = article_concepts(text)
    out = []
    for fname, meta in idx.items():
        if fname.startswith("_") or not isinstance(meta, dict):
            continue
        if fname in exclude:
            continue
        if not os.path.exists(os.path.join("assets", "photos", fname)):
            continue      # index 에만 있고 실물이 없는 항목 방어
        s, hits = score_photo(fname, meta, text, concepts, category_hint)
        out.append((fname, s, hits))
    out.sort(key=lambda r: -r[1])
    return out


def best_photo(text, category_hint=None, exclude=None):
    """가장 잘 맞는 사진 하나. 반환: (파일명|None, 점수, 근거리스트)"""
    ranked = rank_photos(text, category_hint, exclude)
    if not ranked:
        return None, 0.0, []
    return ranked[0]


# 최고점과 이만큼 이내면 '똑같이 잘 맞는 후보'로 보고 회전 대상에 넣는다.
# 점수는 키워드 대조라 소수점 차이에 의미가 없다 — 1등만 쓰면 비슷한 기사마다
# 늘 같은 사진이 나와서, 매칭 기능이 오히려 돌려쓰기를 만든다.
TIE_MARGIN = 3.0


def pick_matching_photo(text, date_tag=None, seq=None, category_hint=None,
                        exclude=None):
    """기사에 맞는 사진들 중에서 '최근에 안 쓴 것'을 골라 돌려준다.

    적합도 1등만 뽑으면 물가 기사마다 같은 사진이 나온다. 그래서
    상위권(최고점 - TIE_MARGIN 이내)을 동급으로 보고, 그 안에서
    photo_library 의 순환 규칙(최근 사용분 배제 + 날짜·순번 해시)을 적용한다.
    → '맞는 사진' 안에서 '안 겹치게' 고르는 두 조건을 동시에 만족시킨다.

    반환: (파일명|None, 점수, 근거)"""
    ranked = rank_photos(text, category_hint, exclude)
    if not ranked:
        return None, 0.0, []
    top_score = ranked[0][1]
    if top_score <= 0:
        return ranked[0]
    tied = [r for r in ranked if r[1] >= top_score - TIE_MARGIN]
    if len(tied) == 1 or date_tag is None:
        return tied[0]

    # 순환: 최근 쓴 사진을 뺀 뒤 결정론적으로 하나 고른다.
    from photo_library import _load_json_safe, _seed, USAGE_PATH, recent_window
    usage = _load_json_safe(USAGE_PATH, {})
    used_recent = set()
    window = recent_window(len(tied))
    if window:
        for hist in usage.values():          # 카테고리 경계 없이 '최근 사용'을 본다
            used_recent.update(hist[-window:])
    fresh = [r for r in tied if r[0] not in used_recent] or tied
    idx = _seed("match", text[:40], date_tag, seq) % len(fresh)
    return fresh[idx]


def review_match(fname, text, category_hint=None):
    """이미 정해진 사진이 이 기사에 맞는지 '스스로 재검토'한다.

    반환: (점수, 경고문자열|None). 경고가 있으면 build_report 에 실린다 —
    조용히 이상한 사진이 나가는 것보다, 시끄럽게 걸리는 편이 낫다."""
    idx = _load_index()
    meta = idx.get(fname)
    if not isinstance(meta, dict):
        return 0.0, f"이미지 매칭 검증 불가(index.json에 {fname} 정보 없음)"
    concepts = article_concepts(text)
    score, hits = score_photo(fname, meta, text, concepts, category_hint)
    if score < MIN_SCORE:
        better, bscore, bhits = best_photo(text, category_hint)
        tip = ""
        if better and bscore > score + 2.0:
            tip = f" / 더 맞아 보이는 후보: {better}(점수 {bscore:.1f}, {', '.join(bhits[:2])})"
        return score, (f"이미지 매칭 약함: {fname} (점수 {score:.1f} < {MIN_SCORE})"
                       f" — 기사 개념 {concepts[:4]}{tip}")
    return score, None


def suggest_stock_thumbnail(text):
    """등락 기사인데 사진 썸네일을 쓰려 하면 알려준다.

    '폭락' 기사에 제품 전시 사진을 깔면 톤이 정반대로 읽힌다(제품 자랑처럼 보임).
    이런 기사는 곤두박질/급등 차트를 그리는 stock_thumbnail 이 사진보다 항상 낫다 —
    종목·방향·가격이 이미지 안에 다 들어가서 미스매치 자체가 불가능하다."""
    for w in VOLATILITY_WORDS:
        if w in text:
            return (f"등락 기사('{w}')인데 사진 썸네일을 씁니다. "
                    f"type을 stock_thumbnail 로 바꾸면 차트+로고라 미스매치가 없습니다.")
    return None
