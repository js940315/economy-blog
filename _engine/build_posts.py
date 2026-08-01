# -*- coding: utf-8 -*-
"""기사 JSON(들)을 받아 output/{MMDD}/{순번}/ 아래에 붙여넣기용 결과물을 만든다.

사용법:
    python build_posts.py articles.json            # 오늘 날짜로 출력
    python build_posts.py articles.json 0801       # 날짜 직접 지정

에이전트는 JSON만 만들면 되고, 아래 3가지는 이 스크립트가 강제로 보정한다:
  1) 마크다운 기호(**, ##, `) 제거  — 네이버에 그대로 노출되면 AI 티가 나므로
  2) 벽돌 문단 자동 분해          — 긴 줄글을 3줄 단위로 쪼개고 사이에 빈 줄 삽입
  3) 45자 넘는 문장 자동 줄바꿈    — 모바일 가독성 최우선

즉 글이 다소 길게 뭉쳐 나와도 최종 결과물은 항상 모바일 규격을 만족한다.
"""

import json
import os
import re
import sys
from datetime import datetime

from common_utils import (build_bar_card_svg, build_number_card_svg,
                          build_page_html, build_photo_card_svg,
                          build_rank_bar_card_svg, build_summary_card_svg,
                          build_stock_thumbnail_svg, build_thumbnail_svg,
                          convert_svg_to_png)


def _asset(kind, name):
    return os.path.join("assets", kind, name) if name else None


def render_image(spec):
    """images 배열의 한 원소를 SVG 문자열로 만든다.

    type 값에 따라 4종 카드 중 하나를 고른다. 전부 같은 배경·서체를 쓰기 때문에
    한 포스팅 안에서 4장이 한 세트로 보인다."""
    kind = spec.get("type", "bar_card")
    brand = spec.get("brand", "경제비버")
    tagline = spec.get("tagline", "THE ECONOMY BEAVER")
    if kind == "thumbnail":
        return build_thumbnail_svg(
            photo_path=_asset("photos", spec["photo"]),
            line1=spec["line1"], line2=spec["line2"],
            brand=brand, tagline=tagline,
            accent_words=spec.get("accent_words"), dim=spec.get("dim", 0.0))
    if kind == "stock_thumbnail":
        return build_stock_thumbnail_svg(
            line1=spec["line1"], line2=spec["line2"],
            price=spec.get("price", ""), delta=spec.get("delta", ""),
            down=spec.get("down", True),
            brand=brand, tagline=tagline,
            logo_path=_asset("tickers", spec.get("logo")),
            accent_words=spec.get("accent_words"), series=spec.get("series"))
    if kind == "photo_card":
        return build_photo_card_svg(
            photo_path=_asset("photos", spec["photo"]),
            eyebrow=spec["eyebrow"],
            headline_lines=spec.get("headline_lines", []),
            credit=spec.get("credit", ""),
            number=spec.get("number"), number_unit=spec.get("number_unit", ""),
            delta=spec.get("delta", ""), direction=spec.get("direction", "up"),
            logo_path=_asset("logos", spec.get("logo")))
    if kind == "number_card":
        return build_number_card_svg(
            eyebrow=spec["eyebrow"], number=spec["number"],
            number_unit=spec.get("number_unit", ""),
            headline_lines=spec.get("headline_lines", []),
            delta=spec.get("delta", ""), direction=spec.get("direction", "up"),
            footnote=spec.get("note", ""),
            # logo는 assets/logos/ 안의 파일명. 기사가 실제로 그 기업을 다룰 때만 넣는다.
            logo_path=_asset("logos", spec.get("logo")))
    if kind == "rank_card":
        return build_rank_bar_card_svg(
            eyebrow=spec["eyebrow"], title_lines=spec.get("title_lines", []),
            items=[tuple(i) for i in spec["items"]], note=spec.get("note", ""))
    if kind == "summary_card":
        return build_summary_card_svg(
            eyebrow=spec["eyebrow"], title_lines=spec.get("title_lines", []),
            points=spec["points"], note=spec.get("note", ""))
    return build_bar_card_svg(
        eyebrow=spec["eyebrow"], title_lines=spec.get("title_lines", []),
        categories=spec["categories"], values=spec["values"],
        displays=spec.get("displays"), note=spec.get("note", ""),
        highlight=spec.get("highlight"))

SPACER = "⠀" * 3   # 점자 빈칸 — 네이버 붙여넣기에서 살아남는 문단 간격
MAX_CHARS = 45      # 한 줄 최대 글자수
MAX_LINES = 5       # 문단이 이 줄수를 넘기면 빈 줄로 끊는다 (벽돌 문단 방지)
EDITOR_HEADING = "📝 한눈에 보는 경제 노트"

MARKER_RE = re.compile(r"^【\s*\d+\s*번\s*(?:이미지|사진)\s*】$")
SENT_RE = re.compile(r"(?<=[.!?])\s+|(?<=다\.)\s*|(?<=요\.)\s*|(?<=죠\.)\s*")


def strip_markdown(text):
    """네이버에 그대로 노출되면 안 되는 마크다운 기호를 제거한다."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)   # **볼드**
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = text.replace("**", "").replace("`", "")
    text = re.sub(r"^#{1,6}\s+", "", text)          # 머리말 기호 (해시태그 #키워드 는 보존)
    text = re.sub(r"^[-*]\s+", "", text)            # 목록 기호
    return text.strip()


def wrap_text(text):
    """여러 문장이 이어진 텍스트를 45자 단위로 자연스럽게 줄바꿈한다 (단어 경계).

    문장마다 끊지 않고 이어 흐르게 하므로, 둘째 줄에 '요.' 같은 짧은 꼬리가
    남지 않는다. 다음 문장이 이어 붙어 줄을 자연스럽게 채운다."""
    words = text.split(" ")
    lines, cur = [], ""
    for w in words:
        cand = f"{cur} {w}".strip()
        if cur and len(cand) > MAX_CHARS:
            lines.append(cur)
            cur = w
        else:
            cur = cand
    if cur:
        lines.append(cur)
    return lines


def flow_group(sentences):
    """한 문단(문장 리스트)을 이어서 흐르게 워드랩한다.

    문장마다 줄바꿈하지 않고 계속 이어 쓰되, 누적 줄이 MAX_LINES(5)를 넘기려 하면
    직전 문장 경계에서 빈 줄을 넣어 벽돌 문단을 막는다.
    → '한 문장 후 무조건 엔터'가 아니라 '길어지면 그때만 한 줄 여백'."""
    out, buf = [], []
    for s in sentences:
        trial = wrap_text(" ".join(buf + [s]))
        if buf and len(trial) > MAX_LINES:
            out += wrap_text(" ".join(buf))
            out.append(SPACER)
            buf = [s]
        else:
            buf.append(s)
    if buf:
        out += wrap_text(" ".join(buf))
    return out


def to_blocks(value):
    """문자열/리스트를 '문단 흐름 + 문단 사이 빈 줄' 형태로 정규화한다.

    문단(빈 줄·소제목·마커로 구분) 안에서는 문장을 이어 흐르게 한다.
    입력이 문장 배열이든 한 덩어리 문자열이든 결과는 동일하게 자연스럽다."""
    if isinstance(value, list):
        items = [strip_markdown(str(x)) for x in value]
    else:
        text = strip_markdown(str(value))
        items = [s.strip() for s in SENT_RE.split(text) if s and s.strip()]

    out, group = [], []

    def flush():
        if group:
            out.extend(flow_group(group))
            group.clear()

    def sep():
        if out and out[-1] != SPACER:
            out.append(SPACER)

    for item in items:
        if not item or item == SPACER:
            flush()
            sep()
        elif MARKER_RE.match(item) or item.startswith(("📌", "📝")):
            flush()
            sep()
            out.append(item)
            out.append(SPACER)
        else:
            group.append(item)
    flush()
    while out and out[-1] == SPACER:
        out.pop()
    while out and out[0] == SPACER:
        out.pop(0)
    return out


def validate(lines):
    """규격 위반을 찾아 목록으로 돌려준다 (빈 목록 = 통과)."""
    problems, run = [], 0
    for line in lines:
        if line == SPACER:
            run = 0
            continue
        if line.startswith("#"):      # 해시태그 묶음은 문단 규칙 대상이 아니다
            continue
        run += 1
        if run > MAX_LINES:
            problems.append(f"{MAX_LINES}줄 초과 문단: {line[:20]}...")
        if len(line) > MAX_CHARS:
            problems.append(f"{len(line)}자 문장: {line[:20]}...")
        if "**" in line or "`" in line:
            problems.append(f"마크다운 잔존: {line[:20]}...")
    return problems


def build_one(article, out_dir):
    """붙여넣기 폴더에는 사람이 실제로 쓰는 것만 남긴다.

    남기는 것: 본문.txt / 1번 사진.png ~ N번 사진.png
    안 만드는 것: svg(png 변환용 중간산물), meta.json/title.html(디버깅·미리보기용)
       → GitHub 폴더에서 헷갈리지 않도록 아예 생성하지 않는다.
       재생성이 필요하면 articles.json 으로 언제든 다시 만들 수 있다.
    """
    os.makedirs(out_dir, exist_ok=True)
    image_map = {}

    for idx, spec in enumerate(article.get("images", []), start=1):
        svg = render_image(spec)
        tmp_svg = os.path.join(out_dir, f"_tmp{idx}.svg")
        png_name = f"{idx}번 사진.png"
        png_path = os.path.join(out_dir, png_name)
        with open(tmp_svg, "w", encoding="utf-8") as f:
            f.write(svg)
        if convert_svg_to_png(tmp_svg, png_path):
            image_map[str(idx)] = png_name
        else:
            print(f"  [경고] PNG 변환 실패: {png_path}")
        if os.path.exists(tmp_svg):       # 중간산물 svg는 남기지 않는다
            os.remove(tmp_svg)

    lines = []
    lines += to_blocks(article["intro"])
    lines += [SPACER] + to_blocks(article["body_paragraphs"])
    lines += [SPACER, EDITOR_HEADING, SPACER] + to_blocks(article["editor_comment"])
    if article.get("disclaimer"):
        lines += [SPACER] + to_blocks(article["disclaimer"])
    lines += [SPACER] + [strip_markdown(h) for h in article.get("hashtags", [])]

    problems = validate(lines)

    # 파일명 앞 '0번'은 정렬용 — 사진(1~4번)보다 위에 오게 해서 작업 순서(본문 먼저)와 일치
    with open(os.path.join(out_dir, "0번 본문.txt"), "w", encoding="utf-8") as f:
        f.write(article["title"] + "\n" + SPACER + "\n" + "\n".join(lines))

    body_only = to_blocks(article["body_paragraphs"])
    body_len = len("".join(l for l in body_only if l != SPACER).replace(" ", ""))
    return body_len, len(image_map), problems


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "articles.json"
    date_tag = sys.argv[2] if len(sys.argv) > 2 else datetime.now().strftime("%m%d")

    with open(src, encoding="utf-8") as f:
        articles = json.load(f)
    if isinstance(articles, dict):
        articles = [articles]

    report = []
    for i, article in enumerate(articles, start=1):
        out_dir = os.path.join("output", date_tag, str(i))
        body_len, n_img, problems = build_one(article, out_dir)
        report.append({
            "no": i, "title": article["title"], "dir": out_dir,
            "chars": body_len, "images": n_img, "problems": problems,
        })

    with open("build_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"{len(articles)}건 생성 완료 -> output/{date_tag}/  (상세: build_report.json)")


if __name__ == "__main__":
    main()
