# -*- coding: utf-8 -*-
"""실사 사진을 재게시 가능한 라이선스로만 받아 assets/photos/ 에 쌓아두는 도구.

    python fetch_photo.py "container ship port"      --name port
    python fetch_photo.py "semiconductor wafer"      --name wafer
    python fetch_photo.py "apartment construction"   --name apartment

검색어는 영어로 넣는 게 결과가 훨씬 좋다 (Openverse 인덱스가 영어 기반).

받은 뒤에는 반드시 Read 도구로 눈으로 확인하고 주제에 맞는 것만 남긴다.
검색 결과에는 무관한 사진이 반드시 섞인다 (예: '항만' 검색에 와인 항아리).

라이선스:
  - 상업이용+변형 허용(cc0/pdm/by/by-sa)만 후보로 올라온다. 뉴스 보도사진은 애초에 제외.
  - CC BY / BY-SA 는 저작자·라이선스 표기가 의무 → index.json 의 credit 을 카드에 넣는다.
  - CC0 / PDM 은 표기 의무 없음. 그래도 출처를 남기면 신뢰도에 유리하다.
"""

import argparse
import json
import os
import sys

from image_sourcing import photo_candidates

PHOTO_DIR = os.path.join("assets", "photos")
INDEX = os.path.join(PHOTO_DIR, "index.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", help='영어 검색어. 예: "container ship port"')
    ap.add_argument("--name", required=True, help="저장 접두어. 예: port")
    ap.add_argument("--limit", type=int, default=8)
    ap.add_argument("--min-width", type=int, default=1400)
    args = ap.parse_args()

    os.makedirs(PHOTO_DIR, exist_ok=True)
    report = photo_candidates(args.query, PHOTO_DIR, limit=args.limit,
                              min_width=args.min_width, prefix=args.name)

    ok = [r for r in report if "path" in r]  # error/skipped 항목은 파일이 없으므로 제외
    if not ok:
        print("후보를 못 받았습니다. 검색어를 바꾸거나 --min-width 를 낮춰보세요.")
        for r in report:
            print("  실패:", r.get("title", "")[:40], r.get("error") or r.get("skipped", ""))
        return 1

    print(f"\n{len(ok)}장을 {PHOTO_DIR}/ 에 저장했습니다. 눈으로 확인하고 고르세요.\n")
    for r in ok:
        star = "※표기필요" if r["attrib_required"] else "         "
        print(f"  {os.path.basename(r['path']):<18} {r['w']}x{r['h']:<6} "
              f"[{r['license']:<5}] {star}  {r['title'][:38]}")

    index = {}
    if os.path.exists(INDEX):
        with open(INDEX, encoding="utf-8") as f:
            index = json.load(f)
    for r in ok:
        index[os.path.basename(r["path"])] = {
            "license": r["license"],
            "credit": r["credit"],
            "attribution_required": r["attrib_required"],
            "title": r["title"],
            "source": r["landing"],
            "query": args.query,
        }
    with open(INDEX, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    print(f"\n라이선스 기록: {INDEX}")
    print("안 쓸 사진은 파일과 index 항목을 같이 지우세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
