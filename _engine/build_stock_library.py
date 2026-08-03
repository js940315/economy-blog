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
import re
import sys

from image_sourcing import stock_photo_candidates
from photo_quality import is_duplicate_of_library, library_entries

DIR = os.path.join("assets", "photos")
INDEX = os.path.join(DIR, "index.json")

# 주제 11종 (스톡의 강점 — 고화질 재고 풍부). 카테고리 키는 기존 taxonomy에 맞춘다.
#
# ⭐ 검색어를 카테고리당 6~8개로 늘린 이유 (2026-08-03, "같은 사진 중복 최악"):
#   장수만 늘리면 중복이 안 풀린다. 같은 검색어로 20장을 받으면 비슷한 아파트
#   사진 20장이 쌓일 뿐이다. 진짜 다양성은 '각도(scene)'에서 나온다 —
#   그래서 한 카테고리를 여러 장면으로 쪼갠다:
#   부동산이면 [스카이라인 / 공사현장 / 부동산중개소 / 열쇠·계약 / 이사 / 빈집].
#   장면이 다르면 사진이 확실히 달라 보이고, 기사 내용에 맞춰 고를 여지도 생긴다.
#   ※ 사람이 나오는 장면(계약, 상담, 장보기)은 감정 전달이 좋아 홈판에서 강하다.
TOPICS = {
    "주식증시": ["stock market ticker board display red green",
             "stock exchange trading screen numbers finance",
             "trader looking at multiple monitors office",
             "financial chart candlestick graph screen",
             "businessman worried looking at falling chart",
             "stock exchange building exterior architecture",
             "smartphone stock trading app in hand"],
    "부동산": ["Seoul apartment complex high rise skyline",
            "modern apartment buildings residential city",
            "apartment construction site crane building",
            "real estate agency window listings",
            "house key handover contract signing",
            "moving boxes empty apartment room",
            "aerial view residential neighborhood rooftops"],
    "은행": ["bank interior counter teller hall",
           "bank vault safe deposit door",
           "atm machine cash withdrawal",
           "loan document signing desk pen",
           "bank building exterior facade columns",
           "credit card and wallet close up"],
    "가상자산": ["bitcoin cryptocurrency gold coins",
             "cryptocurrency trading chart coins blockchain",
             "crypto mining rig gpu hardware",
             "hardware wallet cold storage crypto",
             "ethereum coin dark background macro",
             "bitcoin price crash red screen"],
    "통장": ["stack of cash money savings korean won",
           "coins savings jar money finance",
           "piggy bank saving money",
           "counting banknotes hands close up",
           "household budget notebook calculator",
           "empty wallet no money"],
    "노년층": ["elderly senior couple asian smiling",
            "senior citizens retirement old people park",
            "elderly person alone window thinking",
            "senior couple reviewing documents home",
            "old hands holding cane close up",
            "retirement planning paperwork desk"],
    "경제정책": ["government building classical architecture columns",
             "parliament government complex official building",
             "press conference podium microphones",
             "official document stamp seal desk",
             "policy meeting conference room officials",
             "korean flag government building"],
    "환율": ["foreign exchange currency us dollar bills",
           "currency exchange money world finance",
           "exchange rate board digital display",
           "us dollar and korean won banknotes",
           "airport currency exchange counter",
           "global finance world map currency"],
    "반도체": ["semiconductor silicon wafer closeup",
            "microchip circuit board semiconductor technology",
            "cleanroom semiconductor manufacturing engineer",
            "robotic arm factory automation electronics",
            "memory chip macro detail",
            "data center servers racks"],
    "금리통화": ["korean won banknote cash money",
             "interest rate percent finance calculator money",
             "central bank building architecture",
             "percentage sign wooden blocks finance",
             "mortgage loan house calculator money",
             "economic graph rising interest"],
    "물가소비": ["grocery supermarket shopping cart aisle",
             "fresh produce market vegetables prices",
             "price tag label supermarket shelf",
             "traditional market stall vendor",
             "receipt grocery shopping close up",
             "empty supermarket shelves shortage",
             "family shopping cart groceries"],
    "수출무역": ["Busan port container terminal",
             "container terminal port crane",
             "cargo ship ocean freight",
             "warehouse logistics forklift boxes",
             "truck freight highway transport",
             "shipping containers stacked aerial"],
    "글로벌경제": ["Wall Street New York Stock Exchange",
              "world map global economy connection",
              "international flags summit meeting",
              "new york city financial district skyline",
              "global shipping trade world map"],
}

# 기업 7종 (일반 스톡이라 '주제성' 사진이 온다 — 실제 사옥/깃발 아님).
# 썸네일에는 좌상단 기업 로고가 자동으로 붙으므로(build_posts.auto_logo),
# 배경은 '그 업종다운 장면'이면 충분하다.
COMPANIES = {
    "삼성전자": ["samsung smartphone technology device",
             "modern electronics smartphone display",
             "smartphone factory production line",
             "consumer electronics store display wall",
             "smartphone camera macro detail"],
    "SK하이닉스": ["computer memory ram chip module",
               "semiconductor memory dram closeup",
               "server memory modules rack",
               "silicon wafer manufacturing closeup",
               "electronics circuit macro gold"],
    "기아": ["kia car vehicle",
           "modern car showroom dealership",
           "car assembly line robots",
           "electric vehicle charging station"],
    "현대차": ["hyundai car automobile",
            "car manufacturing factory automobile assembly",
            "automotive design studio clay model",
            "car export ship loading vehicles"],
    "네이버": ["technology office building modern green",
            "IT company office workspace computer",
            "data center server room blue light",
            "developers working laptops office"],
    "카카오": ["mobile messaging app smartphone chat",
            "tech startup office colorful modern",
            "people using smartphones together",
            "mobile payment qr code smartphone"],
    "LG": ["home appliances electronics modern living",
           "electronics store display appliances",
           "washing machine refrigerator kitchen modern",
           "oled tv display living room"],
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


def next_prefix_index(cat):
    """{cat}_{n}_... 형태로 이미 존재하는 n의 다음 번호를 돌려준다.

    새로 받는 사진이 기존 파일을 덮어쓰지 않게 하는 안전장치. 디스크를 직접
    보므로 index.json에 기록이 없는 파일이 있어도 안전하다."""
    pattern = re.compile(re.escape(cat) + r"_(\d+)_")
    highest = -1
    if os.path.isdir(DIR):
        for fname in os.listdir(DIR):
            m = pattern.match(fname)
            if m:
                highest = max(highest, int(m.group(1)))
    return highest + 1


def build(categories, per_category, min_side, size):
    idx = load_index()
    summary = {}
    # 이미 가진 사진 목록(중복 판정 기준). 새로 채택할 때마다 여기에 더해서
    # '이번 실행에서 방금 받은 것끼리' 겹치는 것도 잡는다.
    known = library_entries()
    for cat, queries in categories.items():
        print(f"\n=== {cat}")
        cat_kept, src_counts = 0, {}
        base_qi = next_prefix_index(cat)
        # 검색어를 나눠 각 쿼리에서 절반씩 채운다(같은 사진 반복 방지).
        want_each = max(1, (per_category + len(queries) - 1) // len(queries))
        for qi, q in enumerate(queries):
            if cat_kept >= per_category:
                break
            need = min(want_each, per_category - cat_kept)
            # ⚠ 접두어 번호는 반드시 '기존에 안 쓰인 번호'에서 시작해야 한다.
            #   예전엔 그냥 qi(0,1,2...)를 썼는데, 검색어를 늘리자 qi=0,1 이
            #   이미 있는 파일명(물가소비_0_pexels_0.jpg)과 그대로 겹쳤다.
            #   → 새 다운로드가 기존 사진을 덮어쓰고, 중복 게이트가 그걸
            #     '자기 자신과 중복'으로 보고 삭제해서 라이브러리가 줄었다(실측).
            prefix = f"{cat}_{base_qi + qi}"
            rep = stock_photo_candidates(q, DIR, keep=need, min_side=min_side,
                                         prefix=prefix, size=size)
            for r in rep:
                if "path" not in r:
                    continue
                fname = os.path.basename(r["path"])
                # 중복 게이트 — 이미 라이브러리에 있는 사진과 픽셀이 겹치면 버린다.
                # 스톡 API는 서로 다른 출처에서 같은 사진을 주기도 하고, 검색어를
                # 여러 개 쓰면 결과가 겹친다. 파일명은 다르니 순환 로직은 '다른
                # 사진'으로 착각한다 → 여기서 막아야 중복이 애초에 안 쌓인다.
                dup = is_duplicate_of_library(r["path"], entries=known)
                if dup == fname:
                    # 자기 자신과 중복 = 기존 파일을 덮어썼다는 뜻. 지우면
                    # 멀쩡한 라이브러리 사진이 사라진다. 절대 삭제하지 않는다.
                    print(f"   [경고] {fname} 이 기존 파일을 덮어썼습니다 "
                          f"(삭제하지 않음). next_prefix_index 확인 필요")
                    continue
                if dup:
                    os.remove(r["path"])
                    print(f"   중복  {fname:<26} == {dup} (버림)")
                    continue
                known.append((fname, r["path"], cat))
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
