# -*- coding: utf-8 -*-
"""공인의 인물 사진을 라이선스가 열린 소스에서만 받아 assets/portraits/ 에 쌓는 도구.

    python fetch_portrait.py "Jensen Huang" --name jensen
    python fetch_portrait.py "Rhee Chang-yong Bank of Korea" --name rhee
    python fetch_portrait.py "Lee Jae-yong Samsung" --name leejy

판단 기준 (중요):
  금지 대상은 '실존 인물'이 아니라 '재게시 권리가 없는 사진'이다.
  공인을 그의 공적 활동(실적·정책 발표 등)과 함께 보도·정보전달 맥락에서 다루는 것은 문제없다.
  실제 리스크는 언론사 보도사진의 무단 전재이므로, 이 도구는 아래 라이선스만 통과시킨다:
    Public domain / CC0 / CC BY / CC BY-SA / KOGL 제1유형(공공누리)
  NC(비상업)·ND(변형금지)는 자동 제외한다.

넘지 말 선:
  - 상업적 보증·후원처럼 보이게 쓰지 않는다 (특정 상품 추천에 인물 얼굴을 붙이는 것)
  - 명예훼손·비하·허위사실과 결합하지 않는다
  - 공적 역할과 무관한 사적인 사진은 쓰지 않는다

검색 팁:
  - 영문 정식 표기 + 소속을 함께 넣는다 ("Chey Tae-won SK", "Chung Euisun Hyundai")
  - 한국 재계 인사는 CC 단독 초상이 드물다. 단체·행사 사진만 나오면 무리해서 쓰지 말고
    사옥·로고·제품·반도체·전광판 등 관련 사물 이미지로 대체한다 (fetch_photo.py 사용).
"""

import argparse
import json
import os
import sys

from image_sourcing import portrait_candidates

DIR = os.path.join("assets", "portraits")
INDEX = os.path.join(DIR, "index.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", help='영문 이름 + 소속. 예: "Jensen Huang"')
    ap.add_argument("--name", required=True, help="저장 접두어")
    ap.add_argument("--limit", type=int, default=4)
    ap.add_argument("--min-width", type=int, default=1200)
    args = ap.parse_args()

    os.makedirs(DIR, exist_ok=True)
    report = portrait_candidates(args.query, DIR, limit=args.limit,
                                 min_width=args.min_width, prefix=args.name)

    ok = [r for r in report if "path" in r]
    skipped = [r for r in report if "skipped" in r]

    if not ok:
        print("라이선스 통과 후보가 없습니다.")
        for r in skipped:
            print(f"  제외 [{r['license']}] {r['title'][:50]}")
        print("\n인물 사진 대신 관련 사물로 대체하세요:")
        print('  python fetch_photo.py "semiconductor wafer factory" --name wafer')
        return 1

    print(f"\n{len(ok)}장 저장. 반드시 Read로 얼굴을 확인하고 본인이 맞는지 검수하세요.\n")
    for r in ok:
        print(f"  {os.path.basename(r['path']):<20} {r['w']}x{r['h']:<6} "
              f"[{r['license']:<16}] {r['title'][:44]}")
    if skipped:
        print(f"\n  (라이선스 부적합으로 {len(skipped)}건 제외)")

    index = {}
    if os.path.exists(INDEX):
        with open(INDEX, encoding="utf-8") as f:
            index = json.load(f)
    for r in ok:
        index[os.path.basename(r["path"])] = {
            "license": r["license"],
            "credit": r["credit"],
            "attribution_required": True,   # CC BY/BY-SA/KOGL 전부 출처표시 조건
            "title": r["title"],
            "query": args.query,
        }
    with open(INDEX, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    print(f"\n라이선스 기록: {INDEX}")
    print("카드에 넣을 때 credit 문자열을 그대로 하단에 표기하세요 (출처표시가 조건입니다).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
