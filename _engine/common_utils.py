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
    설치를 시도하거나, 실패를 기록하고 다음 이미지로 넘어가야 한다.

    ※ .svg 파일을 브라우저에 '문서'로 직접 열면(file:// + 확장자 .svg) 크로미움이
    루트 <svg>를 항상 뷰포트에 꽉 채워주지 않는다 — 실제 렌더 크기가 window-size보다
    작게 잡히면서 스크롤 가능한 여백(빈 페이지, 기본 흰 배경)이 오른쪽/아래에 남고
    스크롤바까지 찍히는 경우가 있었다(실측 확인, 2026-08-02). 그래서 SVG를 얇은 HTML
    래퍼에 넣고 CSS로 뷰포트에 강제로 꽉 채운 뒤, 그 .html을 스크린샷한다 —
    브라우저 버전에 기대지 않는 확실한 full-bleed 방법이다."""
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

    html_path = os.path.splitext(svg_path)[0] + "_wrap.html"
    # 래퍼 배경은 '카드에 절대 등장하지 않는 색'(마젠타)으로 깐다.
    # 클라우드 헤드리스는 뷰포트가 window-size와 어긋나며 가장자리에 배경색
    # 띠(레터박스)를 남기는데, 그 위치·크기가 실행마다 달라서 검은 배경으로는
    # '검은 띠'와 '어두운 카드 가장자리'를 구분할 수 없었다(패턴 추정 가드가
    # 두 번 뚫림, 2026-08-04~05 실측). 마젠타는 오탐이 원천 불가능하므로
    # 후처리(crop_letterbox)가 이 색만 정확히 잘라낸다.
    # ⚠ 크기는 vw/vh 가 아니라 '고정 픽셀'로 준다.
    #   100vw/100vh 는 뷰포트에 의존하는데, 클라우드 헤드리스는 뷰포트가
    #   --window-size 와 어긋나는 경우가 있다. 그러면 SVG가 축소되며 가장자리에
    #   배경색 띠(레터박스)가 남고, 그 위치·크기가 실행마다 달라 후처리로도
    #   완전히 막기 어려웠다(2026-08-04~08 세 차례 재발).
    #   viewBox 와 똑같은 픽셀 크기를 박으면 뷰포트와 무관하게 항상 원본 크기로
    #   그려지므로 애초에 띠가 생기지 않는다.
    html = (
        "<!doctype html><html><head><meta charset=\"utf-8\"><style>"
        f"html,body{{margin:0;padding:0;overflow:hidden;background:#f0f;"
        f"width:{int(w)}px;height:{int(h)}px}}"
        f"svg{{display:block;width:{int(w)}px;height:{int(h)}px}}"
        "</style></head><body>" + svg_content + "</body></html>"
    )
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    file_url = "file:///" + os.path.abspath(html_path).replace("\\", "/")
    cmd = [
        browser,
        "--headless",
        "--disable-gpu",
        "--no-sandbox",  # 클라우드 컨테이너에서 root로 돌 때 필요
        # 메모리 절약/안정화 플래그 — 순간 사용량을 낮춰 저사양·불안정 RAM에서
        # 크래시 방아쇠가 될 확률을 줄인다(기능 변화 없음).
        "--disable-dev-shm-usage",       # /dev/shm 대신 디스크 사용(공유메모리 고갈 방지)
        "--disable-extensions",
        "--disable-software-rasterizer",
        "--no-first-run", "--no-default-browser-check",
        "--disable-background-networking",
        f"--screenshot={os.path.abspath(png_path)}",
        f"--window-size={window_size}",
        "--force-device-scale-factor=2",
        "--hide-scrollbars",
        # 브라우저 기본 배경도 마젠타(ARGB) — 몸통 밖 영역까지 같은 키 색으로
        "--default-background-color=FFFF00FF",
        file_url,
    ]
    try:
        subprocess.run(cmd, timeout=30, capture_output=True, check=True)
        return os.path.exists(png_path)
    except Exception as e:
        print(f"  [경고] SVG->PNG 변환 실패: {e}")
        return False
    finally:
        if os.path.exists(html_path):
            os.remove(html_path)


def escape_html(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---- 숫자 강조 카드 (네이버 경제 블로그 썸네일 스타일) ----
CARD_W, CARD_H = 1080, 1080
CARD_BG_TOP = "#0f1f3d"
CARD_BG_BOT = "#0a1428"
CARD_ACCENT_UP = "#ff4d4f"      # 상승 = 빨강 (국내 증시 관행)
CARD_ACCENT_DOWN = "#2f80ed"    # 하락 = 파랑
CARD_GOLD = "#ffc83d"


_NEG_RE = re.compile(r"-\s*\d|▼|하락|급락|하회|순매도|감소|축소|마이너스")
_POS_RE = re.compile(r"\+\s*\d|▲|상승|급등|상회|순매수|증가|확대")


def infer_direction(delta, direction="up"):
    """delta 문구를 보고 화살표 방향을 정한다. 문구가 항상 진실이다.

    기사 JSON의 direction 필드는 사람이 손으로 쓰다 보니 문구와 어긋난다.
    실제로 '외국인 -2.83조 · 기관 -1.95조'(순매도)에 direction="up"이 붙어
    빨간 ▲ 위에 음수가 찍혔다(실측 2026-08-04). 보는 사람은 문구를 읽으므로
    문구에 하락 신호가 있으면 그쪽을 따른다."""
    text = str(delta or "")
    if _NEG_RE.search(text) and not _POS_RE.search(text):
        return "down"
    if _POS_RE.search(text) and not _NEG_RE.search(text):
        return "up"
    return direction        # 판단 불가(둘 다 있거나 없음) — 작성자 지정을 존중


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
    direction = infer_direction(delta, direction)   # 문구와 어긋나면 문구를 따른다
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
    # 주인공 숫자 + 단위. 둘을 한 줄에 그리므로 폭을 재서 캔버스를 넘지 않게 한다.
    #
    # 예전엔 200px/76px 고정이라, 단위가 길면('만원으로 상향', '엔캐리 청산 당시')
    # 오른쪽으로 그대로 밀려나가 글자가 잘렸다(실측 2026-08-04).
    # 숫자가 주인공이니 단위를 먼저 더 줄이고, 그래도 모자라면 둘 다 함께 줄인다.
    num_fs, unit_fs = 200, 76
    avail = CARD_W - 88 - 60            # 좌측 시작점과 우측 안전여백
    gap = 18
    while unit_fs > 46 and (_est_text_width(number, num_fs) + gap
                            + _est_text_width(number_unit, unit_fs)) > avail:
        unit_fs -= 2
    while num_fs > 110 and (_est_text_width(number, num_fs) + gap
                            + _est_text_width(number_unit, unit_fs)) > avail:
        num_fs -= 4
        unit_fs = min(unit_fs, int(num_fs * 0.42))
    p.append(
        f'<text x="88" y="470" font-size="{num_fs}" font-weight="800" fill="#ffffff" '
        f'letter-spacing="-4">{escape_html(number)}'
        f'<tspan font-size="{unit_fs}" font-weight="700" fill="#d5dded" dx="{gap}">'
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


def logo_tag(logo_path, x, y, box_w, box_h, plate=True):
    """카드 우상단 등에 로고를 넣는다. 원본 비율을 유지하며 박스 안에 맞춘다.

    ※ 로고는 상표다. 기사가 실제로 그 기업을 다룰 때만 쓴다.
      관련 없는 기사에 로고를 붙이면 그 기업 얘기인 것처럼 오인시키게 된다.

    plate=True : 어두운 배경에 얹는 코너 배지용 — 흰 라운드 판을 깔아 대비를 준다.
    plate=False: 큰 워터마크로 반투명하게 깔 때(stock_thumbnail 등) — 판 없이 로고만.
                 이때 box_w/box_h는 정사각(로고 대부분 원형)에 가깝게 넘겨야
                 빈 여백이 남는 '갇힌 박스' 느낌이 안 생긴다."""
    if not logo_path or not os.path.exists(logo_path):
        return ""
    uri = png_data_uri(logo_path)
    img_tag = (f'<image href="{uri}" x="{x}" y="{y}" width="{box_w}" height="{box_h}" '
               f'preserveAspectRatio="xMidYMid meet"/>')
    if not plate:
        return img_tag
    # 기업 로고는 대부분 어두운 원색이라 어두운 배경에 그냥 얹으면 묻힌다.
    # 흰 라운드 판을 깔아서 실제 인쇄물처럼 보이게 한다.
    pad = 22
    plate_rect = (f'<rect x="{x-pad}" y="{y-pad}" width="{box_w+pad*2}" height="{box_h+pad*2}" '
                  f'rx="18" fill="#ffffff" opacity="0.94"/>')
    return plate_rect + img_tag


# ---- 썸네일 카피 레이아웃 (폰트를 줄이지 말고 줄을 늘린다) ----
# 모바일 홈판 목록에서 썸네일은 손톱만 하게 줄어든다. 글자가 작아지는 순간
# 카피는 없는 것과 같아지므로, 카피가 길다고 폰트를 깎는 건 최악의 선택이다.
# 원칙: 폰트 크기를 먼저 지키고, 안 담기면 '줄 수'를 늘려서 해결한다.
COPY_MAX_FS = 118      # 짧은 카피(6~8자)일 때 쓰는 초대형 크기
COPY_PREFER_FS = 86    # 이 크기 밑으로 내려갈 바에는 줄을 하나 더 쓴다
COPY_MIN_FS = 76       # 절대 하한 — 어떤 경우에도 이보다 작게 쓰지 않는다


def _est_text_width(text, fs, stroke_ratio=0.17):
    """문자 종류별 평균 폭으로 렌더 폭을 추정한다(정확한 폰트 메트릭 대용).

    한글은 거의 정사각형, 라틴·숫자는 좁고, 공백·마침표는 더 좁다.
    주의할 함정 두 가지 — 둘 다 실측에서 오른쪽이 잘려 발견했다(2026-08-03):
      1) '%'는 좁은 기호가 아니다. 대부분의 서체에서 한글에 가깝게 넓다.
         '41%는'을 좁게 잡았다가 두 번째 줄이 캔버스 밖으로 밀렸다.
      2) 썸네일 글자는 fs*0.17 두께의 외곽선을 두르므로, 그 절반이 좌우로
         각각 삐져나온다. 글리프 폭만 재면 딱 그만큼 넘친다.
    굵은 웨이트(800) 기준이라 표준 폭보다 살짝 넉넉하게 잡는다."""
    wide_symbols = "%&@※₩"
    w = 0.0
    for ch in text:
        if not ch.isascii():
            w += fs * 1.00      # 한글 등 전각 문자
        elif ch in wide_symbols:
            w += fs * 0.95      # 퍼센트 등 — 사실상 전각에 가깝다
        elif ch.isalnum():
            w += fs * 0.60      # 라틴 문자·숫자
        else:
            w += fs * 0.30      # 공백·마침표·쉼표
    return w + fs * stroke_ratio    # 외곽선이 좌우로 삐져나오는 몫


def _balanced_wrap(words, n, fit, prefer_cut=None):
    """어절 리스트를 n줄로 나눈다. 우선순위는 (1) 폰트 크기 (2) 작성자 의도 (3) 균형.

    줄마다 길이가 들쭉날쭉하면 폰트는 제일 긴 줄에 끌려 내려가고 보기에도 엉성하다.
    그래서 먼저 폰트가 가장 크게 나오는 분할을 찾는다. 폰트 크기가 같은 분할이
    여럿이면(정수로 끊기니 흔하다) 작성자가 원래 끊어둔 자리(prefer_cut)를 그대로
    쓰는 쪽을 택한다 — 의미 단위가 안 깨져야 읽는 맛이 산다. 그래도 같으면
    줄 길이 편차가 작은(제곱합 최소) 쪽으로 간다.

    어절 수가 적으므로(보통 3~8개) 모든 분할을 그냥 다 따져본다.
    fit: 줄 리스트를 받아 그 배치에서 쓸 수 있는 폰트 크기를 돌려주는 함수."""
    import itertools
    if n <= 1:
        return [" ".join(words)]
    if len(words) <= n:
        return list(words)

    best, best_key = None, None
    for cuts in itertools.combinations(range(1, len(words)), n - 1):
        bounds = (0,) + cuts + (len(words),)
        lines = [" ".join(words[bounds[i]:bounds[i + 1]]) for i in range(n)]
        widths = [_est_text_width(ln, 100) for ln in lines]
        key = (-fit(lines),                                  # 폰트 큰 쪽 우선
               0 if (prefer_cut is not None and prefer_cut in cuts) else 1,
               sum(w * w for w in widths))                   # 균형 좋은 쪽
        if best_key is None or key < best_key:
            best, best_key = lines, key
    return best


def layout_thumb_copy(line1, line2, size=1080, left_margin=62, right_margin=48,
                      max_fs=COPY_MAX_FS, prefer_fs=COPY_PREFER_FS,
                      min_fs=COPY_MIN_FS, max_lines=4):
    """썸네일 카피를 (줄 리스트, 폰트크기)로 확정한다.

    동작 순서:
      1) 작성자가 준 2줄 그대로 썼을 때 prefer_fs(86px) 이상이면 그대로 존중한다
         — 의도한 끊는 위치가 대개 가장 자연스럽다.
      2) 안 되면 어절 단위로 2줄 → 3줄 → (최후) 4줄까지 늘려가며,
         prefer_fs 이상이 나오는 가장 적은 줄 수를 채택한다.
      3) 그래도 안 되면 그중 폰트가 가장 큰 배치를 쓰고 min_fs로 바닥을 받친다.

    반환 폰트는 max_fs에서 잘리므로 짧은 카피는 자동으로 초대형이 된다."""
    max_width = size - left_margin - right_margin

    def fit(lines):
        """이 줄 배치가 캔버스 폭에 들어가는 최대 폰트 크기."""
        widest = max(_est_text_width(ln, 100) for ln in lines) / 100.0
        if widest <= 0:
            return max_fs
        return int(min(max_fs, max_width / widest))

    given = [ln.strip() for ln in (line1, line2) if ln and ln.strip()]
    if not given:
        return [], max_fs

    # 1) 작성자가 끊어준 대로 충분히 크게 들어가면 그대로 간다
    if len(given) >= 2:
        fs_given = fit(given)
        if fs_given >= prefer_fs:
            return given, fs_given

    # 2) 어절 단위 재배치 — 줄 수를 늘려가며 큰 폰트를 찾는다
    words = " ".join(given).split()
    # 작성자가 끊어준 자리(= 1줄의 어절 수)를 재배치할 때도 되도록 살린다
    prefer_cut = len(given[0].split()) if len(given) >= 2 else None
    best_lines, best_fs = given, fit(given)
    for n in range(2, max_lines + 1):
        if n > len(words):
            break
        lines = _balanced_wrap(words, n, fit, prefer_cut)
        fs = fit(lines)
        if fs > best_fs:
            best_lines, best_fs = lines, fs
        if fs >= prefer_fs:
            # 원하는 크기를 만족하는 가장 적은 줄 수에서 멈춘다
            return lines, fs

    # 3) 최후 방어 — 폰트는 하한 아래로 내리지 않는다
    return best_lines, max(best_fs, min_fs)


def _card_open(accent):
    """4종 카드가 공유하는 배경·그라데이션. 시리즈 통일감의 핵심.

    캔버스를 정확히 0,0~CARD_W,CARD_H로 채운다. 예전엔 스크린샷 시 흰 여백이
    비치는 걸 막으려 배경을 몇 px 더 크게 그리는 임시방편(bleed)을 썼지만,
    진짜 원인은 convert_svg_to_png()가 .svg를 문서로 직접 열어 뷰포트를 안
    꽉 채우던 것이었다 — 그건 HTML 래퍼로 근본 수정했으니 여기서는 다시
    깔끔하게 정확한 캔버스 크기로만 그린다."""
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
    """하단 출처/자료 표기 — 사용자 요청으로 표시하지 않는다 (항상 빈 문자열)."""
    return ""


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
    # 남은 세로 공간에 행을 균등 배치해 아래쪽이 비지 않게 한다.
    #
    # 예전엔 하단 150px를 note(출처 표기) 자리로 비워뒀는데, 출처 표기를 없앤
    # 뒤로는 그 150px가 그냥 빈 공간으로 남아 카드 아래가 휑하게 보였다(실측).
    # 또 '마지막 행의 막대 높이(BOTTOM)'를 안 빼서 실제보다 더 위에서 끝났다.
    # 이제 마지막 막대가 하단 여백 직전에 놓이도록 역산한다.
    BOTTOM, MARGIN = 48, 72          # 마지막 행이 차지하는 높이 / 하단 여백
    space = CARD_H - MARGIN - BOTTOM - y
    row_h = space // (len(items) - 1) if len(items) > 1 else space
    row_h = max(96, min(150, row_h))
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


# 요약 카드에서 색으로 강조할 토큰: 숫자 + 단위(%, 조원, 억, 년, 배, 위 …).
# 홈판 독자는 카드를 1~2초 훑는다 — 숫자가 흰 본문에 묻히면 카드의 정보값이 죽는다.
_EMPH_RE = re.compile(
    r"[+\-▲▼]?\d[\d,.]*\s?(?:%p|%|조\s?원|억\s?원|만\s?원|천\s?원|조|억|만|원|"
    r"년째|년|개월|월|일째|일|주째|주|배|건|명|곳|호|p|포인트|kg|위|세|%대)?")


def _emphasize(line, accent):
    """문장 속 숫자 토큰만 강조색 tspan 으로 감싼다. 나머지는 흰색 유지."""
    out, last = [], 0
    for m in _EMPH_RE.finditer(line):
        if m.start() > last:
            out.append(escape_html(line[last:m.start()]))
        out.append(f'<tspan fill="{accent}" font-weight="800">'
                   f'{escape_html(m.group(0))}</tspan>')
        last = m.end()
    out.append(escape_html(line[last:]))
    return "".join(out)


def _wrap_to_width(text, fs, max_w):
    """어절 단위로 감싸 max_w 를 넘지 않는 줄 리스트로 만든다.

    한 어절이 그 자체로 폭을 넘으면(긴 영문·숫자 조합) 글자 단위로 쪼갠다.
    폰트만 줄이고 줄바꿈을 안 하면 캔버스 밖으로 나가 글자가 잘린다 —
    실제로 42px 하한에서도 297px 넘치는 줄이 나왔다(실측 2026-08-08)."""
    words, lines, cur = text.split(), [], ""
    for wd in words:
        trial = (cur + " " + wd).strip()
        if not cur or _est_text_width(trial, fs) <= max_w:
            cur = trial
            continue
        lines.append(cur)
        if _est_text_width(wd, fs) <= max_w:
            cur = wd
        else:                       # 어절 하나가 너무 길다 -> 글자 단위
            cur = ""
            for ch in wd:
                if _est_text_width(cur + ch, fs) <= max_w:
                    cur += ch
                else:
                    lines.append(cur)
                    cur = ch
    if cur:
        lines.append(cur)
    return lines or [""]


def build_summary_card_svg(eyebrow, title_lines, points, note="", accent=CARD_GOLD):
    """마무리 정리 카드. points = ["한 줄", ...] 또는 [["윗줄","아랫줄"], ...]

    '저장해두고 싶은' 카드를 만들어 스크랩을 유도한다.
    스크랩·공유는 체류시간만큼이나 노출에 영향을 준다."""
    p = [_card_open(accent)]
    head, y = _card_head(eyebrow, title_lines, accent)
    p.append(head)

    y += 56
    avail = CARD_W - 172 - 72          # 번호 배지 오른쪽 ~ 우측 여백
    BOTTOM_MARGIN, MIN_GAP = 96, 40

    # 폰트를 크게 잡되(모바일 가독성), 폭은 '줄바꿈'으로 맞추고 세로가 넘칠 때만
    # 줄인다. 예전엔 폭을 폰트로만 맞추려다 하한(42px)에서 포기하고 그대로
    # 넘쳐 흘러 글자가 잘렸다.
    for fs in range(52, 33, -2):
        wrapped = [_wrap_to_width(ln, fs, avail)
                   for pt in points
                   for ln in (pt if isinstance(pt, list) else [pt])]
        # 원래 point 단위로 다시 묶는다
        grouped, k = [], 0
        for pt in points:
            n = len(pt) if isinstance(pt, list) else 1
            grouped.append([w for sub in wrapped[k:k + n] for w in sub])
            k += n
        line_h = int(fs * 1.30)
        text_h = sum(len(g) for g in grouped) * line_h
        need = text_h + MIN_GAP * (len(points) - 1)
        if need <= CARD_H - BOTTOM_MARGIN - y:
            break

    free = CARD_H - BOTTOM_MARGIN - y - text_h
    gap = free // (len(points) - 1) if len(points) > 1 else 54
    gap = max(MIN_GAP, min(120, gap))

    for i, lines in enumerate(grouped, start=1):
        p.append(f'<circle cx="118" cy="{y-14}" r="30" fill="{accent}" opacity="0.18"/>')
        p.append(
            f'<text x="118" y="{y}" font-size="34" font-weight="800" fill="{accent}" '
            f'text-anchor="middle">{i}</text>'
        )
        ty = y + 2
        for line in lines:
            # 숫자·단위는 강조색으로 — 흰 본문 속에서 정보가 먼저 눈에 들어온다
            p.append(
                f'<text x="172" y="{ty}" font-size="{fs}" font-weight="600" '
                f'fill="#ffffff">{_emphasize(line, accent)}</text>'
            )
            ty += line_h
        y = ty + gap

    p.append(_card_note(note))
    p.append("</svg>")
    return "".join(p)


def _variation_filter(var, filter_id):
    """photo_library.variation_seed()가 만든 dict(align/saturate/hue/bright)로
    SVG <filter> 정의와 preserveAspectRatio 값을 만든다.

    같은 원본 사진이라도 '오늘 이 순번'마다 크롭 위치·톤이 살짝 달라 보이게
    해서 라이브러리를 돌려써도 매번 같은 컷이라는 티가 덜 나게 한다.
    var가 없으면(기존 방식대로 파일명을 직접 지정한 경우 등) 무보정 기본값."""
    if not var:
        return "", "xMidYMid slice"
    align = var.get("align", "xMidYMid")
    sat = var.get("saturate", 1.0)
    hue = var.get("hue", 0)
    bright = var.get("bright", 1.0)
    filt = (
        f'<filter id="{filter_id}" color-interpolation-filters="sRGB">'
        f'<feColorMatrix type="hueRotate" values="{hue}"/>'
        f'<feColorMatrix type="saturate" values="{sat}"/>'
        f'<feComponentTransfer>'
        f'<feFuncR type="linear" slope="{bright}"/>'
        f'<feFuncG type="linear" slope="{bright}"/>'
        f'<feFuncB type="linear" slope="{bright}"/>'
        f'</feComponentTransfer>'
        f'</filter>'
    )
    return filt, f"{align} slice"


THUMB_INK = "#ffffff"
THUMB_STROKE = "#0a1018"
THUMB_ACCENT = "#7dffce"     # 민트 — 숫자·종목명 강조용


def _candle_path(seed_points, x0, y0, w, h, down=True):
    """곤두박질(또는 급등) 라인+영역 차트 좌표를 만든다.

    실제 시세를 쓰는 게 아니라 '분위기'를 그리는 것이므로,
    down이면 우하향, 아니면 우상향으로 끝점을 몰아준다."""
    n = len(seed_points)
    lo, hi = min(seed_points), max(seed_points)
    rng = (hi - lo) or 1
    step = w / (n - 1)
    pts = [(x0 + i * step, y0 + h - (v - lo) / rng * h) for i, v in enumerate(seed_points)]
    return pts


def build_stock_thumbnail_svg(line1, line2, price="", delta="", down=True,
                              brand="", tagline="", logo_path=None,
                              accent_words=None, size=1080, series=None,
                              logo_opacity=0.6):
    """종목 주가 썸네일. 배경에 곤두박질/급등 차트를 깔고 카피를 얹는다.

    사용자 요청: "하이닉스 관련이면 하이닉스 배경에 주식차트 150만원 밑으로
    곤두박질 치는 이미지". 무료 CC 스톡에는 이런 장면이 없으므로 직접 그린다.
    스톡 사진보다 정보성(종목·방향·가격)이 높고, 매일 데이터만 바꾸면 된다.

    down=True  : 하락 (파랑, 우하향, ▼)  ← 한국 증시 관행: 파랑=하락/매도
    down=False : 상승 (빨강, 우상향, ▲)  ← 빨강=상승/매수
    """
    accent_words = accent_words or []
    # 한국 증시 색상 관행 (미국과 반대): 상승=빨강, 하락=파랑
    color = "#2f80ed" if down else "#ff4d5e"
    arrow = "▼" if down else "▲"
    # 기본 시세 곡선 (분위기용). down이면 뒤로 갈수록 급락하는 형태
    if series is None:
        series = ([100, 96, 98, 90, 92, 84, 80, 70, 66, 54, 48, 40]
                  if down else
                  [40, 46, 44, 52, 58, 62, 70, 74, 82, 88, 94, 100])

    p = [f'<svg viewBox="0 0 {size} {size}" xmlns="http://www.w3.org/2000/svg" '
         f'font-family="Pretendard, \'Malgun Gothic\', sans-serif">']
    p.append(
        '<defs>'
        f'<linearGradient id="sbg" x1="0.1" y1="0" x2="0.7" y2="1">'
        f'<stop offset="0%" stop-color="#101826"/>'
        f'<stop offset="100%" stop-color="#05080f"/></linearGradient>'
        f'<linearGradient id="sarea" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="{color}" stop-opacity="0.5"/>'
        f'<stop offset="100%" stop-color="{color}" stop-opacity="0"/></linearGradient>'
        f'<linearGradient id="sscrim" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="#05080f" stop-opacity="0.10"/>'
        f'<stop offset="55%" stop-color="#05080f" stop-opacity="0.35"/>'
        f'<stop offset="100%" stop-color="#05080f" stop-opacity="0.86"/></linearGradient>'
        '</defs>'
    )
    p.append(f'<rect width="{size}" height="{size}" fill="url(#sbg)"/>')

    # 배경 로고 워터마크 (있을 때). 정사각 박스 + 판(plate) 없이 로고만 얹는다 —
    # 이전엔 폭이 2배 넓은 박스에 원형 로고를 'meet'로 맞추다 보니 로고 양옆으로
    # 빈 회색 판이 크게 남아 '갇혀 잘린' 것처럼 보였다.
    if logo_path and os.path.exists(logo_path):
        # 좌측 중단에 배치 — 우상단 가격/등락률과 안 겹치게
        lsize = size * 0.30
        lx, ly = size * 0.08, size * 0.36
        p.append(f'<g opacity="{logo_opacity}">'
                 f'{logo_tag(logo_path, lx, ly, lsize, lsize, plate=False)}</g>')

    # 격자
    for i in range(1, 5):
        gy = size * i / 5
        p.append(f'<line x1="0" y1="{gy}" x2="{size}" y2="{gy}" '
                 f'stroke="#ffffff" stroke-opacity="0.05" stroke-width="1"/>')

    # 차트 영역 (화면 중앙~하단을 크게 가로지름)
    cx, cy, cw, ch = 40, size * 0.30, size - 80, size * 0.42
    pts = _candle_path(series, cx, cy, cw, ch, down=down)
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"{pts[0][0]:.1f},{cy+ch:.1f} " + line + f" {pts[-1][0]:.1f},{cy+ch:.1f}"
    p.append(f'<polygon points="{area}" fill="url(#sarea)"/>')
    p.append(f'<polyline points="{line}" fill="none" stroke="{color}" '
             f'stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>')
    ex, ey = pts[-1]
    p.append(f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="16" fill="{color}"/>')
    p.append(f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="30" fill="{color}" opacity="0.3"/>')

    p.append(f'<rect width="{size}" height="{size}" fill="url(#sscrim)"/>')

    # 가격 + 등락률 배지 (우상단)
    if price:
        p.append(f'<text x="{size-44}" y="150" font-size="66" font-weight="800" '
                 f'fill="#ffffff" text-anchor="end" letter-spacing="-1">{escape_html(price)}</text>')
    if delta:
        dw = 60 + len(delta) * 30
        p.append(f'<rect x="{size-44-dw}" y="176" width="{dw}" height="60" rx="30" fill="{color}"/>')
        p.append(f'<text x="{size-44-dw/2}" y="217" font-size="34" font-weight="700" '
                 f'fill="#ffffff" text-anchor="middle">{arrow} {escape_html(delta)}</text>')

    # 카피 2줄
    def tspans(text):
        if not accent_words:
            return escape_html(text)
        import re as _re
        pat = "(" + "|".join(_re.escape(w) for w in accent_words) + ")"
        parts = [x for x in _re.split(pat, text) if x]
        return "".join(f'<tspan fill="{THUMB_ACCENT}">{escape_html(x)}</tspan>'
                       if x in accent_words else escape_html(x) for x in parts)

    # 카피는 아래쪽 기준선에 붙여 쌓는다 — 3줄이 되면 위로 자라야
    # 하단 브랜드·태그라인을 밀지 않는다.
    lines, fs = layout_thumb_copy(line1, line2, size)
    gap = int(fs * 1.16)
    last_y = int(size * 0.72) + int(92 * 1.16)   # 기존 2줄 배치의 둘째 줄 위치
    for i, ln in enumerate(lines):
        y = last_y - (len(lines) - 1 - i) * gap
        p.append(f'<text x="62" y="{y}" font-size="{fs}" font-weight="800" '
                 f'fill="{THUMB_INK}" stroke="{THUMB_STROKE}" stroke-width="{fs*0.17:.0f}" '
                 f'stroke-linejoin="round" paint-order="stroke" letter-spacing="-2">'
                 f'{tspans(ln)}</text>')

    if brand:
        # 배경 박스(테두리) 없이 텍스트만. 밝은 사진 대비용으로 약한 외곽선만.
        p.append(f'<text x="{size-38}" y="{size-52}" font-size="27" font-weight="700" '
                 f'fill="#ffffff" text-anchor="end" letter-spacing="1" '
                 f'stroke="#0a1018" stroke-width="3.5" paint-order="stroke">{escape_html(brand)}</text>')
    if tagline:
        p.append(f'<text x="62" y="{size-52}" font-size="25" font-weight="600" '
                 f'fill="#ffffff" opacity="0.70" letter-spacing="3">{escape_html(tagline)}</text>')
    p.append("</svg>")
    return "".join(p)


def build_thumbnail_svg(photo_path, line1, line2, brand="", tagline="",
                        accent_words=None, size=1080, dim=0.0, variation=None,
                        logo_path=None):
    """홈판 썸네일. 사진 위에 2줄 카피를 두꺼운 외곽선으로 얹는다.

    설계 근거 (상위 블로그 구조 분석):
      1) 사진은 분위기만 담당하고 정보는 텍스트가 전담한다.
         -> 기사와 딱 맞는 사진을 못 구해도 톤만 맞으면 쓸 수 있다
      2) 기본 2줄. 단 카피가 길어 2줄에 크게 안 담기면 폰트를 줄이는 대신
         layout_thumb_copy가 3줄로 재배치한다 (모바일 가독성 > 줄 수)
      3) 외곽선(paint-order: stroke)이 핵심. 이게 없으면 밝은 사진에서 글자가 사라진다
      4) 숫자·종목명만 색을 바꿔 시선을 그쪽으로 먼저 보낸다

    accent_words: 강조할 단어 리스트 (예: ["하이닉스", "150만원"])
    logo_path  : 기업 로고 (assets/tickers 또는 assets/logos). 특정 기업 기사면
                 반드시 넣는다 — 무료 스톡에는 '그 회사' 사진이 없어서 배경은
                 어차피 범용 이미지가 되는데, 좌상단 로고 하나면 "무슨 회사
                 얘기인지"가 0.1초에 잡힌다. 매칭 품질을 올리는 가장 싼 방법.
                 ※ 상표이므로 그 기업을 실제로 다루는 기사에만 쓴다.
    """
    import base64
    import mimetypes
    mime = mimetypes.guess_type(photo_path)[0] or "image/jpeg"
    with open(photo_path, "rb") as f:
        uri = f"data:{mime};base64," + base64.b64encode(f.read()).decode()

    accent_words = accent_words or []

    def tspans(text):
        """강조 단어만 민트색으로 바꾼다. 나머지는 흰색."""
        if not accent_words:
            return escape_html(text)
        import re as _re
        pat = "(" + "|".join(_re.escape(w) for w in accent_words) + ")"
        parts = [p for p in _re.split(pat, text) if p]
        out = []
        for p in parts:
            if p in accent_words:
                out.append(f'<tspan fill="{THUMB_ACCENT}">{escape_html(p)}</tspan>')
            else:
                out.append(escape_html(p))
        return "".join(out)

    # 아래쪽 기준선에 붙여 쌓는다 — 3줄이 되면 위로 자란다(하단 태그라인 보호)
    lines, fs = layout_thumb_copy(line1, line2, size)
    gap = int(fs * 1.16)
    last_y = int(size * 0.70) + int(92 * 1.16)   # 기존 2줄 배치의 둘째 줄 위치

    filt_def, par = _variation_filter(variation, "var-thumb")
    p = [f'<svg viewBox="0 0 {size} {size}" xmlns="http://www.w3.org/2000/svg" '
         f'font-family="Pretendard, \'Malgun Gothic\', sans-serif">']
    p.append(
        '<defs>'
        '<linearGradient id="tscrim" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0%" stop-color="#000000" stop-opacity="0.30"/>'
        '<stop offset="45%" stop-color="#000000" stop-opacity="0.14"/>'
        '<stop offset="100%" stop-color="#000000" stop-opacity="0.52"/></linearGradient>'
        + filt_def +
        '</defs>'
    )
    filt_attr = ' filter="url(#var-thumb)"' if filt_def else ""
    p.append(f'<image href="{uri}" x="0" y="0" width="{size}" height="{size}" '
             f'preserveAspectRatio="{par}"{filt_attr}/>')
    p.append(f'<rect width="{size}" height="{size}" fill="url(#tscrim)"/>')
    # 배경이 시끄러운 사진(웨이퍼·전광판 등)은 dim을 올려 글자와의 경쟁을 없앤다
    if dim > 0:
        p.append(f'<rect width="{size}" height="{size}" fill="#050a12" opacity="{dim}"/>')

    # 카피 — 외곽선을 글자 뒤로 깔아야(paint-order) 획이 안 갉힌다
    for i, line in enumerate(lines):
        y = last_y - (len(lines) - 1 - i) * gap
        p.append(
            f'<text x="62" y="{y}" font-size="{fs}" font-weight="800" '
            f'fill="{THUMB_INK}" stroke="{THUMB_STROKE}" stroke-width="{fs*0.17:.0f}" '
            f'stroke-linejoin="round" paint-order="stroke" letter-spacing="-2">'
            f'{tspans(line)}</text>'
        )

    # 기업 로고 — 좌상단(우상단 브랜드 배지와 좌우 대칭). 흰 판을 깔아 어떤
    # 사진 위에서도 로고가 묻히지 않게 한다.
    if logo_path and os.path.exists(logo_path):
        p.append(logo_tag(logo_path, 62, 46, 214, 84, plate=True))

    if brand:
        # 배경 박스(테두리) 없이 텍스트만. 우상단, 약한 외곽선만.
        p.append(f'<text x="{size-38}" y="69" font-size="27" font-weight="700" '
                 f'fill="#ffffff" text-anchor="end" letter-spacing="1" '
                 f'stroke="#0a1018" stroke-width="3.5" paint-order="stroke">'
                 f'{escape_html(brand)}</text>')
    if tagline:
        p.append(f'<text x="62" y="{size-44}" font-size="25" font-weight="600" '
                 f'fill="#ffffff" opacity="0.78" letter-spacing="3">'
                 f'{escape_html(tagline)}</text>')
    p.append("</svg>")
    return "".join(p)


def build_photo_card_svg(photo_path, eyebrow, headline_lines, credit="",
                         number=None, number_unit="", delta="", direction="up",
                         accent=CARD_ACCENT_UP, logo_path=None, variation=None):
    """실사 사진을 꽉 채우고 그 위에 카피를 얹는 카드.

    핵심은 스크림(scrim)이다. 사진 위에 흰 글씨를 그냥 얹으면 밝은 부분에서 글자가
    사라진다. 아래에서 위로 어두워지는 그라데이션을 깔아야 어떤 사진이 와도 글이 읽힌다.

    photo_path : 로컬 파일 (jpg/png). 재게시 가능한 라이선스인지 확인된 것만 넣는다.
    credit     : 이미지 위에는 더 이상 표기하지 않는다(디자인 클러터 제거, 확정 규칙).
                 라이선스 출처 기록은 이 값을 호출부(기사 JSON)에 남겨 별도로 추적한다.
    """
    import base64
    import mimetypes
    mime = mimetypes.guess_type(photo_path)[0] or "image/jpeg"
    with open(photo_path, "rb") as f:
        uri = f"data:{mime};base64," + base64.b64encode(f.read()).decode()

    filt_def, par = _variation_filter(variation, "var-photocard")
    p = [f'<svg viewBox="0 0 {CARD_W} {CARD_H}" xmlns="http://www.w3.org/2000/svg" '
         f'font-family="Pretendard, \'Malgun Gothic\', system-ui, sans-serif">']
    p.append(
        '<defs>'
        # 아래 60%를 덮는 스크림 — 사진이 밝든 어둡든 카피 가독성을 보장한다
        '<linearGradient id="scrim" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0%" stop-color="#050d1a" stop-opacity="0"/>'
        '<stop offset="42%" stop-color="#050d1a" stop-opacity="0.34"/>'
        '<stop offset="72%" stop-color="#050d1a" stop-opacity="0.82"/>'
        '<stop offset="100%" stop-color="#050d1a" stop-opacity="0.96"/></linearGradient>'
        # 상단도 살짝 눌러서 eyebrow가 뜨게
        '<linearGradient id="topfade" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0%" stop-color="#050d1a" stop-opacity="0.55"/>'
        '<stop offset="100%" stop-color="#050d1a" stop-opacity="0"/></linearGradient>'
        + filt_def +
        '</defs>'
    )
    filt_attr = ' filter="url(#var-photocard)"' if filt_def else ""
    # slice = 비율 유지하며 꽉 채우기 (여백 없이 crop)
    p.append(f'<image href="{uri}" x="0" y="0" width="{CARD_W}" height="{CARD_H}" '
             f'preserveAspectRatio="{par}"{filt_attr}/>')
    p.append(f'<rect width="{CARD_W}" height="{CARD_H}" fill="url(#scrim)"/>')
    p.append(f'<rect width="{CARD_W}" height="300" fill="url(#topfade)"/>')

    p.append(logo_tag(logo_path, CARD_W - 88 - 260, 84, 260, 78))
    p.append(f'<rect x="88" y="96" width="8" height="66" rx="4" fill="{accent}"/>')
    p.append(f'<text x="122" y="144" font-size="36" font-weight="600" fill="#ffffff" '
             f'opacity="0.92">{escape_html(eyebrow)}</text>')

    # 카피는 아래에서부터 쌓아 올린다 (사진 주제가 위쪽에 오는 경우가 많아서)
    bottom = CARD_H - 76
    y = bottom - 84 * (len(headline_lines) - 1)
    if number:
        y -= 150
    for line in headline_lines:
        p.append(f'<text x="88" y="{y}" font-size="70" font-weight="800" fill="#ffffff" '
                 f'letter-spacing="-1.5">{escape_html(line)}</text>')
        y += 84
    if number:
        y += 34
        # number_card와 같은 이유로 폭을 재서 줄인다 — 단위가 길면 잘려나간다
        num_fs, unit_fs, gap = 112, 48, 14
        avail = CARD_W - 88 - 60
        while unit_fs > 32 and (_est_text_width(str(number), num_fs) + gap
                                + _est_text_width(number_unit, unit_fs)) > avail:
            unit_fs -= 2
        while num_fs > 70 and (_est_text_width(str(number), num_fs) + gap
                               + _est_text_width(number_unit, unit_fs)) > avail:
            num_fs -= 3
        p.append(f'<text x="88" y="{y}" font-size="{num_fs}" font-weight="800" fill="#ffffff" '
                 f'letter-spacing="-3">{escape_html(str(number))}'
                 f'<tspan font-size="{unit_fs}" fill="#d5dded" dx="{gap}">'
                 f'{escape_html(number_unit)}</tspan></text>')
        if delta:
            dr = infer_direction(delta, direction)
            arrow = "▲" if dr == "up" else "▼"
            accent = CARD_ACCENT_UP if dr == "up" else CARD_ACCENT_DOWN
            p.append(f'<text x="{88 + 12}" y="{y+58}" font-size="40" font-weight="700" '
                     f'fill="{accent}">{arrow} {escape_html(delta)}</text>')

    # 출처/자료 표기는 사용자 요청으로 표시하지 않는다 (credit 무시)
    p.append("</svg>")
    return "".join(p)


def build_bar_card_svg(eyebrow, title_lines, categories, values, displays=None,
                       note="", accent=CARD_ACCENT_UP, highlight=None):
    """세로 막대 카드 (다크 톤). 나머지 3종과 같은 배경·서체를 쓴다."""
    p = [_card_open(accent)]
    head, y = _card_head(eyebrow, title_lines, accent)
    p.append(head)

    displays = displays or [f"{v:,.0f}" for v in values]
    # 하단 예약은 '카테고리 라벨(baseline +56)'에 필요한 만큼만 둔다.
    # 예전 190은 없어진 note(출처 표기) 자리까지 잡고 있어서 카드 아래가 휑했다.
    top, bottom = y + 70, CARD_H - 150
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
