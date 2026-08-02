# -*- coding: utf-8 -*-
"""프리미엄 스톡 API(Pexels/Unsplash/Pixabay)로 카테고리별 사진 라이브러리를 채운다.

build_photo_library.py 의 스톡 API 버전. 매일 아침 검색하지 않고 미리 쌓아두고
photo_library.pick_photo 가 (카테고리, 날짜, 순번)으로 순환 선택하게 하는 구조.

    python build_stock_library.py                # 전체 카테고리
    python build_stock_library.py 부동산 은행     # 특정 카테고리만
    python build_stock_library.py --topics       # 주제 9종만
    python build_stock_library.py --companies    # 기업 7종만

키는 환경변수에서만 읽는다: PEXELS_API_KEY / UNSPLASH_ACCESS_KEY / PIXABAY_API_KEY
(코드/커밋에 값이 들어가지 않는다.)

주의:
  - 세 API 모두 워터마크 없음 + 무료 상업 재게시 허용(출처표시 의무 없음, 권장).
  - '리사이즈본'(정사각 1400px)만 assets/photos/ 에 저장된다 — 대용량 원본은 저장 안 함.
  - 스톡은 curated라 무관 사진이 적지만 0은 아니다. 받은 뒤 몽타주로 눈 확인 권장.
  - 기업(삼성전자 등) 검색은 일반 스톡이라 '실제 사옥/깃발'이 아니라 주제성(스마트폰/
    자동차/칩 등) 사진이 온다. index.json 의 검색어/출처로 무엇인지 추적 가능.
"""

import argparse
import json
import os
import sys

from image_sourcing import stock_photo_candidates

DIR = os.path.join("assets", "photos")
INDEX = os.path.join(DIR, "index.json")

# 주제 9종 (스톡의 강점 — 고화질 재고 풍부). 카테고리 키는 기존 taxonomy에 맞춘다.
TOPICS = {
    "주식증시": ["stock market ticker board display red green",
             "stock exchange trading screen numbers finance"],
    "부동산": ["Seoul apartment complex high rise skyline",
            "modern apartment buildings residential city"],
    "은행": ["bank interior counter teller hall",
           "bank vault safe deposit door"],
    "가상자산": ["bitcoin cryptocurrency gold coins",
             "cryptocurrency trading chart coins blockchain"],
    "통장": ["stack of cash money savings korean won",
           "coins savings jar money finance"],
    "노년층": ["elderly senior couple asian smiling",
            "senior citizens retirement old people park"],
    "경제정책": ["government building classical architecture columns",
             "parliament government complex official building"],
    "환율": ["foreign exchange currency us dollar bills",
           "currency exchange money world finance"],
    "반도체": ["semiconductor silicon wafer closeup",
            "microchip circuit board semiconductor technology"],
    "금리통화": ["korean won banknote cash money",
             "interest rate percent finance calculator money"],
    "물가소비": ["grocery supermarket shopping cart aisle",
             "fresh produce market vegetables prices"],
}

# 기업 7종 (일반 스톡이라 '주제성' 사진이 온다 — 실제 사옥/깃발 아님).
COMPANIES = {
    "삼성전자": ["samsung smartphone technology device",
             "modern electronics smartphone display"],
    "SK하이닉스": ["computer memory ram chip module",
               "semiconductor memory dram closeup"],
    "기아": ["kia car vehicle",
           "modern car showroom dealership"],
    "현대차": ["hyundai car automobile",
            "car manufacturing factory automobile assembly"],
    "네이버": ["technology office building modern green",
            "IT company office workspace computer"],
    "카카오": ["mobile messaging app smartphone chat",
            "tech startup office colorful modern"],
    "LG": ["home appliances electronics modern living",
           "electronics store display appliances"],
}

ALL = {**TOPICS, **COMPANIES}


def load_index():
    if os.path.exists(INDEX):
        with open(INDEX, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_index(idx):
    # 원자적 저장: 임시파일에 다 쓰고 os.replace로 교체 → 쓰는 중 크래시해도
    # index.json이 반쯤 쓰이거나 0바이트로 손상되지 않는다.
    tmp = INDEX + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, INDEX)


def build(categories, per_category, min_side, size):
    idx = load_index()
    summary = {}
    for cat, queries in categories.items():
        print(f"\n=== {cat}")
        cat_kept, src_counts = 0, {}
        # 검색어를 나눠 각 쿼리에서 절반씩 채운다(같은 사진 반복 방지).
        want_each = max(1, (per_category + len(queries) - 1) // len(queries))
        for qi, q in enumerate(queries):
            if cat_kept >= per_category:
                break
            need = min(want_each, per_category - cat_kept)
            prefix = f"{cat}_{qi}"
            rep = stock_photo_candidates(q, DIR, keep=need, min_side=min_side,
                                         prefix=prefix, size=size)
            for r in rep:
                if "path" not in r:
                    continue
                fname = os.path.basename(r["path"])
                api = r["source_api"]
                src_counts[api] = src_counts.get(api, 0) + 1
                idx[fname] = {
                    "카테고리": cat,
                    "source_api": api,
                    "license": r["license"],
                    "credit": r["credit"],
                    "photographer": r.get("photographer", ""),
                    "attribution_required": False,
                    "원본해상도": f"{r.get('src_w')}x{r.get('src_h')}",
                    "처리": "정사각 1400px + 시리즈 톤 + 비네트",
                    "검색어": q,
                    "source": r.get("landing", ""),
                    "검수": "스톡 API(워터마크 없음) — 스팟체크",
                }
                print(f"   OK   {fname:<26} [{api}] 원본 {r.get('src_w')}x{r.get('src_h')}")
                cat_kept += 1
        summary[cat] = {"kept": cat_kept, "by_source": src_counts}
    save_index(idx)
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("categories", nargs="*", help="특정 카테고리만 (생략 시 대상 전체)")
    ap.add_argument("--topics", action="store_true", help="주제 9종만")
    ap.add_argument("--companies", action="store_true", help="기업 7종만")
    ap.add_argument("--per", type=int, default=6, help="카테고리당 목표 장수")
    ap.add_argument("--min-side", type=int, default=1120, help="실제 짧은 변 최소 픽셀")
    ap.add_argument("--size", type=int, default=1400, help="정사각 출력 픽셀")
    args = ap.parse_args()

    os.makedirs(DIR, exist_ok=True)

    if args.categories:
        pool = {c: ALL[c] for c in args.categories if c in ALL}
        missing = [c for c in args.categories if c not in ALL]
        if missing:
            print("없는 카테고리:", ", ".join(missing))
            print("가능:", ", ".join(ALL))
            if not pool:
                return 1
    elif args.topics:
        pool = TOPICS
    elif args.companies:
        pool = COMPANIES
    else:
        pool = ALL

    summary = build(pool, args.per, args.min_side, args.size)

    print("\n\n========== 요약 ==========")
    total, by_src = 0, {}
    for cat, s in summary.items():
        total += s["kept"]
        for k, v in s["by_source"].items():
            by_src[k] = by_src.get(k, 0) + v
        srcs = ", ".join(f"{k}:{v}" for k, v in s["by_source"].items()) or "(0)"
        print(f"  {cat:<10} {s['kept']}장  [{srcs}]")
    print(f"\n  합계 {total}장  소스별 { {k: by_src[k] for k in sorted(by_src)} }")
    print(f"  -> {DIR}/  (index.json 갱신)")
    print("  다음: 몽타주로 눈 확인 → 무관/워터마크 파일 삭제 → git add -f 로 확정만 추가")
    return 0


if __name__ == "__main__":
    sys.exit(main())
