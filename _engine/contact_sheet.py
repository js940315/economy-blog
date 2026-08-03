# -*- coding: utf-8 -*-
"""그날 만든 대표 썸네일을 한 장의 격자 이미지로 모은다 — '눈으로 하는 자기검수'용.

    python _engine/contact_sheet.py 0803        (저장소 루트에서)
    -> output/0803/_검수시트.jpg

왜 필요한가:
  photo_match.py 의 점수는 키워드 대조라 '명백한 미스매치'는 걸러도
  '반도체 사진이긴 한데 폭락 기사에 웃는 톤' 같은 건 못 잡는다. 그건 결국
  봐야 안다. 그런데 10건을 한 장씩 열어보면 이미지 10번을 읽어야 해서 비싸다.
  한 장에 모으면 '한 번만 보고' 전체를 판정할 수 있다 — 자동 루틴이 발행 전에
  스스로 검수하기에도, 사람이 최종 확인하기에도 가장 싼 방법.

번호는 output/{날짜}/{번호} 폴더 번호와 같으므로, 이상한 칸을 발견하면
그 번호의 기사만 고쳐서 다시 만들면 된다.
"""

import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

CELL = 420          # 썸네일 한 칸의 변 길이
LABEL_H = 62        # 칸 아래 제목 띠 높이
PAD = 14
COLS = 4
BG = (18, 22, 30)
FG = (238, 242, 248)
SUB = (150, 162, 180)


def _font(size):
    """한글이 깨지지 않게 윈도우/리눅스 공통으로 폰트를 찾는다."""
    candidates = [
        r"C:\Windows\Fonts\malgunbd.ttf", r"C:\Windows\Fonts\malgun.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _titles(date_tag):
    """build_report.json 에서 번호별 제목과 경고를 읽는다(없으면 빈 값)."""
    info = {}
    try:
        with open("build_report.json", encoding="utf-8") as f:
            for item in json.load(f):
                info[str(item.get("no"))] = (item.get("title", ""),
                                             item.get("problems", []))
    except (OSError, ValueError):
        pass
    return info


def build(date_tag):
    root = os.path.join("output", date_tag)
    if not os.path.isdir(root):
        print(f"{root} 가 없습니다.")
        return 1

    seqs = sorted((d for d in os.listdir(root) if d.isdigit()), key=int)
    cells = []
    for seq in seqs:
        thumb = os.path.join(root, seq, "1번 사진.jpg")
        if os.path.exists(thumb):
            cells.append((seq, thumb))
    if not cells:
        print(f"{root} 안에 '1번 사진.jpg' 가 없습니다.")
        return 1

    info = _titles(date_tag)
    cols = min(COLS, len(cells))
    rows = (len(cells) + cols - 1) // cols
    W = PAD + cols * (CELL + PAD)
    H = PAD + rows * (CELL + LABEL_H + PAD)

    sheet = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(sheet)
    f_no = _font(30)
    f_title = _font(19)
    f_warn = _font(17)

    for i, (seq, path) in enumerate(cells):
        cx = PAD + (i % cols) * (CELL + PAD)
        cy = PAD + (i // cols) * (CELL + LABEL_H + PAD)
        im = Image.open(path).convert("RGB").resize((CELL, CELL), Image.LANCZOS)
        sheet.paste(im, (cx, cy))

        title, problems = info.get(seq, ("", []))
        # 번호는 썸네일 위가 아니라 아래 라벨에 둔다 — 이미지 위에 얹으면
        # 하필 좌상단 기업 로고를 가려서 정작 검수할 것을 못 보게 된다.
        ty = cy + CELL + 6
        draw.text((cx + 2, ty), f"{seq}. " + (title[:24] or "(제목 없음)"),
                  font=f_title, fill=FG)
        # 온디맨드로 새로 받은 사진은 육안 검수를 한 번도 안 거쳤다.
        # 타사 로고·사람 얼굴이 박힌 사진이 올 수 있으므로 가장 눈에 띄게 표시한다.
        fresh = [p for p in problems if "온디맨드" in str(p)]
        if fresh:
            draw.rectangle([cx, cy, cx + CELL, cy + 34], fill=(200, 40, 60))
            draw.text((cx + 8, cy + 5), "NEW - 검수 필요", font=f_warn, fill=(255, 255, 255))

        # 매칭 경고가 있으면 빨갛게 — 이 칸부터 보라는 신호.
        # ※ 이모지(⚠)는 기본 폰트에 없어 두부(□)로 깨진다. ASCII 로만 쓴다.
        if problems:
            draw.text((cx + 2, ty + 26),
                      f"[!] {len(problems)}건: {str(problems[0])[:24]}",
                      font=f_warn, fill=(255, 120, 130))
        else:
            draw.text((cx + 2, ty + 26), "경고 없음", font=f_warn, fill=SUB)

    out = os.path.join(root, "_검수시트.jpg")
    sheet.save(out, "JPEG", quality=88)
    print(f"검수 시트 생성: {out}  ({len(cells)}건)")
    return 0


if __name__ == "__main__":
    tag = sys.argv[1] if len(sys.argv) > 1 else None
    if not tag:
        print("사용법: python _engine/contact_sheet.py {MMDD}")
        sys.exit(2)
    sys.exit(build(tag))
