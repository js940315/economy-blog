# -*- coding: utf-8 -*-
"""실사 사진을 재게시 가능한 라이선스로만 받아 assets/photos/ 에 쌓아두는 도구.

    python fetch_photo.py "container ship port"      --name port
    python fetch_photo.py "semiconductor wafer"      --name wafer
    python fetch_photo.py "apartment construction"   --name apartment

검색어는 영어로 넣는 게 결과가 훨씬 좋다 (Openverse 인덱스가 영어 기반).

프리미엄 스톡 API(Pexels/Unsplash/Pixabay)로도 받을 수 있다 (--stock):

    python fetch_photo.py "apartment complex Seoul" --name 부동산 --stock
    python fetch_photo.py "bank vault"               --name 은행   --stock --keep 6

키는 환경변수에서만 읽는다: PEXELS_API_KEY / UNSPLASH_ACCESS_KEY / PIXABAY_API_KEY
(코드/커밋엔 값이 절대 들어가지 않는다). 세 곳 모두 워터마크 없음 + 무료 상업 재게시 허용.

받은 뒤에는 반드시 Read 도구로 눈으로 확인하고 주제에 맞는 것만 남긴다.
검색 결과에는 무관한 사진이 반드시 섞인다 (예: '항만' 검색에 와인 항아리).

라이선스:
  - (기본, Openverse) 상업이용+변형 허용(cc0/pdm/by/by-sa)만 후보로 올라온다. 뉴스 보도사진 제외.
  - CC BY / BY-SA 는 저작자·라이선스 표기가 의무 → index.json 의 credit 을 카드에 넣는다.
  - CC0 / PDM 은 표기 의무 없음. 그래도 출처를 남기면 신뢰도에 유리하다.
  - (--stock) Pexels/Unsplash/Pixabay 라이선스는 표기 의무 없음(권장). photographer/출처는 index.json에 기록.
"""

import argparse
import json
import os
import sys

from image_sourcing import photo_candidates, stock_photo_candidates

PHOTO_DIR = os.path.join("assets", "photos")
INDEX = os.path.join(PHOTO_DIR, "index.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", help='영어 검색어. 예: "container ship port"')
    ap.add_argument("--name", required=True, help="저장 접두어. 예: port (스톡 모드에선 카테고리로도 기록)")
    ap.add_argument("--limit", type=int, default=8)
    ap.add_argument("--min-width", type=int, default=1400)
    ap.add_argument("--stock", action="store_true",
                    help="Openverse 대신 Pexels/Unsplash/Pixabay(프리미엄 스톡)에서 소싱")
    ap.add_argument("--keep", type=int, default=6, help="스톡 모드에서 채택할 장수")
    ap.add_argument("--min-side", type=int, default=1200, help="스톡 모드 실제 짧은 변 최소 픽셀")
    args = ap.parse_args()

    os.makedirs(PHOTO_DIR, exist_ok=True)

    if args.stock:
        report = stock_photo_candidates(args.query, PHOTO_DIR, keep=args.keep,
                                        min_side=args.min_side, prefix=args.name)
    else:
        report = photo_candidates(args.query, PHOTO_DIR, limit=args.limit,
                                  min_width=args.min_width, prefix=args.name)

    ok = [r for r in report if "path" in r]  # error/skipped 항목은 파일이 없으므로 제외
    if not ok:
        print("후보를 못 받았습니다. 검색어를 바꾸거나 --min-width/--min-side 를 낮춰보세요.")
        for r in report:
            print("  실패:", str(r.get("title", r.get("id", "")))[:40],
                  r.get("error") or r.get("skipped", ""))
        return 1

    print(f"\n{len(ok)}장을 {PHOTO_DIR}/ 에 저장했습니다. 눈으로 확인하고 고르세요.\n")
    for r in ok:
        star = "※표기필요" if r.get("attrib_required") else "         "
        tag = r.get("source_api", r.get("title", ""))
        print(f"  {os.path.basename(r['path']):<22} {r['w']}x{r['h']:<6} "
              f"[{r['license']:<20}] {star}  {str(tag)[:24]}")

    index = {}
    if os.path.exists(INDEX):
        with open(INDEX, encoding="utf-8") as f:
            index = json.load(f)
    for r in ok:
        entry = {
            "license": r["license"],
            "credit": r["credit"],
            "attribution_required": r.get("attrib_required", False),
            "source": r["landing"],
            "query": args.query,
        }
        if args.stock:
            # 스톡 모드: 카테고리(=name)·소스·촬영자·원본해상도까지 남겨 순환선택/추적에 쓴다
            entry["카테고리"] = args.name
            entry["source_api"] = r.get("source_api")
            entry["photographer"] = r.get("photographer", "")
            entry["원본해상도"] = f"{r.get('src_w')}x{r.get('src_h')}"
            entry["처리"] = "정사각 1400px + 시리즈 톤 + 비네트"
            entry["검수"] = "스톡 API(워터마크 없음) — 스팟체크"
        else:
            entry["title"] = r["title"]
        index[os.path.basename(r["path"])] = entry
    # 원자적 저장(쓰는 중 크래시로 인한 index.json 손상 방지)
    _tmp = INDEX + ".tmp"
    with open(_tmp, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(_tmp, INDEX)

    print(f"\n라이선스 기록: {INDEX}")
    print("안 쓸 사진은 파일과 index 항목을 같이 지우세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
