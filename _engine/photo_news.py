# -*- coding: utf-8 -*-
"""기사 원문의 대표사진을 썸네일 배경으로 가져온다 (인스타 save_money_119 방식).

왜 만들었나 (2026-08-09, 사용자 지적):
  같은 사람이 운영하는 인스타(save_money_119)는 이재명·구윤철 같은 실제 당사자
  사진이 정확히 붙는데, 네이버 블로그는 외국인 회의 스톡이 붙는다. 소싱 도구는
  똑같은데 결과가 다른 이유는 **어디서 가져오느냐**였다.

  인스타 파이프라인(_cardnews_tools/onepage_cardnews_template.py)의 원칙:
    - 정부정책·기업 주제는 실제 관련 인물 사진을 쓴다
    - 뉴스 기사의 대표사진(og:image)을 여러 매체에서 후보로 모은다
    - 실제로 내려받아 픽셀을 비교하고 가장 큰 것을 채택한다
    - 짧은 변 1080px 미만이면 화질이 뭉개지므로 다른 후보를 찾는다
    - 정부기관·기업 뉴스룸 원본을 언론사보다 우선한다

  경제비버는 이 함수들(article_hero_image / pick_best_image / source_tier)을
  이미 갖고 있으면서 **한 번도 호출하지 않았다.** 정적 스톡 라이브러리에서만
  골랐기 때문에 기사와 무관한 사진이 나온 것이다. 이 모듈이 그 연결을 만든다.

주의:
  - 기사 원문 사진은 통신사·언론사 사진인 경우가 많다. 출처를 index 에 남겨
    사람이 판단할 수 있게 한다. 자동 판단하지 않는다.
  - 화질 미달(짧은 변 < MIN_SIDE)이면 채택하지 않고 None 을 돌려준다.
    업스케일하지 않는다 — 뭉갠 사진은 스톡보다 나쁘다.
"""

import json
import os
import re

from image_sourcing import (article_hero_image, fetch_image, naver_thumb_to_original,
                            pick_best_image, prepare_photo, source_tier)

# og:image 는 대개 '축소본'이다. 파일명 뒤에 붙는 크기 접미사를 떼면 원본이 나온다.
# 실측(2026-08-09):
#   newspim  ..._tc.jpg  300x200   ->  ....jpg   600x400
#   fnnews   ..._l.jpg   800x598   ->  ....jpg   4767x3568   (8배)
# 이 한 줄 때문에 "화질 미달"로 버려지던 보도사진이 대부분 살아난다.
_SHRINK_SUFFIX = re.compile(
    r"_(tc|tn|th|thumb|s|m|l|web|small|medium|large|\d{2,4})(?=\.(jpg|jpeg|png)$)",
    re.I)


def upsize_variants(url):
    """원본일 가능성이 있는 URL 변형들을 생성한다(원래 URL 포함, 큰 것 우선 시도).

    실패해도 손해가 없다 — pick_best_image 가 실제 픽셀을 재서 고르므로,
    404 가 나면 그 후보만 빠지고 나머지로 판단한다."""
    out = [url]
    stripped = _SHRINK_SUFFIX.sub("", url)
    if stripped != url:
        out.insert(0, stripped)          # 원본 후보를 앞에 둔다
    # 쿼리로 크기를 주는 CDN (?w=800, ?type=w640 등)은 쿼리를 떼어본다
    if "?" in url:
        out.append(url.split("?", 1)[0])
    return out

PHOTO_DIR = os.path.join("assets", "photos")
INDEX_PATH = os.path.join(PHOTO_DIR, "index.json")

# 짧은 변 기준. 1080 카드에 채우므로 이보다 작으면 업스케일로 뭉개진다.
MIN_SIDE = 1000
CACHE_DIR = os.path.join("state", "news_photos")


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _save_index(entry_name, meta):
    idx = _load(INDEX_PATH, {})
    idx[entry_name] = meta
    tmp = INDEX_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, INDEX_PATH)


def hero_candidates(article_urls, verbose=True):
    """기사 URL 목록에서 대표사진(og:image) 후보 URL을 모은다.

    여러 매체를 넣을수록 좋다 — 같은 사건이라도 매체마다 호스팅 해상도가
    다르기 때문에(A매체 720px, B매체 1440px) 후보가 많아야 큰 걸 고를 수 있다."""
    urls = []
    for u in article_urls or []:
        if not u:
            continue
        try:
            hero = article_hero_image(u)
        except Exception:
            hero = None
        if not hero:
            if verbose:
                print(f"     대표사진 없음: {u[:60]}")
            continue
        hero = naver_thumb_to_original(hero)
        # og:image 는 축소본인 경우가 대부분이라 '원본 후보'를 함께 넣는다.
        for v in upsize_variants(hero):
            if v not in urls:
                urls.append(v)
    # 정부기관·기업 뉴스룸(tier 1) -> 통신사(2) 순으로 먼저 시도한다
    urls.sort(key=source_tier)
    return urls


def news_hero_photo(article_urls, seq_tag, verbose=True):
    """기사 원문 대표사진을 받아 카드 규격(정사각 1400)으로 저장한다.

    반환: (assets/photos 기준 파일명, 메타dict) 또는 (None, 사유문자열)
    실패해도 예외를 던지지 않는다 — 호출부는 기존 라이브러리로 폴백해야 한다."""
    cands = hero_candidates(article_urls, verbose=verbose)
    if not cands:
        return None, "기사에서 대표사진을 못 찾음"

    os.makedirs(CACHE_DIR, exist_ok=True)
    try:
        best, _report = pick_best_image(cands, CACHE_DIR, min_side=MIN_SIDE,
                                        prefix=f"hero_{seq_tag}")
    except Exception as e:
        return None, f"후보 다운로드 실패({e})"
    if not best:
        return None, "후보를 하나도 내려받지 못함"
    if not best.get("meets_min"):
        # 업스케일하면 뭉갠다. 차라리 스톡이 낫다.
        return None, (f"화질 미달(짧은 변 {best.get('min_side')}px < {MIN_SIDE}) "
                      f"— 업스케일하지 않고 라이브러리로 대체")

    fname = f"뉴스_{seq_tag}.jpg"
    dst = os.path.join(PHOTO_DIR, fname)
    # 인물이 주인공인 보도사진이 많아 focus='top' 이 얼굴을 살린다
    prepare_photo(best["path"], dst, size=1400, focus="top")
    meta = {
        "카테고리": "뉴스원문",
        "source": best.get("url", ""),
        "출처호스트": best.get("host", ""),
        "tier": best.get("tier"),
        "원본해상도": f"{best.get('w')}x{best.get('h')}",
        "처리": "정사각 1400px + 시리즈 톤 + 비네트 (focus=top)",
        "검수": "기사 원문 대표사진 — 출처 확인 후 사용",
    }
    _save_index(fname, meta)
    if verbose:
        print(f"     채택: {fname}  {meta['원본해상도']} "
              f"[{meta['출처호스트']} tier{meta['tier']}]")
    try:
        os.remove(best["path"])          # 임시 원본은 남기지 않는다
    except OSError:
        pass
    return fname, meta
