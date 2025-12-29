import requests
import csv
import json
import re
import time
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from urllib.parse import urljoin
from urllib3.util import create_urllib3_context
from fake_useragent import UserAgent
from bs4 import BeautifulSoup
from dotenv import load_dotenv
load_dotenv()

# MongoDB(사용 시 설치 필요)
# pip install pymongo
try:
    from pymongo import MongoClient, UpdateOne
except Exception:
    MongoClient = None
    UpdateOne = None


# =========================
# ✅ 설정(여기만 바꾸면 전체 반영)
# =========================
@dataclass
class CrawlConfig:
    # 기간/속도
    days_back: int = 120
    page_size: int = 15
    timeout: int = 10
    sleep_sec: float = 0.7
    dedup_global: bool = True

    # ✅ 페이징(기간이 길면 1페이지만으론 부족할 수 있어 추가)
    max_pages: int = 20  # 필요 시 조정

    # 엔드포인트
    base_url: str = "https://ars.yna.co.kr/api/v2/search.basic"
    results_key: str = "YIB_KR_A"

    # 필터(웹 URL ctype/divCode ↔ API 파라미터 추정 매핑)
    # - 결과가 안 나오면 div_code="all"로 바꿔 테스트 권장
    cattr: str = "A"
    div_code: str = "01,02,05,11"
    scope: str = "all"
    sort: str = "date"
    channel: str = "basic_kr"

    # 저장
    output_prefix: str = "yna_news"

    # 디버그
    debug_total: bool = True
    debug_top_keys: bool = False

    # 추가 파라미터 주입(필요 시)
    extra_params: dict = field(default_factory=dict)

    # ✅ 본문/이미지 크롤링
    fetch_content: bool = True
    fetch_image: bool = True
    content_timeout: int = 12
    content_sleep_sec: float = 0.35
    content_max_chars: int = 30000
    content_retries: int = 2
    content_retry_backoff: float = 1.3

    # ✅ MongoDB 업로드
    upload_to_mongo: bool = True
    mongo_uri: str = os.getenv("MONGO_URI", "")
    mongo_db: str = os.getenv("MONGO_DB", "news")
    mongo_collection: str = os.getenv("MONGO_COL", "yna_news")
    mongo_upsert: bool = True
    mongo_batch_size: int = 500

    # ✅ search_groups를 CSV에서 로드하고 싶을 때(옵션)
    # - CSV 컬럼명에 맞춰 아래 매핑을 수정
    load_groups_from_csv: bool = False
    groups_csv_path: str = "Chairman_export.csv"
    groups_csv_group_col: str = "Group"     # 예: 기업집단명
    groups_csv_company_col: str = "Company" # 예: 회사키워드(기업명)
    groups_csv_person_col: str = "Person"   # 예: 총수명


CONFIG = CrawlConfig(
    days_back=120,
    div_code="01,02,05,11",
    cattr="A",
    fetch_content=True,
    fetch_image=True,
    upload_to_mongo=True,
    debug_total=True,
    max_pages=20,
)


# =========================
# SSL 이슈 해결 어댑터
# =========================
class LegacySSLAdapter(requests.adapters.HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = create_urllib3_context()
        ctx.load_default_certs()
        ctx.options |= 0x4  # ssl.OP_LEGACY_SERVER_CONNECT
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)


# =========================
# UA/헤더
# =========================
def safe_user_agent():
    try:
        ua = UserAgent()
        return ua.random
    except Exception:
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )

def headers_for_api():
    return {
        "User-Agent": safe_user_agent(),
        "Referer": "https://www.yna.co.kr/",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
    }

def headers_for_html():
    return {
        "User-Agent": safe_user_agent(),
        "Referer": "https://www.yna.co.kr/",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Connection": "keep-alive",
    }


# =========================
# 유틸
# =========================
def get_since_dt(days_back: int) -> datetime:
    return datetime.now() - timedelta(days=days_back)

def build_queries_company_plus_person(company_kw: str, person_kw: str):
    """요구사항: '기업 + 총수'만 탐색"""
    company_kw = (company_kw or "").strip()
    person_kw = (person_kw or "").strip()
    if company_kw and person_kw:
        return [f"{company_kw} {person_kw}"]
    return []

def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    return "\n".join(lines).strip()


# =========================
# ✅ 본문 정리(기자/구독/이전/다음/이미지확대/이메일/okjebo/관련뉴스/저작권 제거)
# =========================
_UI_TOKENS = ("구독", "구독중", "이전", "다음", "이미지 확대", "이미지확대")
_UI_LINE_RE = re.compile(r"^\s*(구독|구독중|이전|다음|이미지\s*확대|이미지확대)\s*$")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@yna\.co\.kr\b", re.IGNORECASE)
_OKJEBO_PHRASE_RE = re.compile(r"제보는\s*카카오톡\s*okjebo", re.IGNORECASE)
_COPYRIGHT_RE = re.compile(
    r"(저작권자\s*\(c\)\s*연합뉴스|무단\s*전재|재배포\s*금지|연합뉴스\s*무단|ⓒ\s*연합뉴스)",
    re.IGNORECASE,
)
_RELATED_HEADER_RE = re.compile(r"^\s*관련\s*뉴스\s*$|^\s*관련뉴스\s*$|^\s*관련\s*기사\s*$|^\s*관련기사\s*$")

def pre_split_glued_ui_text(text: str) -> str:
    if not text:
        return ""
    # 관련뉴스 헤더 분리
    text = re.sub(r"(관련\s*뉴스|관련뉴스|관련\s*기사|관련기사)", r"\n\1\n", text)
    # 이전/다음 붙은 것 분리
    text = re.sub(r"(이전)\s*(다음)", r"\1\n\2", text)
    text = re.sub(r"(다음)(?=[가-힣])", r"\1\n", text)
    text = re.sub(r"(다음)(?=[A-Za-z0-9._%+-]+@)", r"\1\n", text)
    text = re.sub(r"(이미지\s*확대)(?=[가-힣])", r"\1\n", text)
    text = re.sub(r"(이미지확대)(?=[가-힣])", r"\1\n", text)
    text = re.sub(r"(다음)\s*(<저작권자)", r"\1\n\2", text)
    return text

def remove_reporter_ui_blocks_anywhere(lines: list[str]) -> list[str]:
    out = []
    i = 0
    n = len(lines)

    def is_name_like(s: str) -> bool:
        s = s.strip()
        if not (2 <= len(s) <= 10):
            return False
        return bool(re.fullmatch(r"[가-힣·\s]+", s))

    while i < n:
        cur = lines[i].strip()

        # "홍길동" + "기자" 패턴
        if i + 1 < n and lines[i + 1].strip() == "기자" and is_name_like(cur):
            i += 2
            while i < n:
                t = lines[i].strip()
                if _UI_LINE_RE.match(t):
                    i += 1
                    continue
                if any(tok in t for tok in _UI_TOKENS) and len(t) <= 24:
                    i += 1
                    continue
                break
            continue

        # "홍길동 기자" 한 줄 패턴
        if re.fullmatch(r"[가-힣·\s]{2,10}\s*기자", cur):
            i += 1
            while i < n and _UI_LINE_RE.match(lines[i].strip()):
                i += 1
            continue

        out.append(lines[i])
        i += 1

    return out

def is_headline_like(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if len(s) < 8 or len(s) > 140:
        return False
    if _UI_LINE_RE.match(s) or s == "기자":
        return False
    if _OKJEBO_PHRASE_RE.search(s) or _COPYRIGHT_RE.search(s):
        return False
    if any(ch in s for ch in ["…", "\"", "“", "”", "(", ")", "·", "—", "-"]):
        return True
    if re.search(r"\d", s):
        return True
    if s.endswith(".") or s.endswith("다.") or s.endswith("다"):
        return False
    return False

def remove_related_news_blocks(lines: list[str]) -> list[str]:
    out = []
    i = 0
    n = len(lines)

    while i < n:
        ln = lines[i].strip()
        if _RELATED_HEADER_RE.match(ln):
            i += 1
            # 관련뉴스 아래 줄들(헤드라인처럼 보이는 줄) 제거
            while i < n and is_headline_like(lines[i]):
                i += 1
            continue

        out.append(lines[i])
        i += 1

    return out

def clean_yna_content(text: str) -> str:
    if not text:
        return ""

    text = pre_split_glued_ui_text(text)
    text = _OKJEBO_PHRASE_RE.sub("", text)
    text = _EMAIL_RE.sub("", text)
    text = re.sub(r"\(\s*\)", "", text)

    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]

    lines = [ln for ln in lines if not _UI_LINE_RE.match(ln)]
    lines = remove_related_news_blocks(lines)
    lines = remove_reporter_ui_blocks_anywhere(lines)
    lines = [ln for ln in lines if not _OKJEBO_PHRASE_RE.search(ln)]

    # 저작권 라인부터 컷
    cut_idx = None
    for idx, ln in enumerate(lines):
        if _COPYRIGHT_RE.search(ln):
            cut_idx = idx
            break
        if ln.startswith("<저작권자") or ln.startswith("＜저작권자"):
            cut_idx = idx
            break
    if cut_idx is not None:
        lines = lines[:cut_idx]

    cleaned = "\n".join(lines).strip()
    cleaned = re.sub(r"[ \t]+", " ", cleaned).strip()
    return cleaned


# =========================
# ✅ 이미지 URL 정리(상대경로/특수 케이스 보정)
# =========================
_IMG_HOST_PATH_RE = re.compile(r"^/img\d+\.yna\.co\.kr/")

def absolutize_img_url(src: str, base_url: str) -> str:
    if not src:
        return ""
    src = src.strip()
    if not src or src.startswith("data:"):
        return ""

    if src.startswith("http://") or src.startswith("https://"):
        return src
    if src.startswith("//"):
        return "https:" + src
    # ✅ '/img5.yna.co.kr/...' 같은 케이스 → 'https://img5.yna.co.kr/...'
    if _IMG_HOST_PATH_RE.match(src):
        return "https://" + src.lstrip("/")
    # 일반 상대경로
    return urljoin(base_url, src)

def uniq_keep_order(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for x in items:
        if not x:
            continue
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


# =========================
# 목록 API 호출(페이징 지원)
# =========================
def fetch_articles_paged(session: requests.Session, config: CrawlConfig, query: str, since_dt: datetime):
    collected = []
    last_raw = None

    for page_no in range(1, config.max_pages + 1):
        params = {
            "query": query,
            "page_no": page_no,
            "page_size": config.page_size,
            "scope": config.scope,
            "sort": config.sort,
            "channel": config.channel,
            "div_code": config.div_code,
            "cattr": config.cattr,
        }
        if config.extra_params:
            params.update(config.extra_params)

        resp = session.get(config.base_url, params=params, headers=headers_for_api(), timeout=config.timeout)
        resp.raise_for_status()
        data = resp.json()
        last_raw = data

        if config.debug_top_keys and page_no == 1:
            print("DEBUG top keys:", list(data.keys())[:10])

        if config.results_key not in data:
            break

        if config.debug_total and page_no == 1:
            total = data.get(config.results_key, {}).get("total")
            print(f"DEBUG total({query}):", total)

        results = data[config.results_key].get("result", []) or []
        if not results:
            break

        stop_paging = False
        for art in results:
            cid = art.get("CID")
            dt_str = art.get("DATETIME")
            title = art.get("TITLE") or ""

            if not cid or not dt_str:
                continue

            try:
                art_dt = datetime.strptime(dt_str, "%Y%m%d%H%M%S")
            except Exception:
                continue

            # 정렬이 최신순이므로 since_dt보다 과거가 나오면 이후 페이지는 더 과거일 확률↑ → 페이징 중단
            if art_dt < since_dt:
                stop_paging = True
                continue

            collected.append({
                "CID": cid,
                "TITLE": title.replace("<b>", "").replace("</b>", ""),
                "DATETIME": art_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "URL": f"https://www.yna.co.kr/view/{cid}",
            })

        if stop_paging:
            break

        # 마지막 페이지 감지(결과 수가 page_size보다 적으면 끝)
        if len(results) < config.page_size:
            break

        time.sleep(0.15)

    return collected, last_raw


# =========================
# ✅ 본문/이미지 추출(HTML)
# =========================
def try_extract_from_jsonld_text(soup: BeautifulSoup):
    scripts = soup.find_all("script", attrs={"type": "application/ld+json"})
    for sc in scripts:
        raw = sc.get_text(strip=True)
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except Exception:
            continue

        candidates = obj if isinstance(obj, list) else [obj]
        for it in candidates:
            if not isinstance(it, dict):
                continue
            body = it.get("articleBody") or it.get("description")
            if isinstance(body, str):
                body = clean_yna_content(normalize_text(body))
                if len(body) >= 80:
                    return body, "jsonld"
    return "", ""

def best_text_block_by_heuristic(soup: BeautifulSoup):
    best_text = ""
    best_src = ""
    best_score = 0

    for tag in soup.find_all(["article", "div", "section"], limit=4000):
        ident = " ".join(
            filter(
                None,
                [
                    tag.get("id", ""),
                    " ".join(tag.get("class", []) if tag.get("class") else []),
                ],
            )
        ).lower()

        if any(x in ident for x in ["nav", "menu", "footer", "header", "aside", "banner", "ad", "promo", "related", "share"]):
            continue

        text = normalize_text(tag.get_text("\n"))
        if len(text) < 250:
            continue

        p_cnt = len(tag.find_all("p"))
        score = len(text) + p_cnt * 120

        a_cnt = len(tag.find_all("a"))
        if a_cnt >= 25 and p_cnt == 0:
            continue

        if score > best_score:
            best_score = score
            best_text = text
            best_src = "heuristic"

    best_text = clean_yna_content(best_text)
    return best_text, best_src

def extract_yna_content(html: str):
    soup = BeautifulSoup(html, "html.parser")

    for t in soup(["script", "style", "noscript"]):
        t.decompose()

    body, src = try_extract_from_jsonld_text(soup)
    if body:
        return body, src

    selectors = [
        "#articleBodyContents",
        "#articleBody",
        "#articleWrap",
        ".story-news",
        ".article",
        ".content01",
        "article",
    ]

    best_text = ""
    best_src = ""
    for sel in selectors:
        node = soup.select_one(sel)
        if not node:
            continue
        text = clean_yna_content(normalize_text(node.get_text("\n")))
        if len(text) > len(best_text):
            best_text = text
            best_src = f"selector:{sel}"

    if best_text and len(best_text) >= 80:
        return best_text, best_src

    text2, src2 = best_text_block_by_heuristic(soup)
    if text2 and len(text2) >= 80:
        return text2, src2

    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        text3 = clean_yna_content(normalize_text(meta["content"]))
        if len(text3) >= 40:
            return text3, "meta:description"

    return "", "empty"

def extract_yna_images(html: str, article_url: str):
    """
    대표/본문 이미지 URL 수집
    우선순위:
      1) og:image
      2) twitter:image
      3) JSON-LD image
      4) figure.image-zone01 img (연합뉴스 본문 대표/본문 이미지 패턴)
      5) 본문 셀렉터 내부 img
    반환:
      (primary_url, urls_list, source)
    """
    soup = BeautifulSoup(html, "html.parser")

    urls = []
    source = "empty"

    # 1) og:image
    m = soup.find("meta", attrs={"property": "og:image"})
    if m and m.get("content"):
        u = absolutize_img_url(m["content"], article_url)
        if u:
            urls.append(u)
            source = "meta:og:image"

    # 2) twitter:image
    m = soup.find("meta", attrs={"name": "twitter:image"})
    if m and m.get("content"):
        u = absolutize_img_url(m["content"], article_url)
        if u:
            urls.append(u)
            if source == "empty":
                source = "meta:twitter:image"

    # 3) JSON-LD image
    scripts = soup.find_all("script", attrs={"type": "application/ld+json"})
    for sc in scripts:
        raw = sc.get_text(strip=True)
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except Exception:
            continue
        candidates = obj if isinstance(obj, list) else [obj]
        for it in candidates:
            if not isinstance(it, dict):
                continue
            img = it.get("image")
            img_url = ""
            if isinstance(img, str):
                img_url = img
            elif isinstance(img, list) and img:
                img_url = img[0] if isinstance(img[0], str) else ""
            elif isinstance(img, dict):
                img_url = img.get("url") or img.get("@id") or ""
            img_url = absolutize_img_url(img_url, article_url)
            if img_url:
                urls.append(img_url)
                if source == "empty":
                    source = "jsonld:image"

    # 4) figure.image-zone01 img (캡처에서 보여준 구조)
    for img_tag in soup.select("figure.image-zone01 img"):
        cand = img_tag.get("src") or img_tag.get("data-src") or img_tag.get("data-original")
        cand = absolutize_img_url(cand, article_url)
        if cand:
            urls.append(cand)
            if source == "empty":
                source = "selector:figure.image-zone01"

    # 5) 본문 내부 img 폴백
    selectors = [
        "#articleBodyContents img",
        "#articleBody img",
        "#articleWrap img",
        ".story-news img",
        ".article img",
        ".content01 img",
        "article img",
    ]
    for sel in selectors:
        for img_tag in soup.select(sel):
            cand = img_tag.get("src") or img_tag.get("data-src") or img_tag.get("data-original")
            cand = absolutize_img_url(cand, article_url)
            if cand:
                urls.append(cand)
                if source == "empty":
                    source = f"selector:{sel}"

    urls = uniq_keep_order(urls)
    primary = urls[0] if urls else ""
    return primary, urls, source

def fetch_article_page(session: requests.Session, config: CrawlConfig, url: str):
    last_err = ""
    for attempt in range(config.content_retries + 1):
        try:
            resp = session.get(url, headers=headers_for_html(), timeout=config.content_timeout)
            status = resp.status_code

            if status in (403, 429, 500, 502, 503, 504) and attempt < config.content_retries:
                time.sleep(config.content_retry_backoff ** (attempt + 1))
                continue

            resp.raise_for_status()

            if resp.encoding is None or resp.encoding.lower() == "iso-8859-1":
                resp.encoding = resp.apparent_encoding

            html = resp.text

            # ✅ 본문
            content, content_source = extract_yna_content(html)
            if config.content_max_chars and len(content) > config.content_max_chars:
                content = content[: config.content_max_chars].rstrip() + "\n...(truncated)"

            # ✅ 이미지
            image_url, image_urls, image_source = ("", [], "disabled")
            if config.fetch_image:
                image_url, image_urls, image_source = extract_yna_images(html, url)

            # content가 너무 짧으면 실패로 표시(이미지는 넣어도 됨)
            if not content or len(content.strip()) < 80:
                return {
                    "content": "",
                    "content_len": 0,
                    "content_status": f"EMPTY_HTTP_{status}",
                    "content_source": content_source,
                    "image_url": image_url,
                    "image_urls": image_urls,
                    "image_source": image_source,
                }

            return {
                "content": content,
                "content_len": len(content),
                "content_status": "OK",
                "content_source": content_source,
                "image_url": image_url,
                "image_urls": image_urls,
                "image_source": image_source,
            }

        except Exception as e:
            last_err = str(e)
            if attempt < config.content_retries:
                time.sleep(config.content_retry_backoff ** (attempt + 1))
                continue

    return {
        "content": "",
        "content_len": 0,
        "content_status": f"ERROR:{last_err[:120]}",
        "content_source": "error",
        "image_url": "",
        "image_urls": [],
        "image_source": "error",
    }


def enrich_rows_with_content_and_image(session: requests.Session, config: CrawlConfig, flat_rows: list):
    if not flat_rows:
        return
    print("\n[DETAIL] 본문/이미지 크롤링 시작...")
    for i, row in enumerate(flat_rows, 1):
        url = row.get("URL")
        if not url:
            row["CONTENT"] = ""
            row["CONTENT_LEN"] = 0
            row["CONTENT_STATUS"] = "NO_URL"
            row["CONTENT_SOURCE"] = "none"
            row["IMAGE_URL"] = ""
            row["IMAGE_URLS"] = "[]"
            row["IMAGE_SOURCE"] = "none"
            continue

        r = fetch_article_page(session, config, url)

        row["CONTENT"] = r["content"]
        row["CONTENT_LEN"] = r["content_len"]
        row["CONTENT_STATUS"] = r["content_status"]
        row["CONTENT_SOURCE"] = r["content_source"]

        row["IMAGE_URL"] = r.get("image_url", "")
        row["IMAGE_URLS"] = json.dumps(r.get("image_urls", []), ensure_ascii=False)
        row["IMAGE_SOURCE"] = r.get("image_source", "")

        if i % 10 == 0 or i == len(flat_rows):
            ok_cnt = sum(1 for rr in flat_rows if rr.get("CONTENT_STATUS") == "OK")
            img_cnt = sum(1 for rr in flat_rows if rr.get("IMAGE_URL"))
            print(f"  - 진행 {i}/{len(flat_rows)} | CONTENT_OK {ok_cnt} | IMAGE(primary) {img_cnt}")

        time.sleep(config.content_sleep_sec)

    print("[DETAIL] 본문/이미지 크롤링 완료.\n")


# =========================
# 저장(CSV)
# =========================
def make_output_filename(config: CrawlConfig) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{config.output_prefix}_{ts}_last{config.days_back}d_company_plus_person_only.csv"

def save_results_csv(flat_rows, out_path: str):
    fieldnames = [
        "GROUP",
        "COMPANY_KEYWORD",
        "PERSON",
        "QUERY_USED",
        "CID",
        "DATETIME",
        "TITLE",
        "URL",
        "CONTENT",
        "CONTENT_LEN",
        "CONTENT_STATUS",
        "CONTENT_SOURCE",
        "IMAGE_URL",
        "IMAGE_URLS",
        "IMAGE_SOURCE",
    ]
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(flat_rows)


# =========================
# ✅ MongoDB 업로드(요청: Group, PERSON, CID, DATETIME, TITLE, CONTENT, URL만)
# =========================
def build_mongo_doc_from_row(row: dict) -> dict:
    dt_val = row.get("DATETIME", "")
    dt_obj = None
    try:
        if dt_val:
            dt_obj = datetime.strptime(dt_val, "%Y-%m-%d %H:%M:%S")
    except Exception:
        dt_obj = None

    return {
        "Group": row.get("GROUP", ""),
        "PERSON": row.get("PERSON", ""),
        "CID": row.get("CID", ""),
        "DATETIME": dt_obj if dt_obj else dt_val,
        "TITLE": row.get("TITLE", ""),
        "CONTENT": row.get("CONTENT", ""),
        "URL": row.get("URL", ""),
        "IMAGE_URL": row.get("IMAGE_URL", ""),
        "IMAGE_URLS": json.loads(row.get("IMAGE_URLS", "[]")) if row.get("IMAGE_URLS") else [],
    }


def upload_rows_to_mongo(flat_rows, config: CrawlConfig):
    if not MongoClient or not UpdateOne:
        raise RuntimeError("pymongo가 설치되지 않았습니다. pip install pymongo")

    if not config.mongo_uri:
        raise RuntimeError("MONGO_URI is required. Set it in .env")

    client = MongoClient(config.mongo_uri)
    col = client[config.mongo_db][config.mongo_collection]

    ops = []
    sent = 0

    for row in flat_rows:
        cid = (row.get("CID") or "").strip()
        if not cid:
            continue

        doc = build_mongo_doc_from_row(row)

        ops.append(
            UpdateOne(
                {"CID": cid},
                {"$set": doc},
                upsert=config.mongo_upsert,
            )
        )

        if len(ops) >= config.mongo_batch_size:
            result = col.bulk_write(ops, ordered=False)
            sent += len(ops)
            ops.clear()
            print("✅ Mongo bulk 업로드:", {
                "sent": sent,
                "matched": result.matched_count,
                "modified": result.modified_count,
                "upserted": len(result.upserted_ids or {}),
            })

    if ops:
        result = col.bulk_write(ops, ordered=False)
        sent += len(ops)
        ops.clear()
        print("✅ Mongo bulk 업로드:", {
            "sent": sent,
            "matched": result.matched_count,
            "modified": result.modified_count,
            "upserted": len(result.upserted_ids or {}),
        })


# =========================
# search_groups 로드(옵션)
# =========================
def load_search_groups_from_csv(config: CrawlConfig) -> dict:
    """
    CSV에서 (GROUP -> (COMPANY, PERSON)) 로드
    - 컬럼명은 config.groups_csv_* 로 매핑
    """
    groups = {}
    with open(config.groups_csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            g = (row.get(config.groups_csv_group_col) or "").strip()
            c = (row.get(config.groups_csv_company_col) or "").strip()
            p = (row.get(config.groups_csv_person_col) or "").strip()
            if not g:
                continue
            if not c or not p:
                continue
            groups[g] = (c, p)
    return groups


# =========================
# 메인 크롤러
# =========================
def get_news(search_groups: dict, config: CrawlConfig):
    since_dt = get_since_dt(config.days_back)
    print(f"조회 기준 시간: {since_dt.strftime('%Y-%m-%d %H:%M:%S')} 이후 기사")
    print(f"적용 필터: cattr={config.cattr}, div_code={config.div_code}")
    print(f"페이징: max_pages={config.max_pages} / page_size={config.page_size}")
    print(f"본문(fetch_content)={config.fetch_content} / 이미지(fetch_image)={config.fetch_image}")
    print(f"그룹 수: {len(search_groups)}\n")

    session = requests.Session()
    session.mount("https://", LegacySSLAdapter())

    seen_cids_global = set()
    final_results = {}
    flat_rows = []

    for group_name, (company_kw, person_kw) in search_groups.items():
        group_articles = []
        seen_cids_group = set()

        queries = build_queries_company_plus_person(company_kw, person_kw)
        if not queries:
            print(f"⚠️ 그룹 '{group_name}' 스킵: company/person 누락 (company='{company_kw}', person='{person_kw}')")
            final_results[group_name] = []
            continue

        for q in queries:
            try:
                articles, _raw = fetch_articles_paged(session, config, q, since_dt)

                added = 0
                for a in articles:
                    cid = a["CID"]

                    if cid in seen_cids_group:
                        continue
                    if config.dedup_global and cid in seen_cids_global:
                        continue

                    seen_cids_group.add(cid)
                    if config.dedup_global:
                        seen_cids_global.add(cid)

                    a["KEYWORD_FOUND"] = q
                    group_articles.append(a)
                    added += 1

                    flat_rows.append(
                        {
                            "GROUP": group_name,
                            "COMPANY_KEYWORD": company_kw,
                            "PERSON": person_kw,
                            "QUERY_USED": q,
                            "CID": cid,
                            "DATETIME": a["DATETIME"],
                            "TITLE": a["TITLE"],
                            "URL": a["URL"],
                            "CONTENT": "",
                            "CONTENT_LEN": 0,
                            "CONTENT_STATUS": "PENDING",
                            "CONTENT_SOURCE": "",
                            "IMAGE_URL": "",
                            "IMAGE_URLS": "[]",
                            "IMAGE_SOURCE": "",
                        }
                    )

                print(f"✔ 그룹 '{group_name}' / 쿼리 '{q}' 완료 (추가 {added}건, 그룹누적 {len(group_articles)}건)")
                time.sleep(config.sleep_sec)

            except Exception as e:
                print(f"❌ 그룹 '{group_name}' / 쿼리 '{q}' 오류: {e}")

        final_results[group_name] = group_articles

    if config.fetch_content and flat_rows:
        enrich_rows_with_content_and_image(session, config, flat_rows)

    return final_results, flat_rows


# =========================
# 실행부
# =========================
if __name__ == "__main__":
    # 1) search_groups 준비
    if CONFIG.load_groups_from_csv:
        search_groups = load_search_groups_from_csv(CONFIG)
    else:
        # 기본: 하드코딩 (원하는 대로 편집)
        search_groups = {
            "유진그룹": ("유진그룹", "유경선"),
            "BGF": ("BGF", "홍석조"),
            "현대해상": ("현대해상", "정몽윤"),
            "하이브": ("하이브", "방시혁"),
            "한솔": ("한솔", "조동길"),
            "삼성": ("삼성전자", "이재용"),
            "SK": ("SK", "최태원"),
            "현대자동차": ("현대자동차", "정의선"),
            "LG": ("LG", "구광모"),
            "롯데": ("롯데", "신동빈"),
            "한화": ("한화", "김승연"),
            "HD현대": ("HD현대", "정몽준"),
            "GS": ("GS", "허창수"),
            "신세계": ("신세계", "이명희"),
            "한진": ("한진", "조원태"),
            "CJ": ("CJ", "이재현"),
            "LS": ("LS", "구자은"),
            "카카오": ("카카오", "김범수"),
            "두산": ("두산", "박정원"),
            "DL": ("DL", "이해욱"),
            "중흥건설": ("중흥건설", "정창선"),
            "셀트리온": ("셀트리온", "서정진"),
            "네이버": ("네이버", "이해진"),
            "현대백화점": ("현대백화점", "정지선"),
            "한국앤컴퍼니그룹": ("한국앤컴퍼니그룹", "조양래"),
            "부영": ("부영", "이중근"),
            "하림": ("하림", "김홍국"),
            "효성": ("효성", "조현준"),
            "SM": ("SM", "우오현"),
            "HDC": ("HDC", "정몽규"),
            "호반건설": ("호반건설", "김상열"),
            "코오롱": ("코오롱", "이웅열"),
            "KCC": ("KCC", "정몽진"),
            "DB": ("DB", "김준기"),
            "OCI": ("OCI", "이우현"),
            "LX": ("LX", "구본준"),
            "넷마블": ("넷마블", "방준혁"),
            "이랜드": ("이랜드", "박성수"),
            "교보생명보험": ("교보생명보험", "신창재"),
            "다우키움": ("다우키움", "김익래"),
            "금호석유화학": ("금호석유화학", "박찬구"),
            "태영": ("태영", "윤세영"),
            "KG": ("KG", "곽재선"),
            "HL": ("HL", "정몽원"),
            "동원": ("동원", "김남정"),
            "아모레퍼시픽": ("아모레퍼시픽", "서경배"),
            "태광": ("태광", "이호진"),
            "크래프톤": ("크래프톤", "장병규"),
            "애경": ("애경", "장영신"),
            "동국제강": ("동국제강", "장세주"),
            "중앙": ("중앙", "홍석현"),
        }

    # 2) 수집
    news_data, flat_rows = get_news(search_groups, CONFIG)

    # 3) CSV 저장
    out_csv = make_output_filename(CONFIG)
    save_results_csv(flat_rows, out_csv)
    print(f"\n✅ CSV 저장 완료: {out_csv}")

    # 4) MongoDB 업로드(요청 7필드만)
    if CONFIG.upload_to_mongo:
        upload_rows_to_mongo(flat_rows, CONFIG)
