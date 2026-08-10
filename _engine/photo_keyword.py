# -*- coding: utf-8 -*-
"""제목의 핵심 키워드를 그대로 배경 사진으로 만든다 (사전 없이).

왜 만들었나 (2026-08-10, 사용자 지적):
  "앞으로 하나씩 이렇게 지정으로 하면 밑도 끝도 없다. 제목에 나오는 핵심
  키워드가 배경으로 나오도록 시스템을 만들어라."
  맞는 말이다. 종이컵·하이마트·신용점수를 사전에 한 줄씩 추가하는 방식은
  새 소재가 나올 때마다 사람이 손을 대야 해서 자동화가 아니다.

어떻게 사전을 없앴나:
  Pixabay 는 lang=ko 로 **한국어 질의를 실제로 이해한다**(실측 2026-08-10).
    종이컵   -> 태그: 종이컵, 친환경 컵, 커피잔      ✅
    신용점수 -> 태그: 신용 카드, 직불 카드, 은행     ✅
    커피     -> 태그: 커피, 커피 컵, 에스프레소      ✅
  (Pexels 의 locale=ko-KR 은 응답 문구만 번역할 뿐 검색은 엉뚱했다 —
   '신용점수'에 쇼핑하는 여성이 나왔다. 그래서 한국어 검색은 Pixabay 로 한다.)

  그래서 한글 -> 영어 번역 사전이 통째로 필요 없다. 제목에서 명사 후보를
  뽑아 한국어 그대로 던지면 된다.

관련성 검증이 핵심:
  Pixabay 는 없는 말에도 아무거나 돌려준다 — '하이마트'에 개 초상 사진이
  왔다(실측). 그래서 **돌아온 사진의 태그에 질의어가 실제로 들어있는지**를
  확인하고, 아니면 그 후보를 버린다. 이 게이트가 없으면 엉뚱한 사진이
  '자동으로' 나가서 지금보다 나빠진다.
"""

import json
import os
import re
import urllib.parse
import urllib.request

from image_sourcing import STOCK_UA

# 조사·어미. 한국어는 명사 뒤에 이것들이 붙으므로 떼어내면 대개 명사가 남는다.
_JOSA = ("으로써", "으로서", "에서는", "에게서", "이라는", "라는", "부터", "까지",
         "에서", "에게", "한테", "으로", "라도", "이나", "밖에", "조차", "마저",
         "처럼", "보다", "만큼", "이란", "은", "는", "이", "가", "을", "를",
         "에", "의", "도", "만", "와", "과", "로", "께", "야", "다", "요")

# 이미지로 만들 수 없는 말들. '무엇을 찍을 수 없는가' 기준의 최소 목록이라
# 소재가 늘어도 여기는 커지지 않는다(사전과 다른 점).
_STOP = {
    "정부", "발표", "확정", "추진", "검토", "결정", "논란", "전망", "예상", "가능",
    "시작", "종료", "확대", "축소", "인상", "인하", "증가", "감소", "상승", "하락",
    "역대", "최고", "최저", "사상", "이번", "지난", "올해", "내년", "작년", "다시",
    "결국", "진짜", "정말", "그냥", "이제", "아직", "벌써", "무슨", "이런", "저런",
    "때문", "이유", "경우", "상황", "문제", "방법", "계획", "정책", "제도", "기준",
    "우리", "여러분", "사람", "국민", "관련", "대비", "기록", "수준", "규모", "효과",
}


# 용언(동사·형용사) 활용 흔적. 이게 들어있으면 명사가 아니다.
# '금지하겠답니', '높아졌습니', '억울하다고' 가 명사로 잡혀 엉뚱한 사진이
# 검색된 실측(2026-08-10) 때문에 넣었다. 명사만 남겨야 사진이 맞는다.
_VERBISH = re.compile(
    r"(하겠|했|합니|습니|었|았|겠|하다|한다|된다|되는|하는|하고|하며|하면"
    r"|다고|라고|는데|지만|어요|아요|네요|군요|더라|랍니|답니|까지도)")
# 용언은 대개 이 글자로 끝난다(명사는 드물다)
_VERB_TAIL = ("다", "요", "죠", "네", "군", "지", "고", "며", "면", "서", "니")


def _looks_like_noun(w):
    if _VERBISH.search(w):
        return False
    if len(w) > 2 and w.endswith(_VERB_TAIL):
        return False
    return True


def extract_keywords(*texts, limit=5):
    """제목·카피에서 배경 후보가 될 명사를 뽑는다. 사전을 쓰지 않는다.

    규칙만 쓴다: 한글 덩어리를 자르고 -> 조사를 떼고 -> 용언(동사·형용사)을
    걸러내고 -> 찍을 수 없는 추상어를 걸러낸 뒤 돌려준다.

    ⚠ 길이순으로 정렬하면 안 된다. 활용형이 명사보다 길어서 '금지하겠답니'가
    '종이컵'을 제치고 1순위가 됐다(실측). 제목은 주제를 앞에서 말하므로
    '나온 순서'가 훨씬 나은 신호다."""
    blob = " ".join(t for t in texts if t)
    cands, seen = [], set()
    for w in re.findall(r"[가-힣]{2,}", blob):
        for j in _JOSA:                       # 조사는 긴 것부터 떼야 정확하다
            if len(w) > 2 and w.endswith(j):
                w = w[: -len(j)]
                break
        if len(w) < 2 or w in _STOP or w in seen or not _looks_like_noun(w):
            continue
        seen.add(w)
        cands.append(w)                       # 등장 순서 유지
    return cands[:limit]


def _pixabay_ko(query, per_page=8, timeout=25):
    """Pixabay 한국어 검색. 반환: [{tags, url, w, h}, ...]"""
    key = os.getenv("PIXABAY_API_KEY")
    if not key:
        return []
    url = "https://pixabay.com/api/?" + urllib.parse.urlencode({
        "key": key, "q": query, "lang": "ko", "image_type": "photo",
        "per_page": per_page, "safesearch": "true", "order": "popular",
    })
    try:
        req = urllib.request.Request(url, headers=STOCK_UA)
        data = json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode())
    except Exception:
        return []
    return [{"tags": h.get("tags", ""), "url": h.get("largeImageURL") or h.get("webformatURL"),
             "w": h.get("imageWidth", 0), "h": h.get("imageHeight", 0)}
            for h in data.get("hits", [])]


def _relevant(keyword, tags, head=3):
    """돌아온 사진이 정말 그 키워드의 사진인지 태그로 검증한다.

    Pixabay 는 모르는 말에도 아무거나 돌려준다('하이마트' -> 개 초상 사진).
    검증 규칙 두 가지 — 둘 다 실측 사고에서 나왔다(2026-08-10):
      1) 부분 일치를 허용하면 안 된다. '코스피' 가 '롤러 코스터' 의 '코스' 에
         걸려 놀이공원 사진이 통과했다. **키워드 전체**가 태그에 있어야 한다.
      2) 태그 아무 데나가 아니라 **앞쪽 태그**여야 한다. Pixabay 태그는 대략
         관련도순인데, '장바구니' 가 뒤쪽 태그에 걸려 염소 사진이 통과했다.
    """
    parts = [t.strip() for t in (tags or "").split(",") if t.strip()]
    return any(keyword in t for t in parts[:head])


def keyword_photo_url(*texts, verbose=True):
    """제목에서 뽑은 키워드로 한국어 검색해 '검증된' 사진 URL을 돌려준다.

    반환: (url, 키워드, 해상도문자열) 또는 (None, None, 사유)
    후보를 순서대로 시도하다 태그 검증을 통과하는 첫 키워드를 채택한다."""
    kws = extract_keywords(*texts)
    if not kws:
        return None, None, "제목에서 명사를 못 뽑음"
    if verbose:
        print(f"  [키워드] 후보: {kws}")
    for kw in kws:
        hits = _pixabay_ko(kw)
        ok = [h for h in hits if _relevant(kw, h["tags"]) and h["url"]]
        if not ok:
            if verbose and hits:
                print(f"     '{kw}' 관련성 미달(태그 불일치) — 다음 후보")
            continue
        ok.sort(key=lambda h: -(h["w"] * h["h"]))
        best = ok[0]
        if verbose:
            print(f"     '{kw}' 채택: {best['w']}x{best['h']} / 태그 {best['tags'][:40]}")
        return best["url"], kw, f"{best['w']}x{best['h']}"
    return None, None, f"후보 {kws} 전부 관련 사진 없음"
