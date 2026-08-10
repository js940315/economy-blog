# -*- coding: utf-8 -*-
"""라이브러리에 맞는 사진이 없을 때만 그 자리에서 새로 소싱한다 (하이브리드 보강).

설계 근거 (2026-08-03, 사용자와 '매번 소싱 vs 라이브러리' 논의 결과):
  '매일 전부 그때그때 소싱'은 실측으로 두 전제가 깨졌다.
    1) 저장소 절약 안 됨 — git은 파일을 지워도 히스토리에 남아 용량이 안 줄고,
       삭제 커밋 때문에 오히려 커진다(.git 203MB > 작업트리 142MB로 확인).
    2) 다양성 안 생김 — 같은 검색어는 Pexels에서 매번 '완전히 동일한' 결과를 준다
       (3회 호출 결과 ID 배열이 100% 일치). 어제 지운 사진을 오늘 또 받는다.
  게다가 무인 새벽 실행이라 육안 검수가 빠지고, 외부 API가 죽으면 발행이 멈춘다.

  그래서 라이브러리를 기본으로 두고, **정말 맞는 사진이 없을 때만** 보강한다.
  하루 10건 중 1~2건이지 10건 전부가 아니다.

같은 사진을 다시 받지 않기 위해:
  검색어별로 '다음에 볼 페이지'를 state/ondemand_pages.json 에 기록한다.
  1페이지가 늘 같으므로, 새로 소싱할 때마다 페이지를 넘겨서 새 사진을 만난다.
"""

import json
import os

from image_sourcing import stock_photo_candidates
from photo_match import (CONCEPT_CATEGORIES, CONCEPTS, SPECIFIC_SUBJECTS,
                         article_concepts)
from photo_quality import (BRIGHT_LIMIT, brightness, is_duplicate_of_library,
                           library_entries)

PHOTO_DIR = os.path.join("assets", "photos")
INDEX_PATH = os.path.join(PHOTO_DIR, "index.json")
PAGE_STATE = os.path.join("state", "ondemand_pages.json")

# 한 번에 받을 후보 수. 무인 실행이라 크게 벌리지 않는다 —
# API 부담과 '검수 없이 들어오는 사진' 리스크를 동시에 줄인다.
KEEP = 2
MAX_PAGE = 12          # 이 이상 넘어가면 검색어 자체가 고갈된 것으로 본다


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _save(path, data):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def build_query(text):
    """기사 텍스트에서 영어 검색어와 소속 카테고리를 만든다.

    반환: (검색어, 카테고리) 또는 (None, None)
    개념 사전을 그대로 재사용하므로 매칭 기준과 소싱 기준이 어긋나지 않는다 —
    '이 개념이 부족해서 소싱했는데 정작 그 개념으로 안 찾는' 사고를 막는다."""
    concepts = article_concepts(text)
    if not concepts:
        return None, None

    # ① 구체 소재(종이컵·신용점수·가전 …)가 있으면 그것을 최우선으로 찾는다.
    #    제목에 눈에 보이는 물건이 있는데 카테고리 사진(국회·거래소)을 쓰면
    #    독자는 "왜 저 사진?" 이 된다. 검색어가 구체적이라 오소싱 위험도 낮다.
    for c in concepts:
        if c in SPECIFIC_SUBJECTS:
            words = CONCEPTS.get(c, [])[:3]
            if words:
                return " ".join(words), CONCEPT_CATEGORIES.get(c) or c

    # ② 그다음이 카테고리가 매핑된 일반 개념
    for c in concepts:
        cat = CONCEPT_CATEGORIES.get(c)
        if cat:
            words = CONCEPTS.get(c, [])[:3]
            if words:
                return " ".join(words), cat
    # ⛔ 카테고리로 분류조차 안 되는 주제면 소싱하지 않는다.
    #   분류가 안 된다 = 우리 taxonomy가 못 다루는 주제 = 검색어가 막연하다는 뜻.
    #   실제로 '일자리/고용'을 'office workspace manufacturing'으로 검색했더니
    #   유럽 인쇄소 사진(타사 브랜드 로고 + 직원 얼굴)이 왔다. 무인 실행이라
    #   그대로 발행될 뻔했다 → 애매하면 기존 라이브러리를 쓰는 게 항상 낫다.
    return None, None


def source_for_article(text, verbose=True):
    """기사에 맞는 사진을 새로 받아 라이브러리에 등록하고 파일명을 돌려준다.

    실패하면 None — 호출부는 반드시 기존 라이브러리 사진으로 폴백해야 한다.
    (외부 API 장애가 발행 자체를 막으면 안 된다)"""
    query, category = build_query(text)
    if not query:
        return None

    pages = _load(PAGE_STATE, {})
    page = pages.get(query, 1)
    if page > MAX_PAGE:
        if verbose:
            print(f"  [온디맨드] '{query}' 는 {MAX_PAGE}페이지까지 소진 — 건너뜀")
        return None

    # 파일명 충돌 방지: od(on-demand) + 페이지 번호로 기존 파일과 겹치지 않게 한다
    prefix = f"{category}_od{page}"
    if verbose:
        print(f"  [온디맨드] 새로 소싱: '{query}' (page {page})")

    try:
        report = stock_photo_candidates(query, PHOTO_DIR, keep=KEEP,
                                        min_side=1200, prefix=prefix, page=page)
    except Exception as e:
        print(f"  [온디맨드] 소싱 실패({e}) — 기존 라이브러리로 폴백")
        return None

    pages[query] = page + 1          # 다음번엔 다음 페이지를 본다
    _save(PAGE_STATE, pages)

    known = library_entries()
    idx = _load(INDEX_PATH, {})
    accepted = None
    for r in report:
        if "path" not in r:
            continue
        path, fname = r["path"], os.path.basename(r["path"])

        # 무인 실행이라 육안 검수가 없다. 기계로 걸 수 있는 관문은 다 건다.
        dup = is_duplicate_of_library(path, entries=known)
        if dup and dup != fname:
            os.remove(path)
            if verbose:
                print(f"     버림(중복 {dup}): {fname}")
            continue
        mean, _ = brightness(path)
        if mean is not None and mean > BRIGHT_LIMIT + 20:
            # 너무 밝으면 흰 카피가 죽는다. dim으로도 한계가 있어 아예 안 쓴다.
            os.remove(path)
            if verbose:
                print(f"     버림(너무 밝음 {mean:.0f}): {fname}")
            continue

        idx[fname] = {
            "카테고리": category,
            "source_api": r.get("source_api", ""),
            "license": r.get("license", ""),
            "credit": r.get("credit", ""),
            "photographer": r.get("photographer", ""),
            "attribution_required": False,
            "원본해상도": f"{r.get('src_w')}x{r.get('src_h')}",
            "처리": "정사각 1400px + 시리즈 톤 + 비네트",
            "검색어": query,
            "source": r.get("landing", ""),
            "검수": "온디맨드 자동 소싱 — 육안 미검수(검수시트에서 확인할 것)",
        }
        if accepted is None:
            accepted = fname
        known.append((fname, path, category))

    if accepted:
        _save(INDEX_PATH, idx)
        if verbose:
            print(f"     채택: {accepted}")
    return accepted
