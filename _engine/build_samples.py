# -*- coding: utf-8 -*-
"""테스트 샘플 전용 빌더. output/samples/{MMDD}/{순번}/ 에만 쓰고
실제 발행 폴더(output/{MMDD}/)는 절대 건드리지 않는다.

사용법: python _engine/build_samples.py _engine/articles_samples_0802.json 0802
"""
import json
import os
import sys

from build_posts import build_one


def main():
    src = sys.argv[1]
    date_tag = sys.argv[2]

    with open(src, encoding="utf-8") as f:
        articles = json.load(f)

    report = []
    for i, article in enumerate(articles, start=1):
        out_dir = os.path.join("output", "samples", date_tag, str(i))
        body_len, n_img, problems = build_one(article, out_dir)
        report.append({
            "no": i, "title": article["title"], "dir": out_dir,
            "chars": body_len, "images": n_img, "problems": problems,
        })

    with open("samples_build_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"{len(articles)}건 생성 완료 -> output/samples/{date_tag}/  (상세: samples_build_report.json)")


if __name__ == "__main__":
    main()
