# -*- coding: utf-8 -*-
"""카테고리별 사진 풀에서 '오늘·이 순번'에 어떤 사진을 쓸지 결정론적으로 고른다.

목적: 같은 카테고리 사진이 며칠 연속 반복돼 보이는 걸 막는다(유사문서·식상함
리스크). Date.now()/random()을 못 쓰는 클라우드 빌드 환경이라, 대신
(카테고리, 날짜, 그날의 순번)을 해시해 항상 같은 입력이면 같은 결과가 나오는
'결정론적 순환'을 쓴다 — 같은 기사를 다시 빌드해도 사진이 안 바뀌면서도,
날짜·순번이 다르면 자연히 다른 사진이 나온다.

거기에 '최근 N장은 최대한 피한다'는 최소한의 반복회피 규칙을 얹어서, 우연히
어제 쓴 사진이 오늘 또 뽑히는 걸 한 번 더 막는다.

사용법 (build_posts.py에서):
    from photo_library import pick_photo, record_usage, variation_seed
    fname = pick_photo("부동산", date_tag, seq)      # -> "부동산_2_0.jpg"
    record_usage("부동산", fname, date_tag, seq)      # 실제로 그 이미지를 만든 뒤에 호출
    var = variation_seed(fname, date_tag, seq)        # 크롭 정렬 + 톤 보정 파라미터
"""

import hashlib
import json
import os

PHOTO_DIR = os.path.join("assets", "photos")
INDEX_PATH = os.path.join(PHOTO_DIR, "index.json")
USAGE_PATH = os.path.join("state", "photo_usage.json")

# 카테고리 안에서 '최근 이만큼'은 재사용을 피한다. 풀 크기에 비례해서 정한다.
#
# 예전엔 3 고정이었다. 풀이 20장이어도 최근 3장만 피하니, 남은 17장 중에서
# 해시로 아무거나 뽑혀 같은 사진이 며칠 간격으로 계속 재등장했다
# (사용자: "같은 사진 중복 최악"). 풀의 일정 비율을 통째로 막아야
# 한 바퀴를 거의 다 돌고 나서 다시 나온다.
RECENT_RATIO = 0.7     # 풀의 70%를 최근 사용분으로 간주해 배제
RECENT_WINDOW_MIN = 3  # 풀이 아주 작을 때의 하한
HISTORY_MAX = 60       # usage 로그가 무한히 커지지 않게 카테고리당 이만큼만 보관


def recent_window(pool_size):
    """풀 크기에 맞는 '최근 배제' 개수. 최소 1장은 항상 남긴다."""
    if pool_size <= 1:
        return 0
    window = max(RECENT_WINDOW_MIN, int(pool_size * RECENT_RATIO))
    return min(window, pool_size - 1)   # 후보가 0이 되면 안 된다

ALIGNS = ["xMinYMin", "xMidYMin", "xMaxYMin",
          "xMinYMid", "xMidYMid", "xMaxYMid",
          "xMinYMax", "xMidYMax", "xMaxYMax"]


def _load_json(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def _save_json(path, data):
    """원자적 저장 — 임시파일에 다 쓴 뒤 os.replace로 교체한다.

    쓰는 도중 시스템이 비정상 종료(블루스크린 등)해도 원본이 반쯤 쓰이거나
    0바이트로 손상되지 않는다(교체는 원자적). photo_usage.json이 NUL로 깨져
    엔진이 크래시했던 사고의 재발 방지."""
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _load_json_safe(path, default):
    """빈/손상 JSON을 만나도 크래시 대신 default로 복구한다(불안정 환경 대비)."""
    try:
        return _load_json(path, default)
    except (ValueError, OSError):
        return default


def _seed(*parts):
    h = hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()
    return int(h[:12], 16)


def category_pool(category):
    """assets/photos/index.json에서 해당 카테고리로 태그된 파일명 목록.

    두 가지 표기를 다 인식한다:
      1) index.json에 "카테고리": "부동산" 필드가 명시된 경우 (신규 방식)
      2) 파일명이 "부동산_"로 시작하는 경우 (기존 관행 — 필드가 없어도 잡아준다)
    """
    idx = _load_json_safe(INDEX_PATH, {})
    pool = []
    for fn, meta in idx.items():
        if fn.startswith("_") or not isinstance(meta, dict):
            continue
        cat = meta.get("카테고리")
        if cat == category or (cat is None and fn.startswith(category + "_")):
            # index.json 에는 있는데 실물 파일이 없는 항목을 걸러낸다.
            # 중복 정리(photo_quality audit --fix)로 파일만 지워졌거나 git
            # 작업으로 인덱스와 디스크가 어긋나면, 여기서 안 막을 경우
            # 빌드가 FileNotFoundError 로 통째로 죽는다(실측 2026-08-04).
            if os.path.exists(os.path.join(PHOTO_DIR, fn)):
                pool.append(fn)
    return sorted(pool)


def pick_photo(category, date_tag, seq, exclude=None):
    """카테고리 풀에서 (날짜, 순번) 기반으로 결정론적으로 하나를 고른다.

    exclude: 같은 포스트 안에서 이미 쓴 파일명 집합(예: 썸네일에 쓴 사진은
    실물 슬롯에서 제외) — 한 포스트 안에서 사진이 겹치지 않게 하는 용도.
    반환값이 None이면 그 카테고리에 사진이 아직 없다는 뜻 — 호출부가
    카드로 대체하거나 다른 카테고리로 폴백해야 한다."""
    pool = category_pool(category)
    if exclude:
        pool = [p for p in pool if p not in exclude]
    if not pool:
        return None

    usage = _load_json_safe(USAGE_PATH, {})
    window = recent_window(len(pool))
    recent = set(usage.get(category, [])[-window:]) if window else set()
    candidates = [p for p in pool if p not in recent] or pool

    idx = _seed(category, date_tag, seq) % len(candidates)
    return candidates[idx]


def record_usage(category, filename, date_tag, seq):
    """실제로 이미지를 만든 뒤 호출 — 다음 순환 판단의 '최근 사용' 근거가 된다."""
    if not filename:
        return
    usage = _load_json_safe(USAGE_PATH, {})
    lst = usage.setdefault(category, [])
    lst.append(filename)
    usage[category] = lst[-HISTORY_MAX:]
    _save_json(USAGE_PATH, usage)


def variation_seed(photo_path, date_tag, seq):
    """같은 원본 사진이라도 (날짜, 순번)마다 살짝 다르게 보이도록 크롭
    정렬(9방향)과 톤(채도/색조/밝기) 파라미터를 결정론적으로 뽑는다.

    범위를 좁게 잡아서(채도 0.86~1.00, 색조 ±10도, 밝기 0.96~1.04) 사진 자체가
    이상해 보이지 않으면서도 '매번 같은 필터'라는 티는 안 나게 했다."""
    s = _seed(photo_path, date_tag, seq)
    align = ALIGNS[s % 9]
    s //= 9
    sat = round(0.86 + (s % 15) / 100.0, 2)
    s //= 15
    hue = ((s % 11) - 5) * 2
    s //= 11
    bright = round(0.96 + (s % 9) / 100.0, 2)
    return {"align": align, "saturate": sat, "hue": hue, "bright": bright}
