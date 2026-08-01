# -*- coding: utf-8 -*-
"""카테고리별 사진 라이브러리를 미리 채워두는 도구.

매일 아침 기사마다 사진을 새로 검색하면 (1) 느리고 (2) 429에 걸리고
(3) 무관한 사진이 걸려도 아무도 못 잡는다. 그래서 미리 카테고리별로 쌓아두고
매일은 '고르기만' 하는 구조로 간다.

    python build_photo_library.py            # 전체 카테고리
    python build_photo_library.py 수출무역    # 특정 카테고리만

받은 뒤 Read 도구로 눈으로 확인하고, 주제에 안 맞는 파일은 지운다.
지우면 index.json 도 같이 정리해야 하므로 --prune 으로 정리한다.

소스는 Wikimedia Commons 직접 경로만 쓴다:
  - Openverse는 rawpixel 등이 축소본(1024px)만 줘서 카드(1080px)에 못 쓴다
  - korea.kr(정책브리핑)은 720px 상한 + 항목별 공공누리 부착 여부 확인 필요라 제외
"""

import argparse
import json
import os
import sys

from image_sourcing import prepare_photo, wikimedia_photo_candidates

DIR = os.path.join("assets", "photos")
INDEX = os.path.join(DIR, "index.json")

# 카테고리 -> 검색어. 한국 소재를 우선하되, 한국 사진이 부족한 주제는
# 일반 소재로 보완한다 (Commons는 한국 사진 재고가 서구권보다 적다).
CATEGORIES = {
    "수출무역": ["Busan port container terminal", "container terminal port crane"],
    "반도체": ["semiconductor wafer fab", "cleanroom semiconductor manufacturing"],
    "부동산": ["Seoul apartment complex", "apartment building construction Korea"],
    "주식증시": ["stock exchange trading floor", "stock market chart screen trading"],
    "경제정책": ["Government Complex Seoul", "National Assembly Building Korea"],
    "금리통화": ["Bank of Korea building", "South Korean won banknote"],
    "고용노동": ["office building interior workers desk", "construction workers site"],
    "물가소비": ["Korean traditional market", "supermarket shelves grocery"],
    "글로벌경제": ["Wall Street New York Stock Exchange", "shipping global trade"],
}


def load_index():
    if os.path.exists(INDEX):
        with open(INDEX, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_index(idx):
    with open(INDEX, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=2)


def prune(idx):
    """파일이 지워진 항목을 index에서 정리한다."""
    gone = [k for k in idx if not k.startswith("_") and
            not os.path.exists(os.path.join(DIR, k))]
    for k in gone:
        idx.pop(k)
    return gone


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("category", nargs="?", help="특정 카테고리만 (생략 시 전체)")
    ap.add_argument("--per", type=int, default=2, help="검색어당 채택 수")
    ap.add_argument("--min-width", type=int, default=1600)
    ap.add_argument("--prune", action="store_true", help="index 정리만 하고 종료")
    args = ap.parse_args()

    os.makedirs(DIR, exist_ok=True)
    idx = load_index()

    if args.prune:
        gone = prune(idx)
        save_index(idx)
        print(f"index에서 {len(gone)}건 정리: {gone}")
        return 0

    targets = ({args.category: CATEGORIES[args.category]}
               if args.category else CATEGORIES)
    if args.category and args.category not in CATEGORIES:
        print("없는 카테고리입니다. 가능한 값:", ", ".join(CATEGORIES))
        return 1

    total_ok = total_skip = 0
    for cat, queries in targets.items():
        print(f"\n=== {cat}")
        for qi, q in enumerate(queries):
            prefix = f"{cat}_{qi}"
            rep = wikimedia_photo_candidates(q, DIR, limit=args.per,
                                             min_width=args.min_width,
                                             prefix=prefix)
            for r in rep:
                if "path" in r:
                    fname = os.path.basename(r["path"])
                    # 카드 규격(정사각 1400px)으로 미리 가공해 둔다
                    try:
                        prepare_photo(r["path"], r["path"], size=1400)
                        w = h = 1400
                    except Exception as e:
                        print(f"   가공 실패 {fname}: {str(e)[:40]}")
                        w, h = r["w"], r["h"]
                    idx[fname] = {
                        "카테고리": cat,
                        "license": r["license"],
                        "credit": r["credit"],
                        "attribution_required": True,
                        "원본해상도": f"{r.get('src_w')}x{r.get('src_h')}",
                        "처리": "정사각 1400px + 시리즈 톤 + 비네트",
                        "검색어": q,
                        "검수": "미확인 — Read로 눈 확인 필요",
                    }
                    print(f"   OK   {fname:<22} 원본 {r.get('src_w')}x{r.get('src_h')} [{r['license']}]")
                    total_ok += 1
                elif "skipped" in r:
                    total_skip += 1

    save_index(idx)
    print(f"\n채택 {total_ok}장 / 폐기 {total_skip}건 -> {DIR}/")
    print("이제 Read 도구로 각 파일을 열어 주제에 맞는지 확인하세요.")
    print("안 맞는 건 파일 삭제 후: python build_photo_library.py --prune")
    return 0


if __name__ == "__main__":
    sys.exit(main())
