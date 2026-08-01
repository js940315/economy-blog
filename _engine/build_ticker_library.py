# -*- coding: utf-8 -*-
"""종목별 로고 라이브러리를 만든다 (국내주식 / 해외주식 / 가상자산).

주식·코인 기사는 '그 종목의 얼굴'이 있어야 홈판에서 인식된다.
일반 항만·아파트 사진으로는 삼성전자 기사인지 알 수 없다.

    python build_ticker_library.py              # 전체
    python build_ticker_library.py --group 국내주식
    python build_ticker_library.py --only 삼성전자

Commons 검색은 자회사·제품 로고(Galaxy A8, SK magic 등)를 잔뜩 섞어주므로
제목 점수로 1차 걸러낸 뒤, 컨택트시트로 눈 확인하는 2단계로 간다.
"""

import argparse
import json
import os
import re
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from image_sourcing import commons_file_candidates, fetch_image

DIR = os.path.join("assets", "tickers")
INDEX = os.path.join(DIR, "index.json")

# 종목명 -> (Commons 검색어, 파일 접두어)
TICKERS = {
    "국내주식": {
        "삼성전자": ("Samsung Electronics logo", "samsung"),
        "SK하이닉스": ("SK Hynix logo", "skhynix"),
        "현대자동차": ("Hyundai Motor Company logo", "hyundai"),
        "기아": ("Kia logo", "kia"),
        "LG에너지솔루션": ("LG Corp logo wordmark", "lgensol"),
        "네이버": ("Naver Corporation logo", "naver"),
        "카카오": ("Kakao Corp logo", "kakao"),
        "포스코": ("POSCO Holdings company logo", "posco"),
        "셀트리온": ("Celltrion logo", "celltrion"),
        "KB금융": ("KB Financial Group logo", "kbfg"),
    },
    "해외주식": {
        "애플": ("Apple Inc logo", "apple"),
        "엔비디아": ("Nvidia logo", "nvidia"),
        "테슬라": ("Tesla Motors logo", "tesla"),
        "마이크로소프트": ("Microsoft Corporation wordmark", "microsoft"),
        "구글": ("Google logo", "google"),
        "아마존": ("Amazon.com Inc logo", "amazon"),
        "메타": ("Meta Platforms logo", "meta"),
        "AMD": ("Advanced Micro Devices company logo", "amd"),
        "인텔": ("Intel Corporation company logo 2020", "intel"),
        "TSMC": ("TSMC logo", "tsmc"),
        "브로드컴": ("Broadcom logo", "broadcom"),
        "넷플릭스": ("Netflix logo", "netflix"),
    },
    "가상자산": {
        "비트코인": ("Bitcoin logo", "bitcoin"),
        "이더리움": ("Ethereum logo", "ethereum"),
        "리플": ("XRP cryptocurrency symbol", "xrp"),
        "솔라나": ("Solana blockchain logo", "solana"),
        "도지코인": ("Dogecoin logo", "dogecoin"),
    },
}

# 제목에 이런 단어가 있으면 제품·자회사 로고일 가능성이 높다
JUNK_WORDS = ["galaxy", "iphone", "ipad", "macbook", "watch", "store", "magic",
              "telecom", "innotek", "display logo of", "font", "wordmark of the",
              "series", "model ", "edition", "cardboard", "pay", "cloud", "music",
              "tv ", "plus", "mini", "pro ", "air ", "chip", "card"]


def score(title, company_query, mime):
    """후보 제목이 '그 회사의 대표 로고'일 가능성 점수."""
    t = (title or "").lower().replace("file:", "")
    words = [w for w in re.split(r"[^a-z0-9]+", company_query.lower())
             if w and w != "logo"]
    s = 0
    if all(w in t for w in words):
        s += 4                      # 회사명 전체 포함
    elif words and words[0] in t:
        s += 1
    if "logo" in t:
        s += 3
    if (mime or "").endswith("svg+xml"):
        s += 2                      # 공식 로고는 대개 벡터
    for j in JUNK_WORDS:
        if j in t:
            s -= 4
            break
    # 파일명이 짧을수록 대표 로고일 확률이 높다 (긴 건 대개 변형·행사용)
    if len(t) < 34:
        s += 1
    return s


def fetch_one(name, query, prefix, keep=2, width=1200):
    cands = commons_file_candidates(query, width=width, limit=10)
    ranked = sorted(cands, key=lambda c: -score(c.get("title"), query, c.get("mime")))
    out = []
    for c in ranked:
        if len(out) >= keep:
            break
        if score(c.get("title"), query, c.get("mime")) <= 0:
            continue
        url = c.get("render_url")
        if not url:
            continue
        path = os.path.join(DIR, f"{prefix}_{len(out)}.png")
        try:
            if os.path.exists(path):      # 이어받기: 이미 있으면 재다운로드 안 함
                out.append({
                    "file": os.path.basename(path), "title": c["title"],
                    "license": c["license"],
                    "score": score(c.get("title"), query, c.get("mime")),
                })
                continue
            data = None
            for attempt in range(4):      # 429는 간격을 늘려가며 재시도
                try:
                    time.sleep(1.0 + attempt * 1.5)
                    data = fetch_image(url)
                    break
                except Exception as e:
                    if "429" not in str(e) or attempt == 3:
                        raise
            with open(path, "wb") as f:
                f.write(data)
            out.append({
                "file": os.path.basename(path),
                "title": c["title"],
                "license": c["license"],
                "score": score(c.get("title"), query, c.get("mime")),
            })
        except Exception as e:
            print(f"     실패 {c['title'][:34]}: {str(e)[:34]}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", help="국내주식 / 해외주식 / 가상자산")
    ap.add_argument("--only", help="종목명 하나만")
    ap.add_argument("--keep", type=int, default=2, help="종목당 후보 수")
    args = ap.parse_args()

    os.makedirs(DIR, exist_ok=True)
    idx = {}
    if os.path.exists(INDEX):
        with open(INDEX, encoding="utf-8") as f:
            idx = json.load(f)

    groups = {args.group: TICKERS[args.group]} if args.group else TICKERS
    if args.group and args.group not in TICKERS:
        print("그룹은 국내주식 / 해외주식 / 가상자산 중 하나입니다.")
        return 1

    total = 0
    for gname, items in groups.items():
        print(f"\n=== {gname}")
        for name, (query, prefix) in items.items():
            if args.only and args.only != name:
                continue
            got = fetch_one(name, query, prefix, keep=args.keep)
            if not got:
                print(f"   {name:<14} 실패 - 후보 없음")
                continue
            idx[name] = {
                "그룹": gname,
                "검색어": query,
                "후보": got,
                "검수": "미확인 — 컨택트시트로 눈 확인 필요",
            }
            print(f"   {name:<14} {len(got)}장  " +
                  ", ".join(f"{g['file']}[{g['license']}]" for g in got))
            total += len(got)

    idx["_주의"] = ("로고는 상표다. 해당 종목을 실제로 다루는 기사에만 쓰고, "
                    "그 기업이 블로그를 후원·보증하는 것처럼 보이게 쓰지 않는다.")
    idx["_추가방법"] = "python build_ticker_library.py --only 종목명"
    with open(INDEX, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=2)

    print(f"\n총 {total}장 -> {DIR}/")
    print("컨택트시트로 확인하고 엉뚱한 건 지우세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
