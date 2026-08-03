# -*- coding: utf-8 -*-
"""썸네일 카피 가독성 미리보기 — 짧은/중간/긴 카피를 한 번에 뽑아 눈으로 비교한다.

사용법:  python _engine/preview_thumbs.py         (레포 루트에서 실행)
결과:    output/preview_thumb/*.png
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common_utils import (build_stock_thumbnail_svg, build_thumbnail_svg,
                          convert_svg_to_png, layout_thumb_copy)

OUT = os.path.join("output", "preview_thumb")

CASES = [
    # (파일명, 1줄, 2줄, 강조단어, 사진)
    ("a_short", "하이닉스", "폭락 왔다", ["하이닉스"], "주식_0_0.jpg"),
    ("b_normal", "월급 500만원인데", "왜 계속 가난할까", ["500만원"], "생활물가_0_0.jpg"),
    ("c_mid", "수출 989억 신기록인데", "웃을 수가 없는 이유", ["989억"], "port_terminal.jpg"),
    ("d_long", "7월 수출 989억 달러 신기록인데",
     "체감 경기는 왜 이렇게 싸늘한가", ["989억"], "port_terminal.jpg"),
]


def pick(fname):
    """샘플 사진이 없으면 아무 사진이나 하나 골라 대체한다."""
    path = os.path.join("assets", "photos", fname)
    if os.path.exists(path):
        return path
    for f in sorted(os.listdir(os.path.join("assets", "photos"))):
        if f.lower().endswith((".jpg", ".png")):
            return os.path.join("assets", "photos", f)
    raise SystemExit("assets/photos 에 사진이 없습니다")


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, l1, l2, accent, photo in CASES:
        lines, fs = layout_thumb_copy(l1, l2)
        print(f"[{name}] fs={fs}  {len(lines)}줄  | " + " / ".join(lines))
        svg = build_thumbnail_svg(
            photo_path=pick(photo), line1=l1, line2=l2,
            brand="경제비버", tagline="THE ECONOMY BEAVER",
            accent_words=accent, dim=0.12)
        svg_path = os.path.join(OUT, name + ".svg")
        with open(svg_path, "w", encoding="utf-8") as f:
            f.write(svg)
        convert_svg_to_png(svg_path, os.path.join(OUT, name + ".png"))
        os.remove(svg_path)

    # 종목 썸네일도 같은 로직을 타는지 확인
    svg = build_stock_thumbnail_svg(
        line1="삼성전자 8만원", line2="다시 무너지나",
        price="79,800원", delta="3.2%", down=True,
        brand="경제비버", tagline="THE ECONOMY BEAVER",
        logo_path=os.path.join("assets", "tickers", "samsung_0.png"),
        accent_words=["8만원"])
    svg_path = os.path.join(OUT, "e_stock.svg")
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg)
    convert_svg_to_png(svg_path, os.path.join(OUT, "e_stock.png"))
    os.remove(svg_path)
    print("→", os.path.abspath(OUT))


if __name__ == "__main__":
    main()
