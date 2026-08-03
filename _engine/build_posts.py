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
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from common_utils import (build_bar_card_svg, build_number_card_svg,
                          build_page_html, build_photo_card_svg,
                          build_rank_bar_card_svg, build_summary_card_svg,
                          build_stock_thumbnail_svg, build_thumbnail_svg,
                          convert_svg_to_png)
from photo_library import pick_photo, record_usage, variation_seed


def _asset(kind, name):
    return os.path.join("assets", kind, name) if name else None


def resolve_photo(spec, date_tag, seq, used_in_post):
    """spec["photo"](파일명 직접 지정) 또는 spec["photo_category"](카테고리
    지정 — 날짜·순번 기반 순환)을 실제 파일명으로 해석한다.

    photo_category를 쓰면 같은 카테고리를 하루이틀 연속으로 써도 자동으로
    다른 사진이 뽑힌다(photo_library.pick_photo). used_in_post는 같은
    포스트 안에서 이미 쓴 파일명 집합 — 썸네일과 실물이 같은 사진으로
    겹치는 걸 막는다."""
    if spec.get("photo"):
        return spec["photo"], None
    category = spec.get("photo_category")
    if not category:
        return None, None
    chosen = pick_photo(category, date_tag, seq, exclude=used_in_post)
    return chosen, category


def render_image(spec, date_tag=None, seq=None, used_in_post=None):
    """images 배열의 한 원소를 SVG 문자열로 만든다.

    type 값에 따라 4종 카드 중 하나를 고른다. 전부 같은 배경·서체를 쓰기 때문에
    한 포스팅 안에서 4장이 한 세트로 보인다."""
    used_in_post = used_in_post if used_in_post is not None else set()
    kind = spec.get("type", "bar_card")
    brand = spec.get("brand", "경제비버")
    tagline = spec.get("tagline", "THE ECONOMY BEAVER")
    if kind == "thumbnail":
        fname, category = resolve_photo(spec, date_tag, seq, used_in_post)
        if not fname:
            raise ValueError("thumbnail: photo 또는 photo_category 중 하나가 필요합니다")
        used_in_post.add(fname)
        if category:
            record_usage(category, fname, date_tag, seq)
        var = variation_seed(fname, date_tag, seq) if date_tag is not None else None
        return build_thumbnail_svg(
            photo_path=_asset("photos", fname),
            line1=spec["line1"], line2=spec["line2"],
            brand=brand, tagline=tagline,
            accent_words=spec.get("accent_words"), dim=spec.get("dim", 0.0),
            variation=var)
    if kind == "stock_thumbnail":
        return build_stock_thumbnail_svg(
            line1=spec["line1"], line2=spec["line2"],
            price=spec.get("price", ""), delta=spec.get("delta", ""),
            down=spec.get("down", True),
            brand=brand, tagline=tagline,
            logo_path=_asset("tickers", spec.get("logo")),
            accent_words=spec.get("accent_words"), series=spec.get("series"))
    if kind == "photo_card":
        fname, category = resolve_photo(spec, date_tag, seq, used_in_post)
        if not fname:
            raise ValueError("photo_card: photo 또는 photo_category 중 하나가 필요합니다")
        used_in_post.add(fname)
        if category:
            record_usage(category, fname, date_tag, seq)
        var = variation_seed(fname, date_tag, seq) if date_tag is not None else None
        return build_photo_card_svg(
            photo_path=_asset("photos", fname),
            eyebrow=spec["eyebrow"],
            headline_lines=spec.get("headline_lines", []),
            credit=spec.get("credit", ""),
            number=spec.get("number"), number_unit=spec.get("number_unit", ""),
            delta=spec.get("delta", ""), direction=spec.get("direction", "up"),
            logo_path=_asset("logos", spec.get("logo")),
            variation=var)
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
# 한 문단 목표 글자수. 네이버 모바일에서 대략 4줄 분량.
# 이 값을 넘으면 문장 경계에서 문단을 나눠 빈 줄을 넣는다.
# ※ 문장 중간에는 절대 줄바꿈(\n)을 넣지 않는다 — 네이버가 화면 폭에 맞춰
#   알아서 감싸기 때문에, 우리가 하드 줄바꿈을 박으면 어색한 데서 끊긴다.
MAX_PARA_CHARS = 110
EDITOR_HEADING = "📝 한눈에 보는 경제 노트"
DIVIDER = "━" * 19   # 소제목 밑 구분선. 모바일에서 딱 한 줄로 꽉 차는 길이

# 소제목·특수 이모지 문단은 flow_group으로 이어붙이지 않고 '독립 문단'으로 둔다.
#   📌 소제목  💡 핵심 포인트  👉 독자에게 질문(댓글 유도)  💬 관점 한 문장(공유 유도)
#   📝 경제 노트 헤딩  ⚠️ 주의  ✅ 체크
HEADING_PREFIXES = ("📌", "📝")
CALLOUT_PREFIXES = ("💡", "👉", "💬", "⚠️", "✅", "🔍")

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


def flow_group(sentences):
    """문장들을 이어 한 문단으로 만든다. 문장 중간엔 절대 줄바꿈하지 않는다.

    한 문단은 '한 줄'로 저장되고(문장들이 공백으로 이어짐), 네이버 에디터가
    화면 폭에 맞춰 알아서 감싼다. 문단이 모바일 약 4줄(MAX_PARA_CHARS)을 넘기려
    하면 그때만 직전 문장 경계에서 끊어 빈 줄을 넣는다.
    → '한 문장마다 엔터'도 아니고 '억지 줄바꿈'도 아니다. 문단만 나눈다."""
    out, buf, buf_len = [], [], 0
    for s in sentences:
        if buf and buf_len + len(s) > MAX_PARA_CHARS:
            out.append(" ".join(buf))   # 문단 확정 (한 줄, \n 없음)
            out.append(SPACER)
            buf, buf_len = [s], len(s)
        else:
            buf.append(s)
            buf_len += len(s) + 1
    if buf:
        out.append(" ".join(buf))
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
        elif item.startswith(HEADING_PREFIXES):
            # 소제목 → 밑에 구분선을 자동으로 깔아 시각적으로 확실히 구획
            flush()
            sep()
            out.append(item)
            out.append(DIVIDER)
            out.append(SPACER)
        elif item.startswith(CALLOUT_PREFIXES) or MARKER_RE.match(item):
            # 콜아웃(💡👉💬)·이미지 마커 → 이어붙이지 않고 독립 문단으로 띄운다
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


def place_images_evenly(body_lines, n_images, start=1):
    """본문 문단들 사이에 이미지 마커 N개를 '글자수 기준 균등'으로 끼워넣는다.

    이미지가 한곳에 몰리거나(스크롤 초반만 화려) 큰 빈 구간이 생기면(중반 이탈)
    안 되므로, 본문 텍스트 총량을 (N+1)등분해서 각 경계의 문단 사이에 마커를 둔다.
    body_paragraphs 안의 원래 마커는 무시하고 여기서 새로 배치한다.

    카드형 이미지는 '그 주제 전체'를 요약하므로 정확한 문맥 위치에 안 묶인다.
    대신 마지막 이미지(정리 카드)는 본문 맨 끝에 오도록 경계를 잡는다."""
    # 이미지 삽입 후보 = 문단과 문단 사이(=SPACER 위치). 소제목 바로 뒤는 피한다.
    para_lens, boundary_after = [], []   # boundary_after[i] = i번째 줄 뒤에 삽입 가능?
    total = 0
    for i, ln in enumerate(body_lines):
        is_text = ln not in (SPACER, DIVIDER) and not ln.startswith(
            ("#", "※", "📌", "📝") + CALLOUT_PREFIXES) and not MARKER_RE.match(ln)
        if is_text:
            total += len(ln)
        # 빈 줄(SPACER) 위치에서, 바로 앞이 소제목/구분선이 아니면 삽입 가능
        ok = (ln == SPACER and i > 0 and
              not body_lines[i-1].startswith(("📌", "📝")) and body_lines[i-1] != DIVIDER)
        boundary_after.append(ok)
        para_lens.append(len(ln) if is_text else 0)

    if total == 0 or n_images == 0:
        return body_lines

    targets = [total * (k + 1) / (n_images + 1) for k in range(n_images)]
    targets[-1] = total + 1   # 마지막 이미지는 본문 맨 끝으로 민다

    out, acc, ti = [], 0, 0
    for i, ln in enumerate(body_lines):
        out.append(ln)
        acc += para_lens[i]
        # 현재 누적이 다음 목표를 넘었고, 여기가 삽입 가능한 경계면 마커 삽입
        while ti < n_images and acc >= targets[ti] and boundary_after[i]:
            out.append(f"【{ti+start}번 사진】")
            out.append(SPACER)
            ti += 1
    # 남은 이미지(마지막 등)는 본문 맨 끝에 순서대로
    while ti < n_images:
        if out and out[-1] != SPACER:
            out.append(SPACER)
        out.append(f"【{ti+1}번 사진】")
        out.append(SPACER)
        ti += 1
    return out


def validate(lines):
    """규격 위반을 찾아 목록으로 돌려준다 (빈 목록 = 통과).

    이제 '줄 길이'는 보지 않는다 (네이버가 감싸므로). 문단이 목표치를 크게
    초과하는지(벽돌 위험)와 마크다운 잔존만 본다."""
    problems = []
    for line in lines:
        if line == SPACER or line == DIVIDER:
            continue
        if line.startswith(("#", "※") + HEADING_PREFIXES + CALLOUT_PREFIXES) or MARKER_RE.match(line):
            continue
        # 한 문장이 워낙 길어 문단 분리로도 못 줄인 경우만 경고 (여유 +50)
        if len(line) > MAX_PARA_CHARS + 50:
            problems.append(f"{len(line)}자 문단(너무 김): {line[:20]}...")
        if "**" in line or "`" in line:
            problems.append(f"마크다운 잔존: {line[:20]}...")
    return problems


REAL_PHOTO_IMAGE_TYPES = {"photo_card"}   # '실물 사진'으로 인정하는 카드 타입
THUMBNAIL_TYPES = {"thumbnail", "stock_thumbnail"}


def validate_image_structure(specs):
    """images 배열이 '썸네일1 + 실물1 + 카드N' 5장 스펙(v2/v3)을 지키는지 확인한다.

    사람이 기사 JSON을 쓸 때 실물 슬롯을 깜빡하고 데이터 카드로 채워도
    (썸네일1+카드4) 겉보기엔 5장이라 build 단계에서 조용히 넘어가곤 했다.
    여기서 강제로 잡아내 build_report.json의 problems에 남긴다."""
    problems = []
    if not specs:
        return problems
    if specs[0].get("type") not in THUMBNAIL_TYPES:
        problems.append(
            f"1번 이미지가 대표 썸네일이 아님(thumbnail/stock_thumbnail만 허용): "
            f"{specs[0].get('type')}")
    if len(specs) == 5:
        slot2 = specs[1].get("type")
        if slot2 not in REAL_PHOTO_IMAGE_TYPES:
            problems.append(
                f"5장 구성(썸네일1+실물1+카드3)인데 2번(실물) 슬롯이 photo_card가 "
                f"아니라 '{slot2}'임 — 실물 사진을 넣거나 4장 구성으로 바꿀 것")
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
    specs = article.get("images", [])

    # out_dir은 항상 ".../{date_tag}/{seq}" 형태(samples든 실제 발행이든)라
    # 여기서 순환picks 시드로 쓸 (date_tag, seq)를 그대로 뽑아낸다.
    parts = [p for p in out_dir.replace("\\", "/").split("/") if p]
    date_tag, seq = (parts[-2], parts[-1]) if len(parts) >= 2 else (parts[-1], "1")
    used_in_post = set()   # 한 포스트 안에서 사진이 겹치지 않게 추적

    from PIL import Image

    # SVG 작성 자체는 순수 CPU/문자열 작업이라 거의 공짜다. 시간을 잡아먹는 건
    # 이미지 1장마다 헤드리스 브라우저 프로세스를 새로 띄우는 convert_svg_to_png다.
    # 이미지끼리는 서로 완전히 독립적이므로, 그 부분만 스레드풀로 병렬 실행해
    # 벽시계 시간을 이미지 개수만큼 순차로 곱하지 않게 한다.
    #
    # ※ 동시 실행 브라우저 수 = 순간 메모리 사용량. 헤드리스 크로미움은 장당
    #   수백 MB를 쓰므로 8개를 한꺼번에 띄우면 순간 2~3GB가 튄다. 여유 RAM이
    #   적은(또는 RAM/디스크가 불안정한) 로컬에서 이 스파이크가 커널 크래시
    #   (MEMORY_MANAGEMENT 블루스크린)의 방아쇠가 될 수 있어, 기본을 낮게(3) 잡고
    #   환경변수 RENDER_CONCURRENCY로 조절한다. 안정적인 클라우드 러너는 8로 올려도 됨.
    tmp_paths = []
    for idx, spec in enumerate(specs, start=1):
        svg = render_image(spec, date_tag=date_tag, seq=seq, used_in_post=used_in_post)
        tmp_svg = os.path.join(out_dir, f"_tmp{idx}.svg")
        tmp_png = os.path.join(out_dir, f"_tmp{idx}.png")
        with open(tmp_svg, "w", encoding="utf-8") as f:
            f.write(svg)
        tmp_paths.append((idx, tmp_svg, tmp_png))

    if tmp_paths:
        try:
            workers = int(os.getenv("RENDER_CONCURRENCY", "3"))
        except ValueError:
            workers = 3
        workers = max(1, min(workers, len(tmp_paths)))
        with ThreadPoolExecutor(max_workers=workers) as ex:
            ok_flags = list(ex.map(
                lambda t: convert_svg_to_png(t[1], t[2]), tmp_paths))
    else:
        ok_flags = []

    for (idx, tmp_svg, tmp_png), ok in zip(tmp_paths, ok_flags):
        img_name = f"{idx}번 사진.jpg"
        img_path = os.path.join(out_dir, img_name)
        if ok:
            # 2160px 원본을 1080px JPG로 — 네이버엔 충분하고 용량은 1/20.
            # 저장소·다운로드가 가벼워져 매일 복붙 가성비가 올라간다.
            im = Image.open(tmp_png).convert("RGB")
            if im.size[0] > 1080:
                im = im.resize((1080, 1080), Image.LANCZOS)
            im.save(img_path, "JPEG", quality=92, subsampling=1)
            image_map[str(idx)] = img_name
        else:
            print(f"  [경고] 이미지 변환 실패: {img_path}")
        for tmp in (tmp_svg, tmp_png):     # 중간산물은 남기지 않는다
            if os.path.exists(tmp):
                os.remove(tmp)

    # 본문 조립: body_paragraphs 안의 원래 이미지 마커는 걷어내고,
    # place_images_evenly가 글자수 기준으로 균등하게 다시 배치한다.
    body_wo_markers = [p for p in article["body_paragraphs"]
                       if not MARKER_RE.match(strip_markdown(str(p)))]
    body_lines = to_blocks(body_wo_markers)
    n_img = len(article.get("images", []))
    # 2~N번 사진만 본문에 균등 배치(1번은 아래에서 '맨 위'로 뺀다).
    body_lines = place_images_evenly(body_lines, max(0, n_img - 1), start=2)

    lines = []
    # ★ 1번 사진(대표 썸네일)을 제목 바로 밑·도입부 위에 둔다 — 모바일로 들어오자마자
    #   보이게 해 초반 이탈을 막고, 홈판 대표 썸네일로도 확실히 잡히게 한다.
    if n_img >= 1:
        lines += ["【1번 사진】", SPACER]
    lines += to_blocks(article["intro"])
    lines += [SPACER] + body_lines
    lines += [SPACER, EDITOR_HEADING, SPACER] + to_blocks(article["editor_comment"])
    # 여운형 질문 — 정리(경제 노트) 다음, 면책 앞. 글의 진짜 마지막 말이라
    # 독자가 자기 상황을 떠올리며 자연스럽게 반응하게 된다. ('댓글' 요청 아님)
    if article.get("closing_question"):
        lines += [SPACER] + to_blocks(article["closing_question"])
    if article.get("disclaimer"):
        lines += [SPACER] + to_blocks(article["disclaimer"])
    lines += [SPACER] + [strip_markdown(h) for h in article.get("hashtags", [])]

    problems = validate(lines)
    problems += validate_image_structure(specs)

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
