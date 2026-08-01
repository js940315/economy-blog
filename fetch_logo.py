# -*- coding: utf-8 -*-
"""기업 로고를 Wikimedia Commons에서 받아 assets/logos/ 에 쌓아두는 도구.

    python fetch_logo.py "Samsung Electronics"
    python fetch_logo.py "SK Hynix" --name skhynix

받은 뒤에는 반드시 눈으로 확인한다. Commons 검색은 자회사·제품 로고
(예: Galaxy A8, SK magic)를 섞어서 주기 때문에 자동 채택하면 엉뚱한 게 박힌다.

라이선스 주의:
  - Public domain(단순 문자 로고 다수) : 표기 없이 사용 가능
  - CC BY / CC BY-SA : 출처·저작자 표기 필요 -> 카드 하단 note에 적는다
  - 로고는 저작권과 별개로 '상표'다. 해당 기업을 실제로 다루는 기사에만 쓰고,
    그 기업이 우리 블로그를 후원/보증하는 것처럼 보이게 쓰지 않는다.
"""

import argparse
import json
import os
import re
import sys

from image_sourcing import logo_candidates

LOGO_DIR = os.path.join("assets", "logos")
INDEX = os.path.join(LOGO_DIR, "index.json")


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("company", help='예: "Samsung Electronics"')
    ap.add_argument("--name", help="저장 이름 (기본: 회사명 슬러그)")
    ap.add_argument("--limit", type=int, default=5)
    args = ap.parse_args()

    prefix = args.name or slugify(args.company)
    os.makedirs(LOGO_DIR, exist_ok=True)

    report = logo_candidates(f"{args.company} logo", LOGO_DIR,
                             width=1200, limit=args.limit, prefix=prefix)

    ok = [r for r in report if "error" not in r]
    if not ok:
        print("후보를 하나도 못 받았습니다. 검색어를 더 구체적으로 바꿔보세요.")
        for r in report:
            print("  실패:", r.get("title"), r.get("error", "")[:60])
        return 1

    print(f"\n{len(ok)}개 후보를 {LOGO_DIR}/ 에 저장했습니다. 눈으로 확인 후 고르세요.\n")
    for r in ok:
        print(f"  {os.path.basename(r['path']):<24} {r['w']}x{r['h']:<6} "
              f"[{r['license']}]  {r['title']}")

    index = {}
    if os.path.exists(INDEX):
        with open(INDEX, encoding="utf-8") as f:
            index = json.load(f)
    index[args.company] = [
        {"file": os.path.basename(r["path"]), "license": r["license"], "title": r["title"]}
        for r in ok
    ]
    with open(INDEX, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    print(f"\n라이선스 기록: {INDEX}")
    print("CC BY / CC BY-SA 인 파일을 쓸 경우 카드 note에 출처를 남기세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
