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
