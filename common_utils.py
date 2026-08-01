# -*- coding: utf-8 -*-
"""차트 SVG 생성 + PNG 변환 유틸리티. 로컬(Windows)과 클라우드(Linux) 양쪽에서 동작하도록
브라우저 바이너리를 여러 방식으로 찾는다."""

import os
import re
import shutil
import subprocess

WINDOWS_BROWSER_PATHS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]

LINUX_BROWSER_NAMES = [
    "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
    "microsoft-edge", "microsoft-edge-stable",
]


def find_browser():
    for path in WINDOWS_BROWSER_PATHS:
        if os.path.exists(path):
            return path
    for name in LINUX_BROWSER_NAMES:
        found = shutil.which(name)
        if found:
            return found
    return None


def convert_svg_to_png(svg_path, png_path):
    """헤드리스 브라우저로 SVG를 스크린샷 떠서 PNG로 바꾼다.
    (네이버는 SVG 업로드를 거부하므로 항상 PNG로 변환해서 써야 한다)
    브라우저를 못 찾으면 False를 반환한다 — 호출부에서 apt-get/pip 등으로
    설치를 시도하거나, 실패를 기록하고 다음 이미지로 넘어가야 한다."""
    browser = find_browser()
    if not browser:
        print("  [경고] 헤드리스 브라우저를 못 찾아서 SVG->PNG 변환을 건너뜁니다.")
        return False

    with open(svg_path, "r", encoding="utf-8") as f:
        svg_content = f.read()
    m = re.search(r'viewBox="[\d.\-]+\s+[\d.\-]+\s+([\d.]+)\s+([\d.]+)"', svg_content)
    if m:
        w, h = float(m.group(1)), float(m.group(2))
    else:
        w, h = 640, 380
    window_size = f"{int(w)},{int(h)}"

    file_url = "file:///" + os.path.abspath(svg_path).replace("\\", "/")
    cmd = [
        browser,
        "--headless",
        "--disable-gpu",
        "--no-sandbox",  # 클라우드 컨테이너에서 root로 돌 때 필요
        f"--screenshot={os.path.abspath(png_path)}",
        f"--window-size={window_size}",
        "--force-device-scale-factor=2",
        "--default-background-color=FFFFFFFF",
        file_url,
    ]
    try:
        subprocess.run(cmd, timeout=30, capture_output=True, check=True)
        return os.path.exists(png_path)
    except Exception as e:
        print(f"  [경고] SVG->PNG 변환 실패: {e}")
        return False


def escape_html(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---- 숫자 강조 카드 (네이버 경제 블로그 썸네일 스타일) ----
CARD_W, CARD_H = 1080, 1080
CARD_BG_TOP = "#0f1f3d"
CARD_BG_BOT = "#0a1428"
CARD_ACCENT_UP = "#ff4d4f"      # 상승 = 빨강 (국내 증시 관행)
CARD_ACCENT_DOWN = "#2f80ed"    # 하락 = 파랑
CARD_GOLD = "#ffc83d"


def build_number_card_svg(eyebrow, number, number_unit, headline_lines,
                          delta="", direction="up", footnote="", logo_path=None):
    """큰 숫자 하나를 주인공으로 세운 정사각 카드.

    eyebrow        : 상단 작은 라벨 (예: 2026년 7월 수출)
    number         : 주인공 숫자 문자열 (예: 988.9)
    number_unit    : 숫자 뒤 단위 (예: 억 달러)
    headline_lines : 하단 카피, 줄 단위 리스트 (2줄 권장)
    delta          : 증감 표기 (예: 전년 대비 +62.8%)
    direction      : up = 빨강, down = 파랑
    """
    accent = CARD_ACCENT_UP if direction == "up" else CARD_ACCENT_DOWN
    arrow = "▲" if direction == "up" else "▼"
    # 나머지 3종 카드와 같은 배경을 써야 한 세트로 보인다
    p = [_card_open(accent)]
    # 기업 로고 (있을 때만) — 우상단, "무슨 회사 얘기인지" 0.1초 안에 인식시킨다
    p.append(logo_tag(logo_path, CARD_W - 88 - 300, 150, 300, 90))
    # 좌측 강조 바
    p.append(f'<rect x="88" y="196" width="8" height="86" rx="4" fill="{accent}"/>')
    p.append(
        f'<text x="122" y="248" font-size="40" fill="#a9b6cc" '
        f'letter-spacing="1">{escape_html(eyebrow)}</text>'
    )
    # 주인공 숫자
    p.append(
        f'<text x="88" y="470" font-size="200" font-weight="800" fill="#ffffff" '
        f'letter-spacing="-4">{escape_html(number)}'
        f'<tspan font-size="76" font-weight="700" fill="#d5dded" dx="18">'
        f'{escape_html(number_unit)}</tspan></text>'
    )
    if delta:
        p.append(
            f'<text x="92" y="556" font-size="52" font-weight="700" fill="{accent}">'
            f'{arrow} {escape_html(delta)}</text>'
        )
    # 구분선
    p.append(f'<rect x="88" y="630" width="904" height="2" fill="#ffffff" opacity="0.14"/>')
    # 하단 카피
    y = 740
    for line in headline_lines:
        p.append(
            f'<text x="88" y="{y}" font-size="66" font-weight="700" fill="#ffffff" '
            f'letter-spacing="-1">{escape_html(line)}</text>'
        )
        y += 92
    p.append(_card_note(footnote))
    p.append("</svg>")
    return "\n".join(p)


def png_data_uri(path):
    """PNG를 base64 data URI로 만든다.

    SVG 안에 <image href="data:...">로 박아야 헤드리스 브라우저가 한 번에 렌더한다.
    외부 파일 경로로 걸어두면 스크린샷 시점에 로드가 안 될 수 있다."""
    import base64
    with open(path, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()


def logo_tag(logo_path, x, y, box_w, box_h):
    """카드 우상단 등에 로고를 넣는다. 원본 비율을 유지하며 박스 안에 맞춘다.

    ※ 로고는 상표다. 기사가 실제로 그 기업을 다룰 때만 쓴다.
      관련 없는 기사에 로고를 붙이면 그 기업 얘기인 것처럼 오인시키게 된다."""
    if not logo_path or not os.path.exists(logo_path):
        return ""
    uri = png_data_uri(logo_path)
    # 기업 로고는 대부분 어두운 원색이라 어두운 배경에 그냥 얹으면 묻힌다.
    # 흰 라운드 판을 깔아서 실제 인쇄물처럼 보이게 한다.
    pad = 22
    plate = (f'<rect x="{x-pad}" y="{y-pad}" width="{box_w+pad*2}" height="{box_h+pad*2}" '
             f'rx="18" fill="#ffffff" opacity="0.94"/>')
    return plate + (f'<image href="{uri}" x="{x}" y="{y}" width="{box_w}" height="{box_h}" '
                    f'preserveAspectRatio="xMidYMid meet"/>')


def _card_open(accent):
    """4종 카드가 공유하는 배경·그라데이션. 시리즈 통일감의 핵심."""
    return (
        f'<svg viewBox="0 0 {CARD_W} {CARD_H}" xmlns="http://www.w3.org/2000/svg" '
        f'font-family="Pretendard, \'Malgun Gothic\', system-ui, sans-serif">'
        '<defs>'
        f'<linearGradient id="bg" x1="0" y1="0" x2="0.4" y2="1">'
        f'<stop offset="0%" stop-color="{CARD_BG_TOP}"/>'
        f'<stop offset="100%" stop-color="{CARD_BG_BOT}"/></linearGradient>'
        f'<radialGradient id="glow" cx="0.5" cy="0.5" r="0.5">'
        f'<stop offset="0%" stop-color="{accent}" stop-opacity="0.16"/>'
        f'<stop offset="100%" stop-color="{accent}" stop-opacity="0"/></radialGradient>'
        '</defs>'
        f'<rect width="{CARD_W}" height="{CARD_H}" fill="url(#bg)"/>'
        f'<circle cx="{CARD_W-40}" cy="-40" r="620" fill="url(#glow)"/>'
    )


def _card_head(eyebrow, title_lines, accent):
    """상단 라벨 + 제목. 모든 카드가 같은 위치·크기를 쓴다."""
    p = [f'<rect x="88" y="96" width="8" height="72" rx="4" fill="{accent}"/>',
         f'<text x="122" y="146" font-size="38" fill="#a9b6cc">{escape_html(eyebrow)}</text>']
    y = 268
    for line in title_lines:
        p.append(
            f'<text x="88" y="{y}" font-size="64" font-weight="800" fill="#ffffff" '
            f'letter-spacing="-1">{escape_html(line)}</text>'
        )
        y += 84
    return "".join(p), y


def _card_note(note):
    """하단 출처. 길면 폰트를 줄여 카드 밖으로 넘치지 않게 한다."""
    if not note:
        return ""
    size = 32 if len(note) <= 34 else (27 if len(note) <= 46 else 23)
    return (f'<text x="88" y="{CARD_H-64}" font-size="{size}" fill="#7f8da3">'
            f'{escape_html(note)}</text>')


def build_rank_bar_card_svg(eyebrow, title_lines, items, note="", accent=CARD_ACCENT_UP):
    """가로 순위 막대 카드. items = [(라벨, 수치값, 표시문자열), ...]

    독자가 '내 업종·내 지역은 어디쯤인가'를 3초 안에 찾게 만드는 포맷.
    1위만 강조색을 주고 나머지는 눌러서 시선 순서를 통제한다."""
    p = [_card_open(accent)]
    head, y = _card_head(eyebrow, title_lines, accent)
    p.append(head)

    y += 40
    max_val = max(abs(v) for _, v, _ in items) or 1
    bar_x, bar_max_w = 88, 700
    # 남은 세로 공간에 행을 균등 배치해 아래쪽이 비지 않게 한다
    row_h = max(96, min(132, (CARD_H - 150 - y) // max(1, len(items))))
    for i, (label, value, display) in enumerate(items):
        # 값이 작아도 막대가 점으로 보이지 않도록 최소 길이를 준다
        w = max(56, abs(value) / max_val * bar_max_w)
        color = accent if i == 0 else "#ffffff"
        opacity = "1" if i == 0 else "0.22"
        p.append(
            f'<text x="88" y="{y}" font-size="38" font-weight="600" fill="#d5dded">'
            f'{escape_html(label)}</text>'
        )
        p.append(
            f'<rect x="{bar_x}" y="{y+18}" width="{w:.0f}" height="30" rx="15" '
            f'fill="{color}" opacity="{opacity}"/>'
        )
        val_color = accent if i == 0 else "#ffffff"
        p.append(
            f'<text x="{CARD_W-88}" y="{y+2}" font-size="46" font-weight="800" '
            f'fill="{val_color}" text-anchor="end">{escape_html(display)}</text>'
        )
        y += row_h

    p.append(_card_note(note))
    p.append("</svg>")
    return "".join(p)


def build_summary_card_svg(eyebrow, title_lines, points, note="", accent=CARD_GOLD):
    """마무리 정리 카드. points = ["한 줄", "한 줄", "한 줄"]

    '저장해두고 싶은' 카드를 만들어 스크랩을 유도한다.
    스크랩·공유는 체류시간만큼이나 노출에 영향을 준다."""
    p = [_card_open(accent)]
    head, y = _card_head(eyebrow, title_lines, accent)
    p.append(head)

    y += 56
    for i, point in enumerate(points, start=1):
        lines = point if isinstance(point, list) else [point]
        p.append(f'<circle cx="118" cy="{y-14}" r="30" fill="{accent}" opacity="0.18"/>')
        p.append(
            f'<text x="118" y="{y}" font-size="34" font-weight="800" fill="{accent}" '
            f'text-anchor="middle">{i}</text>'
        )
        ty = y + 2
        for line in lines:
            p.append(
                f'<text x="172" y="{ty}" font-size="44" font-weight="600" fill="#ffffff">'
                f'{escape_html(line)}</text>'
            )
            ty += 58
        y = ty + 54

    p.append(_card_note(note))
    p.append("</svg>")
    return "".join(p)


def build_bar_card_svg(eyebrow, title_lines, categories, values, displays=None,
                       note="", accent=CARD_ACCENT_UP, highlight=None):
    """세로 막대 카드 (다크 톤). 나머지 3종과 같은 배경·서체를 쓴다."""
    p = [_card_open(accent)]
    head, y = _card_head(eyebrow, title_lines, accent)
    p.append(head)

    displays = displays or [f"{v:,.0f}" for v in values]
    top, bottom = y + 70, CARD_H - 190
    plot_h = bottom - top
    max_val = max(values) or 1
    n = len(categories)
    slot = (CARD_W - 176) / n
    bar_w = slot * 0.56

    p.append(f'<line x1="88" y1="{bottom}" x2="{CARD_W-88}" y2="{bottom}" '
             f'stroke="#ffffff" stroke-opacity="0.18" stroke-width="2"/>')

    for i, (cat, val, disp) in enumerate(zip(categories, values, displays)):
        h = max(10, val / max_val * plot_h)
        x = 88 + i * slot + (slot - bar_w) / 2
        # highlight를 주면 그 항목을, 안 주면 최댓값을 강조한다.
        # 이야기의 주인공과 최댓값이 다를 때가 많아 지정할 수 있게 열어둔다.
        is_hero = (i == highlight) if highlight is not None else (val == max_val)
        color = accent if is_hero else "#ffffff"
        opacity = "1" if is_hero else "0.26"
        p.append(
            f'<rect x="{x:.0f}" y="{bottom-h:.0f}" width="{bar_w:.0f}" height="{h:.0f}" '
            f'rx="10" fill="{color}" opacity="{opacity}"/>'
        )
        p.append(
            f'<text x="{x+bar_w/2:.0f}" y="{bottom-h-28:.0f}" font-size="44" '
            f'font-weight="800" fill="#ffffff" text-anchor="middle">{escape_html(disp)}</text>'
        )
        p.append(
            f'<text x="{x+bar_w/2:.0f}" y="{bottom+56}" font-size="36" fill="#a9b6cc" '
            f'text-anchor="middle">{escape_html(str(cat))}</text>'
        )

    p.append(_card_note(note))
    p.append("</svg>")
    return "".join(p)


# ---- 팔레트: dataviz 스킬에서 검증된 단일 계열 blue ----
CHART_BLUE = "#2a78d6"
CHART_SURFACE = "#fcfcfb"
CHART_PRIMARY_INK = "#0b0b0b"
CHART_SECONDARY_INK = "#52514e"
CHART_MUTED = "#898781"
CHART_GRID = "#e1e0d9"
CHART_AXIS = "#c3c2b7"


def build_bar_chart_svg(title, subtitle, categories, values, unit="", footnote=""):
    """categories/values 로부터 단일 계열 막대그래프 SVG를 동적으로 만든다."""
    n = len(categories)
    assert n == len(values) and n >= 1

    W, H = 640, 380
    left, right = 70, 40
    top, bottom = 60, 80
    plot_top, plot_bottom = 110, H - bottom

    max_val = max(values) if values else 1
    import math
    magnitude = 10 ** (len(str(int(max_val))) - 1)
    nice_max = math.ceil(max_val / magnitude) * magnitude
    if nice_max <= max_val:
        nice_max += magnitude

    plot_h = plot_bottom - plot_top
    bar_gap_ratio = 0.35
    bar_w = (W - left - right) / n * (1 - bar_gap_ratio)
    slot_w = (W - left - right) / n

    def y_for(v):
        return plot_bottom - (v / nice_max) * plot_h

    parts = []
    parts.append(
        f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
        f'font-family="system-ui, -apple-system, \'Segoe UI\', sans-serif">'
    )
    parts.append(f'<rect x="0" y="0" width="{W}" height="{H}" fill="{CHART_SURFACE}"/>')
    parts.append(
        f'<text x="32" y="30" font-size="19" font-weight="700" '
        f'fill="{CHART_PRIMARY_INK}">{escape_html(title)}</text>'
    )
    parts.append(
        f'<text x="32" y="50" font-size="13" fill="{CHART_SECONDARY_INK}">'
        f'{escape_html(subtitle)}</text>'
    )

    for i in range(4):
        val = nice_max * i / 3
        y = y_for(val)
        stroke = CHART_AXIS if i == 0 else CHART_GRID
        sw = 2 if i == 0 else 1
        parts.append(f'<line x1="{left-38}" y1="{y}" x2="{W-right}" y2="{y}" stroke="{stroke}" stroke-width="{sw}"/>')
        label = f"{int(val):,}" + (f"({unit})" if i == 3 and unit else "")
        parts.append(
            f'<text x="{left-45}" y="{y+4}" font-size="11" fill="{CHART_MUTED}" '
            f'text-anchor="end">{escape_html(label)}</text>'
        )

    baseline = y_for(0)
    for i, (cat, val) in enumerate(zip(categories, values)):
        slot_x = left + i * slot_w
        bar_x = slot_x + (slot_w - bar_w) / 2
        bar_top = y_for(val)
        r = 4
        path = (
            f"M{bar_x},{baseline} L{bar_x},{bar_top+r} "
            f"Q{bar_x},{bar_top} {bar_x+r},{bar_top} "
            f"L{bar_x+bar_w-r},{bar_top} Q{bar_x+bar_w},{bar_top} {bar_x+bar_w},{bar_top+r} "
            f"L{bar_x+bar_w},{baseline} Z"
        )
        parts.append(f'<path d="{path}" fill="{CHART_BLUE}"/>')
        label_val = f"{val:,.0f}{unit}" if isinstance(val, (int, float)) else f"{val}{unit}"
        parts.append(
            f'<text x="{bar_x+bar_w/2}" y="{bar_top-10}" font-size="13" font-weight="700" '
            f'fill="{CHART_PRIMARY_INK}" text-anchor="middle">{escape_html(label_val)}</text>'
        )
        parts.append(
            f'<text x="{bar_x+bar_w/2}" y="{baseline+20}" font-size="12" '
            f'fill="{CHART_SECONDARY_INK}" text-anchor="middle">{escape_html(str(cat))}</text>'
        )

    if footnote:
        parts.append(
            f'<text x="32" y="{H-15}" font-size="11" fill="{CHART_MUTED}">'
            f'{escape_html(footnote)}</text>'
        )

    parts.append("</svg>")
    return "\n".join(parts)


def build_page_html(title, paragraphs, image_map):
    """paragraphs: 문자열 리스트. image_map: {"1": "image1.png", ...} 형태로
    【N번 이미지】 마커를 실제 <img> 태그로 치환한다 (title.html 미리보기용)."""
    import re as _re
    marker_re = _re.compile(r"^【\s*(\d+)\s*번\s*이미지\s*】$")
    body_parts = []
    for p in paragraphs:
        stripped = p.strip()
        m = marker_re.match(stripped)
        if m and m.group(1) in image_map:
            body_parts.append(f'<p><img src="./{image_map[m.group(1)]}" style="max-width:100%;"></p>')
        else:
            body_parts.append(f"<p>{escape_html(p) or '&nbsp;'}</p>")

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{escape_html(title)}</title>
<style>
  body {{
    font-family: -apple-system, "Malgun Gothic", "Apple SD Gothic Neo", sans-serif;
    font-size: 16px; line-height: 1.8; max-width: 640px; margin: 24px auto; color: #222;
  }}
  h1 {{ font-size: 22px; margin-bottom: 20px; }}
  p {{ margin: 10px 0; }}
  img {{ display: block; margin: 14px 0; border-radius: 4px; }}
</style>
</head>
<body>
<h1>{escape_html(title)}</h1>
{chr(10).join(body_parts)}
</body>
</html>
"""
