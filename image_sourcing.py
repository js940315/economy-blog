# -*- coding: utf-8 -*-
"""
save_money_119 카드뉴스 - 향상된 이미지 소싱 헬퍼 (2026-08-01)

기존 onepage_cardnews_template.download_best_image 를 확장한 모듈.
"소재로 인물 특정 -> 여러 매체에서 후보 다수 수집 -> 실제 픽셀 비교로 최고화질 채택 -> 육안 검수"
4단계 파이프라인에서, '후보 수집'과 '채택' 단계를 더 다양하고/고화질/신뢰도 높게 만들어 준다.

핵심 아이디어:
  1) 검색 썸네일이 아니라 '원본'을 받는다  -> naver_thumb_to_original(), article_hero_image()
  2) 라이선스가 깨끗한 고해상 소스를 추가한다 -> wikimedia_portrait_candidates()
  3) 후보를 5~8개로 늘려 실제 픽셀을 비교하고, 출처/해상도/용량을 리포트로 남긴다 -> pick_best_image()

주의:
  - 실존 인물 사진을 AI 업스케일링으로 보정하지 않는다 (이 모듈은 '고르기'만 하고 절대 확대·보정하지 않음).
  - 발행 전 반드시 육안 매칭 검수 게이트(Read로 이미지 직접 확인)를 통과시킨다. 이 모듈은 그 게이트를 대체하지 않는다.
  - urllib 직접 다운로드는 기존 download_best_image 와 동일한 방식(프로젝트에서 이미 검증된 경로)이다.
"""
import io
import json
import os
import re
import urllib.parse
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (compatible; savemoney119-cardnews/1.0)"}

# 후보를 모을 때의 '출처 우선순위' (숫자가 작을수록 신뢰/화질 우선). 리포트 정렬·가점에 사용.
SOURCE_TIERS = [
    # tier 1: 공식 1차 출처 (정부/기업 뉴스룸, 퍼블릭도메인 정부 사이트) - 원본 고해상, 워터마크 없음, 라이선스 안전
    (1, ["korea.kr", "president.go.kr", "moef.go.kr", "molit.go.kr", "krx.co.kr",
         "news.samsung.com", "samsung.com", "skhynix.com", "hyundai.com", "lge.co.kr",
         "nvidia.com", "tesla.com", "whitehouse.gov", "go.kr"]),
    # tier 2: 통신사 원본 (신뢰도 최상위, 원본 해상도 확보 가능)
    (2, ["yna.co.kr", "yonhapnews", "news1.kr", "newsis.com", "imgnews.naver.net"]),
    # tier 3: 라이선스가 명확한 아카이브 (CC/PD, 고해상)
    (3, ["upload.wikimedia.org", "commons.wikimedia.org", "kogl.or.kr", "gongu.copyright.or.kr"]),
    # tier 4: 종합 일간지/기타 매체 (그 외 전부)
]


def source_tier(url):
    host = urllib.parse.urlparse(url).netloc.lower()
    for tier, hosts in SOURCE_TIERS:
        if any(h in host or h in url for h in hosts):
            return tier
    return 4


def _get(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=timeout).read()


def fetch_image(url, referer=None, timeout=25, tries=2):
    """이미지 바이너리를 견고하게 받아온다. 뉴스 CDN의 hotlink 차단(403) 대비로
    'UA만' -> 'UA+Referer(자동: 해당 호스트 루트)' 순으로 재시도한다.
    ※ 이미지/로고 같은 '바이너리 자산'은 반드시 이 방식(urllib)으로 받는다.
      WebFetch 계열 도구는 페이지 '텍스트'용이라 이미지 바이트를 못 준다 (예가 실패하던 흔한 원인)."""
    from urllib.parse import urlparse
    header_variants = [dict(UA)]
    if referer:
        header_variants.append({**UA, "Referer": referer})
    else:
        p = urlparse(url)
        header_variants.append({**UA, "Referer": f"{p.scheme}://{p.netloc}/"})
    last = None
    for h in header_variants:
        for _ in range(tries):
            try:
                req = urllib.request.Request(url, headers=h)
                return urllib.request.urlopen(req, timeout=timeout).read()
            except Exception as e:
                last = e
    raise last


# ---------- 1) 썸네일 -> 원본 정규화 ----------

def naver_thumb_to_original(url):
    """네이버 검색 이미지 결과는 리사이즈 프록시(search.pstatic.net)나 ?type=w800 축소본인 경우가 많다.
    실제 원본 URL로 되돌린다."""
    # search.pstatic.net/sunny?...&src=<real> 형태 -> 내부 src 추출
    if "pstatic.net" in url and "src=" in url:
        qs = urllib.parse.urlparse(url).query
        params = urllib.parse.parse_qs(qs)
        if "src" in params:
            url = urllib.parse.unquote(params["src"][0])
    # 뒤에 붙은 리사이즈 파라미터 제거 (?type=w800, ?type=nf220 등)
    url = re.sub(r"[?&]type=[^&]*$", "", url)
    return url


# ---------- 2) 기사 페이지에서 대표(원본) 이미지 뽑기 ----------

def article_hero_image(article_url, timeout=20):
    """뉴스 기사 URL에서 og:image / twitter:image(대개 원본 대표사진)를 추출한다.
    검색 썸네일보다 큰 원본을 얻는 가장 쉬운 방법."""
    try:
        html = _get(article_url, timeout).decode("utf-8", "ignore")
    except Exception:
        return None
    patterns = [
        r'property=["\']og:image(?::url)?["\']\s+content=["\']([^"\']+)["\']',
        r'content=["\']([^"\']+)["\']\s+property=["\']og:image["\']',
        r'name=["\']twitter:image["\']\s+content=["\']([^"\']+)["\']',
    ]
    for pat in patterns:
        m = re.search(pat, html)
        if m:
            return m.group(1)
    return None


# ---------- 3) 라이선스 안전 고해상 소스: Wikimedia Commons ----------

def wikimedia_portrait_candidates(query, limit=6, min_width=900, thumb_width=2000, timeout=20):
    """Wikimedia Commons에서 인물/주제 이미지를 검색해 원본(또는 지정폭 썸네일) URL 목록을 돌려준다.
    정치인/글로벌 CEO의 공식 초상이 CC/PD 라이선스로 고해상 등록돼 있는 경우가 많다.
    (재게시 라이선스가 상대적으로 안전 — 단 파일별 라이선스/저작자 표기 조건은 최종 확인 필요.)"""
    api = "https://commons.wikimedia.org/w/api.php"
    params = {
        "action": "query", "format": "json",
        "generator": "search",
        "gsrsearch": f"{query} filetype:bitmap",
        "gsrnamespace": 6, "gsrlimit": limit,
        "prop": "imageinfo",
        "iiprop": "url|size|extmetadata",
        "iiurlwidth": thumb_width,
    }
    url = api + "?" + urllib.parse.urlencode(params)
    try:
        data = json.loads(_get(url, timeout).decode())
    except Exception:
        return []
    out = []
    pages = data.get("query", {}).get("pages", {})
    for _pid, page in pages.items():
        for ii in page.get("imageinfo", []):
            w = ii.get("width", 0)
            if w < min_width:
                continue
            meta = ii.get("extmetadata", {}) or {}
            license_short = (meta.get("LicenseShortName", {}) or {}).get("value", "")
            out.append({
                "url": ii.get("url"),                 # 원본
                "thumb": ii.get("thumburl"),          # 지정폭 썸네일(카드용으로 충분)
                "width": w, "height": ii.get("height", 0),
                "license": license_short,
                "title": page.get("title", ""),
            })
    # 큰 순으로
    out.sort(key=lambda r: r["width"] * r["height"], reverse=True)
    return out


# ---------- 4) 후보 다운로드 + 실제 픽셀 비교 + 리포트 ----------

def pick_best_image(urls, tmp_dir, min_side=1200, prefix="cand", normalize=True):
    """후보 URL들을 실제로 내려받아 픽셀 크기를 비교하고, 출처 tier와 함께 리포트를 남긴다.

    반환: (best, report)
      best   = {"path","url","w","h","min_side","bytes","host","tier","meets_min"}  (다운로드 실패 전부면 None)
      report = 후보별 결과 리스트 (성공/실패 모두 기록)

    선택 규칙:
      - 기본은 '실제 짧은 변이 min_side 이상'인 후보들 중 '면적이 가장 큰 것'.
      - min_side를 만족하는 후보가 하나도 없으면, 그 중 가장 큰 것을 쓰되 meets_min=False로 경고.
      - AI 업스케일링/보정은 하지 않는다 (원본을 그대로 채택).
    """
    os.makedirs(tmp_dir, exist_ok=True)
    report = []
    seen = set()
    downloaded = []
    for i, raw in enumerate(urls):
        u = naver_thumb_to_original(raw) if normalize else raw
        if not u or u in seen:
            continue
        seen.add(u)
        try:
            data = _get(u, 25)
            im = Image.open(io.BytesIO(data))
            w, h = im.size
            ext = "png" if (im.format == "PNG") else "jpg"
            path = os.path.join(tmp_dir, f"{prefix}_{i}.{ext}")
            with open(path, "wb") as f:
                f.write(data)
            rec = {
                "path": path, "url": u, "w": w, "h": h, "min_side": min(w, h),
                "bytes": len(data), "host": urllib.parse.urlparse(u).netloc,
                "tier": source_tier(u),
            }
            downloaded.append(rec)
            report.append(rec)
        except Exception as e:
            report.append({"url": u, "error": str(e), "tier": source_tier(u)})

    if not downloaded:
        return None, report

    qualified = [r for r in downloaded if r["min_side"] >= min_side]
    pool = qualified if qualified else downloaded
    # 화질(면적) 우선, 동률이면 tier(작을수록 신뢰) 우선
    best = sorted(pool, key=lambda r: (r["w"] * r["h"], -r["tier"]), reverse=True)[0]
    best["meets_min"] = best["min_side"] >= min_side
    return best, report


# ---------- 5) 기업 로고 소싱 (삼성/SK/테슬라 등) ----------

def commons_file_candidates(query, width=1200, limit=8, timeout=20):
    """Wikimedia Commons 파일 검색. 각 파일의 원본 크기 + '지정폭 렌더 URL'(thumburl)을 준다.
    핵심: SVG 로고도 thumburl은 지정폭 PNG로 렌더돼 내려온다 → 별도 SVG 변환 불필요."""
    api = "https://commons.wikimedia.org/w/api.php"
    params = {
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": query, "gsrnamespace": 6, "gsrlimit": limit,
        "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata",
        "iiurlwidth": width,
    }
    try:
        data = json.loads(_get(api + "?" + urllib.parse.urlencode(params), timeout).decode())
    except Exception:
        return []
    out = []
    for _pid, page in data.get("query", {}).get("pages", {}).items():
        for ii in page.get("imageinfo", []):
            meta = ii.get("extmetadata", {}) or {}
            out.append({
                "title": page.get("title", ""),
                "mime": ii.get("mime"),
                "src_w": ii.get("width"), "src_h": ii.get("height"),
                "render_url": ii.get("thumburl") or ii.get("url"),  # 지정폭 PNG 렌더
                "orig_url": ii.get("url"),
                "license": (meta.get("LicenseShortName", {}) or {}).get("value", ""),
            })
    return out


def logo_candidates(company, out_dir, width=1200, limit=8, prefix="logo"):
    """기업 로고 후보들을 실제로 렌더/다운로드해서 파일로 저장하고 리포트를 돌려준다.
    ※ Commons 검색은 자회사/변형 로고(예: 'SK magic', 'Galaxy A8')를 섞어주므로
      반드시 Read로 육안 확인 후 채택할 것. 이 함수는 '후보 모으기'까지만 한다.

    반환: report = [{"path","title","mime","w","h","render_url","license"} 또는 {"error",...}]
    (뉴스 사진과 달리 로고는 가로로 긴 워드마크가 많아 min_side 기준을 적용하지 않는다.)"""
    import time
    os.makedirs(out_dir, exist_ok=True)
    cands = commons_file_candidates(f"{company} logo", width=width, limit=limit)
    report = []
    for i, c in enumerate(cands):
        url = c["render_url"]
        if not url:
            continue
        try:
            time.sleep(0.6)  # upload.wikimedia.org 연속 요청 시 HTTP 429 방지 (throttle)
            data = fetch_image(url)
            ext = "png"
            path = os.path.join(out_dir, f"{prefix}_{i}.{ext}")
            with open(path, "wb") as f:
                f.write(data)
            w = h = None
            if Image is not None:
                try:
                    im = Image.open(io.BytesIO(data)); w, h = im.size
                except Exception:
                    pass
            report.append({"path": path, "title": c["title"], "mime": c["mime"],
                           "w": w, "h": h, "render_url": url, "license": c["license"]})
        except Exception as e:
            report.append({"error": str(e), "title": c["title"], "render_url": url})
    return report


# 후보를 못 찾을 때의 최후 폴백 URL 빌더 (참고용 — 화질/색상 한계 있음)
def logo_fallback_urls(domain, brand_slug=None):
    """Commons에서 못 구했을 때 최후 폴백. 순서대로 시도.
      1) Simple Icons: 단색 브랜드 SVG (색이 단색이라 카드용으로는 제한적)
      2) Google favicon: 최대 256px PNG (작음, 정말 최후일 때만)
    ※ Clearbit(logo.clearbit.com)는 이 샌드박스에서 DNS 차단이라 제외했다."""
    urls = []
    if brand_slug:
        urls.append(f"https://cdn.simpleicons.org/{brand_slug}")           # 단색 svg
    urls.append(f"https://www.google.com/s2/favicons?domain={domain}&sz=256")  # 작은 png
    return urls


try:
    from PIL import Image  # noqa: E402  (하단 import: 픽셀 비교에만 필요)
except Exception:  # pragma: no cover
    Image = None


if __name__ == "__main__":
    # 간단 self-test (네트워크 필요)
    print("[test] Wikimedia: Jensen Huang")
    for c in wikimedia_portrait_candidates("Jensen Huang", limit=4)[:4]:
        print("  ", c["width"], "x", c["height"], c["license"], c["url"])
    print("[test] naver thumb normalize")
    t = "https://search.pstatic.net/common/?type=b150&src=http%3A%2F%2Fimgnews.naver.net%2Fimage%2F001%2Fx.jpg"
    print("  ->", naver_thumb_to_original(t))
