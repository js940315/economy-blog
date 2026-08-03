# -*- coding: utf-8 -*-
"""사진 라이브러리의 '중복'과 '썸네일 적합도'를 실제 픽셀로 판정한다.

    python _engine/photo_quality.py audit          # 현재 라이브러리 진단
    python _engine/photo_quality.py audit --fix    # 근접중복 자동 정리(index 갱신)

왜 필요한가 (2026-08-03, 사용자: "같은 사진 중복 최악"):
  장수만 늘리면 중복이 해결되지 않는다. 같은 검색어로 20장을 받으면 거의 똑같은
  아파트 사진 20장이 쌓일 뿐이고, 스톡 API는 서로 다른 출처에서 같은 사진을
  주기도 한다. 파일명이 다르니 순환 로직은 '다른 사진'으로 착각한다.
  → 파일명이 아니라 픽셀로 같은지 봐야 한다.

두 가지를 본다:
  1) 근접중복(dhash) — 사람 눈에 "또 그 사진이네" 소리가 나오는 쌍을 잡는다
  2) 썸네일 적합도  — 우리 썸네일은 흰 글씨를 얹는다. 사진이 너무 밝으면
     카피가 죽는다(dim을 올려도 한계). 밝기·대비를 재서 미리 알려준다.
"""

import argparse
import io
import json
import os
import sys

from PIL import Image, ImageStat

def _force_utf8_stdout():
    """윈도우 콘솔 기본 코드페이지(cp949)는 '—' 같은 문자를 못 찍고 죽는다.

    ※ 반드시 CLI 진입점에서만 부른다. 예전엔 모듈 최상단에서 sys.stdout 을
      갈아끼웠는데, 이 모듈을 import 하는 쪽(build_posts 등)의 stdout까지
      바꿔버려서 호출부가 'I/O operation on closed file'로 죽었다(실측)."""
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                      errors="replace")

PHOTO_DIR = os.path.join("assets", "photos")
INDEX_PATH = os.path.join(PHOTO_DIR, "index.json")

# dhash 해밍거리가 이 값 이하면 '구조가 비슷하다'고 본다.
# 0~4: 거의 동일(리사이즈·재압축본), 5~10: 같은 촬영의 다른 컷일 가능성.
DUP_DISTANCE = 10

# ※ dhash 만으로는 오탐이 난다. 한강 다리 사진과 실리콘 웨이퍼 접사가 거리 9로
#   잡힌 적이 있다 — 둘 다 '반복되는 가로 띠' 구조라서 밝기 패턴이 닮았다(실측).
#   그래서 색 분포까지 같아야 중복으로 확정한다. 파랑-회색 도시 vs 노란 웨이퍼처럼
#   색이 완전히 다르면 구조가 닮아도 사람 눈엔 전혀 다른 사진이다.
COLOR_LIMIT = 0.22

# 자동 삭제(--fix)는 이 거리 이하에서만 한다. 애매한 건 사람이 보고 지운다 —
# 잘못 지우면 다양성이 오히려 줄어드는 게 이 작업의 목적과 정반대이므로 보수적으로.
AUTOFIX_DISTANCE = 4

# 썸네일 배경으로 쓸 때 흰 글씨가 살아남는 평균 밝기 상한(0~255).
# 이보다 밝으면 dim을 크게 줘야 하고, 그래도 답답하면 다른 사진을 쓰는 게 낫다.
BRIGHT_LIMIT = 165


def dhash(path, size=8):
    """인접 픽셀 밝기 비교로 만드는 64비트 지각 해시.

    리사이즈·재압축·약간의 크롭에도 값이 거의 안 변해서 '같은 사진'을 잘 잡는다.
    (파일 해시(md5)는 1픽셀만 달라도 완전히 달라져서 이 용도로는 못 쓴다.)"""
    try:
        im = Image.open(path).convert("L").resize((size + 1, size), Image.LANCZOS)
    except OSError:
        return None
    px = list(im.tobytes())   # getdata()는 Pillow 14에서 제거 예정
    bits = 0
    for row in range(size):
        for col in range(size):
            left = px[row * (size + 1) + col]
            right = px[row * (size + 1) + col + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return bits


def hamming(a, b):
    return bin(a ^ b).count("1")


def color_signature(path, bins=4):
    """RGB 색 분포를 정규화한 벡터. 구조가 아니라 '색감'을 비교하기 위한 값.

    채널당 bins개 구간으로 나눈 3차원 히스토그램을 1차원으로 편다."""
    try:
        im = Image.open(path).convert("RGB").resize((64, 64), Image.LANCZOS)
    except OSError:
        return None
    step = 256 // bins
    hist = [0] * (bins ** 3)
    data = im.tobytes()
    for i in range(0, len(data), 3):
        r, g, b = data[i] // step, data[i + 1] // step, data[i + 2] // step
        hist[min(r, bins - 1) * bins * bins
             + min(g, bins - 1) * bins
             + min(b, bins - 1)] += 1
    total = sum(hist) or 1
    return [h / total for h in hist]


def color_distance(sig_a, sig_b):
    """두 색 분포의 차이(0=동일, 1=완전히 다름). L1 거리의 절반."""
    if not sig_a or not sig_b:
        return 1.0
    return sum(abs(x - y) for x, y in zip(sig_a, sig_b)) / 2.0


def brightness(path):
    """평균 밝기와 표준편차(대비). 흰 글씨가 읽히는지 가늠하는 값."""
    try:
        im = Image.open(path).convert("L")
    except OSError:
        return None, None
    st = ImageStat.Stat(im)
    return st.mean[0], st.stddev[0]


def suggest_dim(path, requested=0.0):
    """이 사진 위에 흰 글씨를 얹으려면 얼마나 어둡게 깔아야 하는지 계산한다.

    썸네일 카피는 항상 흰색이라 배경이 밝으면 그냥 안 읽힌다. 사람이 사진마다
    dim 값을 눈으로 정하게 하면 반드시 빠뜨리므로(그리고 자동 선택된 사진은
    애초에 사람이 안 봤으므로) 실제 밝기를 재서 자동으로 정한다.

    기사 JSON이 더 큰 dim을 명시했으면 그쪽을 존중한다 — 연출 의도일 수 있어서
    '더 어둡게'는 허용하고 '더 밝게'만 막는다."""
    mean, _ = brightness(path)
    if mean is None:
        return requested
    if mean < 90:
        auto = 0.15          # 이미 어두움 — 과하게 깔면 사진이 죽는다
    elif mean < 130:
        auto = 0.28
    elif mean < BRIGHT_LIMIT:
        auto = 0.40
    else:
        auto = 0.52          # 밝은 사진 — 강하게 깔아야 카피가 산다
    return max(requested or 0.0, auto)


def _load_index():
    try:
        with open(INDEX_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_index(idx):
    tmp = INDEX_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, INDEX_PATH)


def library_entries():
    """index.json 에 있고 실물 파일도 존재하는 사진 목록."""
    idx = _load_index()
    out = []
    for fname, meta in idx.items():
        if fname.startswith("_") or not isinstance(meta, dict):
            continue
        path = os.path.join(PHOTO_DIR, fname)
        if os.path.exists(path):
            cat = meta.get("카테고리") or fname.split("_")[0]
            out.append((fname, path, cat))
    return out


def find_duplicates(entries=None, distance=DUP_DISTANCE):
    """근접중복 쌍을 찾는다. 반환: [(파일A, 파일B, 거리), ...]

    카테고리가 달라도 같은 사진이면 잡는다 — 다른 카테고리에 같은 사진이
    들어가 있으면 독자 입장에선 더 이상하게 보인다."""
    entries = entries if entries is not None else library_entries()
    items = []
    for fname, path, cat in entries:
        h = dhash(path)
        if h is not None:
            items.append((fname, h, color_signature(path)))
    pairs = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            d = hamming(items[i][1], items[j][1])
            if d > distance:
                continue
            # 구조가 닮아도 색감이 다르면 사람 눈엔 다른 사진이다 -> 중복 아님
            cd = color_distance(items[i][2], items[j][2])
            if cd > COLOR_LIMIT:
                continue
            pairs.append((items[i][0], items[j][0], d, cd))
    pairs.sort(key=lambda p: (p[2], p[3]))
    return pairs


def is_duplicate_of_library(path, distance=DUP_DISTANCE, entries=None):
    """새로 받은 사진이 이미 라이브러리에 있는 것과 겹치는지.

    소싱 단계에서 이걸로 걸러야 중복이 애초에 안 쌓인다(사후 정리보다 확실하다).
    반환: 겹치는 기존 파일명 또는 None."""
    h = dhash(path)
    if h is None:
        return None
    sig = color_signature(path)
    entries = entries if entries is not None else library_entries()
    for fname, epath, cat in entries:
        eh = dhash(epath)
        if eh is None or hamming(h, eh) > distance:
            continue
        if color_distance(sig, color_signature(epath)) <= COLOR_LIMIT:
            return fname
    return None


def audit(fix=False):
    entries = library_entries()
    print(f"사진 {len(entries)}장 검사 중...\n")

    # 1) 근접중복
    pairs = find_duplicates(entries)
    auto = [p for p in pairs if p[2] <= AUTOFIX_DISTANCE]
    print(f"[근접중복] {len(pairs)}쌍 (구조 <= {DUP_DISTANCE} & 색차 <= {COLOR_LIMIT})")
    print(f"   그중 자동삭제 대상(거리 <= {AUTOFIX_DISTANCE}): {len(auto)}쌍")
    for a, b, d, cd in pairs[:30]:
        mark = "삭제" if d <= AUTOFIX_DISTANCE else "확인"
        print(f"   [{mark}] 구조{d:>3} 색차{cd:.3f}  {a}  ==  {b}")
    if len(pairs) > 30:
        print(f"   ... 외 {len(pairs)-30}쌍")

    # 2) 너무 밝아 흰 글씨가 죽는 사진
    bright = []
    for fname, path, cat in entries:
        mean, std = brightness(path)
        if mean is not None and mean > BRIGHT_LIMIT:
            bright.append((fname, mean, std))
    bright.sort(key=lambda r: -r[1])
    print(f"\n[너무 밝음] {len(bright)}장 (평균밝기 > {BRIGHT_LIMIT}) "
          f"— 썸네일 배경으로 쓰면 흰 글씨가 죽는다")
    for fname, mean, std in bright[:15]:
        print(f"   밝기{mean:6.1f} 대비{std:5.1f}  {fname}")

    if fix and auto:
        # 각 중복쌍에서 뒤쪽(나중에 들어온) 파일을 지운다.
        # 지울 대상이 다른 쌍의 생존자로도 쓰이지 않게 순차 처리한다.
        # ※ 확실한 쌍(AUTOFIX_DISTANCE 이하)만 건드린다 — 애매한 걸 지우면
        #   다양성이 되레 줄어서 이 작업의 목적과 정반대가 된다.
        removed = set()
        for a, b, d, cd in auto:
            if a in removed or b in removed:
                continue
            removed.add(b)
        idx = _load_index()
        for fname in removed:
            path = os.path.join(PHOTO_DIR, fname)
            if os.path.exists(path):
                os.remove(path)
            idx.pop(fname, None)
        _save_index(idx)
        print(f"\n[정리] 근접중복 {len(removed)}장 삭제 + index 갱신")
        for f in sorted(removed):
            print(f"   삭제: {f}")

    return 0


def reindex():
    """디스크에는 있는데 index.json 에 없는 사진을 되살린다.

    index.json 은 git 이 추적하지만 사진 파일은 .gitignore 대상이라, git 명령
    (checkout/revert)으로 인덱스만 과거로 돌아가면 멀쩡한 사진이 통째로
    '없는 사진'이 된다 — category_pool 이 index 를 기준으로 풀을 만들기 때문.
    실제로 소싱 중단 후 복구하다가 72장이 이렇게 사라졌다(2026-08-03).

    카테고리는 파일명 접두어에서 유추한다({카테고리}_{n}_{출처}.jpg 규칙)."""
    idx = _load_index()
    known = {k for k in idx if not k.startswith("_")}
    files = sorted(f for f in os.listdir(PHOTO_DIR) if f.lower().endswith(".jpg"))
    added = 0
    for fname in files:
        if fname in known:
            continue
        cat = fname.split("_")[0]
        source = "unknown"
        for api in ("pexels", "unsplash", "pixabay"):
            if api in fname:
                source = api
        idx[fname] = {
            "카테고리": cat,
            "source_api": source,
            "license": f"{source} License" if source != "unknown" else "미상",
            "credit": "",
            "attribution_required": False,
            "처리": "정사각 1400px + 시리즈 톤 + 비네트",
            "검수": "reindex 로 복구 — 원본 메타 유실(파일명에서 카테고리 유추)",
        }
        added += 1
    if added:
        _save_index(idx)
    print(f"[reindex] {added}장을 index.json 에 복구 (총 {len(files)}장)")
    return 0


def main():
    _force_utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["audit", "reindex"])
    ap.add_argument("--fix", action="store_true", help="근접중복을 실제로 삭제한다")
    args = ap.parse_args()
    if args.command == "reindex":
        return reindex()
    return audit(fix=args.fix)


if __name__ == "__main__":
    sys.exit(main())
