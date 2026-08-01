# -*- coding: utf-8 -*-
"""기사 JSON(들)을 받아 output/{MMDD}/{순번}/ 아래에 title.html + chart.png를 만든다.

사용법:
    python build_posts.py articles.json            # 오늘 날짜로 출력
    python build_posts.py articles.json 0801       # 날짜 직접 지정

articles.json 은 PROMPT_V1.md 12번 스키마를 따르는 객체의 배열이다.
에이전트는 JSON만 만들면 되고, 조립·변환은 전부 이 스크립트가 담당한다.
"""

import json
import os
import sys
from datetime import datetime

from common_utils import build_bar_chart_svg, build_page_html, convert_svg_to_png

SPACER = "⠀" * 3  # 점자 빈칸 3개 — 네이버 붙여넣기에서 살아남는 문단 간격


def build_one(article, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    image_map = {}

    chart = article.get("chart") or {}
    if chart.get("categories") and chart.get("values"):
        svg = build_bar_chart_svg(
            title=chart.get("title", ""),
            subtitle=chart.get("subtitle", ""),
            categories=chart["categories"],
            values=chart["values"],
            unit=chart.get("unit", ""),
            footnote=chart.get("footnote", ""),
        )
        svg_path = os.path.join(out_dir, "chart.svg")
        png_path = os.path.join(out_dir, "chart.png")
        with open(svg_path, "w", encoding="utf-8") as f:
            f.write(svg)
        if convert_svg_to_png(svg_path, png_path):
            image_map["1"] = "chart.png"
        else:
            print(f"  [경고] PNG 변환 실패: {out_dir}")

    # 본문 조립: 도입부 → 본문 → 에디터 코멘트 → 면책 → 해시태그
    paragraphs = [article["intro"], SPACER]
    paragraphs += article["body_paragraphs"]
    paragraphs += [SPACER, "[에디터 Comment]", article["editor_comment"]]
    if article.get("disclaimer"):
        paragraphs += [SPACER, article["disclaimer"]]
    paragraphs += [SPACER] + article.get("hashtags", [])

    html = build_page_html(article["title"], paragraphs, image_map)
    with open(os.path.join(out_dir, "title.html"), "w", encoding="utf-8") as f:
        f.write(html)

    # 붙여넣기용 순수 텍스트 (이미지 마커는 그대로 남겨둠)
    with open(os.path.join(out_dir, "body.txt"), "w", encoding="utf-8") as f:
        f.write(article["title"] + "\n" + SPACER + "\n" + "\n".join(paragraphs))

    with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(article, f, ensure_ascii=False, indent=2)

    body_len = len("".join(article["body_paragraphs"]).replace(" ", "").replace(SPACER, ""))
    return body_len


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "articles.json"
    date_tag = sys.argv[2] if len(sys.argv) > 2 else datetime.now().strftime("%m%d")

    with open(src, encoding="utf-8") as f:
        articles = json.load(f)
    if isinstance(articles, dict):
        articles = [articles]

    for i, article in enumerate(articles, start=1):
        out_dir = os.path.join("output", date_tag, str(i))
        body_len = build_one(article, out_dir)
        print(f"[{i}] {article['title']}")
        print(f"    -> {out_dir}  (본문 {body_len}자)")

    print(f"\n총 {len(articles)}개 생성 완료: output/{date_tag}/")


if __name__ == "__main__":
    main()
