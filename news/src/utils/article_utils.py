# ------------------------------------------------------------------
# 작성자 : 최준혁 (+ ChatGPT 보강)
# 기능 : 기사 본문 + 작성일 추출 모듈
# ------------------------------------------------------------------
from .driver_utils import initialize_driver
import requests
from bs4 import BeautifulSoup
from newspaper import Article
from typing import Callable, Optional, Tuple, List, Iterable
import re
import json
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time
import nltk
from urllib.parse import urljoin
import os
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

# ----- KST 헬퍼 ----------------------------------------------------
try:
    from zoneinfo import ZoneInfo
    KST = ZoneInfo('Asia/Seoul')
    def get_today_kst_str():
        return datetime.now(KST).strftime('%Y%m%d %H:%M')
    def get_today_kst_date_str():
        return datetime.now(KST).strftime('%Y%m%d')
except ImportError:
    import pytz
    KST = pytz.timezone('Asia/Seoul')
    def get_today_kst_str():
        return datetime.now(KST).strftime('%Y%m%d %H:%M')
    def get_today_kst_date_str():
        return datetime.now(KST).strftime('%Y%m%d')

# dateutil 이 있으면 사용(더 강력), 없으면 표준 파서로 폴백
try:
    from dateutil import parser as date_parser
except Exception:
    date_parser = None

# NLTK 데이터 경로 설정
nltk_data_path = './nltk_data'
if os.path.exists(nltk_data_path):
    nltk.data.path.append(nltk_data_path)

# 최소 본문 길이
MIN_BODY_LENGTH = 300

# HTTP 요청 기본 헤더
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'ko-KR,ko;q=0.8,en-US;q=0.5,en;q=0.3',
}

# ------------------------------------------------------------------
# 기능 : 기사 본문 추출(기존 로직 유지)
# ------------------------------------------------------------------
def extract_article_content(
    url: str,
    progress_callback: Optional[Callable[[str], None]] = None
) -> Tuple[str, str]:
    """
    주어진 기사 URL에서 제목과 본문을 추출.
    여러 방식으로 시도해 충분한 길이의 본문을 얻으면 성공.
    :param url: 뉴스 기사 URL
    :param progress_callback: (선택 사항) 진행 상태를 알리기 위한 콜백 함수
    :return: (제목, 본문)
    """
    extractors = [
        extract_with_newspaper,
        extract_with_smart_parser,
        extract_with_iframe,
    ]

    for extractor in extractors:
        try:
            if progress_callback:
                progress_callback(f"[본문] {extractor.__name__} 시도")
            title, body = extractor(url)
            if len(body) >= MIN_BODY_LENGTH:
                if progress_callback:
                    progress_callback(f"[본문] {extractor.__name__} 성공 (len={len(body)})")
                return title, body
            else:
                if progress_callback:
                    progress_callback(f"[본문] {extractor.__name__} 본문 짧음 (len={len(body)})")
        except Exception as e:
            if progress_callback:
                progress_callback(f"[본문] {extractor.__name__} 예외: {e}")
            continue

    raise ValueError("기사 본문 추출 실패")

# ------------------------------------------------------------------
# 기능 : newspaper 라이브러리 사용(기존)
# ------------------------------------------------------------------
def extract_with_newspaper(url: str) -> tuple[str, str]:
    article = Article(url, language='ko')
    article.download()
    article.parse()
    return article.title.strip(), article.text.strip()

# ------------------------------------------------------------------
# 기능 : BeautifulSoup 스마트 파싱(기존)
# ------------------------------------------------------------------
def extract_with_smart_parser(url: str) -> tuple[str, str]:
    res = requests.get(url, headers=HEADERS, timeout=10)
    soup = BeautifulSoup(res.text, 'html.parser')

    title = "제목 없음"
    for selector in ['h1', '.article-title', '.news-title', '.entry-title', 'meta[property="og:title"]', 'meta[name="title"]']:
        tag = soup.select_one(selector)
        if tag:
            if tag.name == 'meta':
                content = tag.get('content') or ''
                if content.strip():
                    title = content.strip()
                    break
            elif tag.text and tag.text.strip():
                title = tag.text.strip()
                break

    body = ""
    for selector in ['article', '.articleBody', '.view_content', '.post-content', '#articleBody', '#news_body', '.news_body', '#articeBody', '#articlContent', '.content-article']:
        body_area = soup.select_one(selector)
        if body_area:
            for unwanted in body_area.select('script, style, .ad, .advertisement, .ads, .comment, #commnets, .sns_area'):
                unwanted.decompose()
            body = body_area.get_text("\n").strip()
            if len(body) > 200:
                break

    return title, body

# ------------------------------------------------------------------
# 기능 : iframe 처리(기존)
# ------------------------------------------------------------------
def extract_with_iframe(url: str) -> tuple[str, str]:
    res = requests.get(url, headers=HEADERS, timeout=10)
    soup = BeautifulSoup(res.text, 'html.parser')
    
    title_tag = soup.select_one('h1') or soup.select_one('title') or soup.select_one('meta[property="og:title"]')
    if title_tag and getattr(title_tag, 'name', '') == 'meta':
        title = (title_tag.get('content') or '').strip() or "제목 없음"
    else:
        title = title_tag.text.strip() if title_tag else "제목 없음"

    best_body = ""
    # 흔한 iframe 키워드들 포괄
    iframes = soup.select("iframe[src*='proc_view_body'], iframe[src*='view'], iframe[src*='article']")
    for iframe in iframes:
        iframe_url = urljoin(url, iframe.get("src"))
        try:
            iframe_res = requests.get(iframe_url, headers=HEADERS, timeout=10)
            iframe_soup = BeautifulSoup(iframe_res.text, 'html.parser')
            body = ""
            for selector in ['article', '.articleBody', '.view_content', '.post-content', '#articleBody', '#news_body', '.news_body']:
                body_area = iframe_soup.select_one(selector)
                if body_area:
                    for unwanted in body_area.select('script, style, .ad, .comment'):
                        unwanted.decompose()
                    body = body_area.get_text("\n").strip()
                    if len(body) > 200:
                        break
            if not body or len(body) < 100:
                body = iframe_soup.get_text("\n").strip()
            if len(body) > len(best_body):
                best_body = body
        except Exception:
            continue

    return title, best_body

# ===========================
#        날짜 추출 보강부 
# ===========================

_META_DATE_KEYS: List[str] = [
    # Open Graph / Facebook
    'article:published_time',
    'og:published_time',
    'article:modified_time',
    'og:updated_time',
    # 일반 메타
    'pubdate',
    'publishdate',
    'timestamp',
    'date',
    'dc.date',
    'dc.date.issued',
    'DC.date.issued',
    'dcterms.created',
    'dcterms.date',
    'dcterms.issued',
    'sailthru.date',
    'parsely-pub-date',
    'date_published',
    'datePublished',
    'datecreated',
    'dateCreated',
]

# 한국/영문 날짜 텍스트 패턴(예: 2025.09.02 11:30, 2025-09-02, 2025년 9월 2일 등)
_TEXT_DATE_REGEXES: List[re.Pattern] = [
    re.compile(r'(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})\s+(\d{1,2}):(\d{2})'),
    re.compile(r'(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})'),
    re.compile(r'(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일(?:\s*(\d{1,2})시\s*(\d{1,2})분)?'),
]

_URL_DATE_REGEXES: List[re.Pattern] = [
    re.compile(r'/(\d{4})/(\d{1,2})/(\d{1,2})/'),
    re.compile(r'/(\d{8})(?:/|$)'),
]

def _try_parse_datetime(value: str) -> Optional[datetime]:
    """
    문자열 -> datetime 파싱 시도.
    가능한 경우 tz-aware로 반환. 실패시 None.
    """
    if not value:
        return None
    # 1) RFC 2822 형식 시도 (e.g., Tue, 02 Sep 2025 11:20:00 +0900)
    try:
        dt = parsedate_to_datetime(value)
        if isinstance(dt, datetime):
            return dt
    except Exception:
        pass

    # 2) dateutil 있으면 가장 강력
    if date_parser is not None:
        try:
            # dayfirst는 False (국문 사이트는 연-월-일이 보편적)
            dt = date_parser.parse(value, fuzzy=True, dayfirst=False)
            return dt
        except Exception:
            pass

    # 3) 대표 포맷들 수동 시도
    common_formats = [
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M",
        "%Y.%m.%d %H:%M",
        "%Y-%m-%d",
        "%Y.%m.%d",
        "%Y/%m/%d",
        "%Y%m%d",
        "%a, %d %b %Y %H:%M:%S %z",
    ]
    for fmt in common_formats:
        try:
            dt = datetime.strptime(value.strip(), fmt)
            return dt
        except Exception:
            continue
    return None

def _to_kst_string(dt: datetime) -> str:
    """
    datetime -> 'YYYYMMDD HH:MM' (KST) 문자열
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt_kst = dt.astimezone(KST)
    return dt_kst.strftime('%Y%m%d %H:%M')

def _clean_text(s: str) -> str:
    return re.sub(r'\s+', ' ', s or '').strip()

def _iter_ldjson_objects(soup: BeautifulSoup) -> Iterable[dict]:
    for tag in soup.find_all('script', type=lambda t: t and 'ld+json' in t):
        try:
            txt = tag.string or tag.get_text() or ''
            if not txt.strip():
                continue
            # 일부 사이트는 여러 JSON 객체를 배열로 묶기도 함
            data = json.loads(txt)
            if isinstance(data, dict):
                yield data
            elif isinstance(data, list):
                for obj in data:
                    if isinstance(obj, dict):
                        yield obj
        except Exception:
            continue

def _extract_from_ldjson(soup: BeautifulSoup) -> Optional[datetime]:
    for obj in _iter_ldjson_objects(soup):
        t = (obj.get('datePublished')
             or obj.get('dateCreated')
             or (obj.get('publication', {}) or {}).get('datePublished'))
        if isinstance(t, str) and t.strip():
            dt = _try_parse_datetime(t)
            if dt:
                return dt
    return None

def _extract_from_meta(soup: BeautifulSoup) -> Optional[datetime]:
    # property / name 둘 다 검사
    for key in _META_DATE_KEYS:
        # property
        for tag in soup.select(f'meta[property="{key}"]'):
            val = tag.get('content') or ''
            if val.strip():
                dt = _try_parse_datetime(val)
                if dt:
                    return dt
        # name
        for tag in soup.select(f'meta[name="{key}"]'):
            val = tag.get('content') or ''
            if val.strip():
                dt = _try_parse_datetime(val)
                if dt:
                    return dt

    # 일반적인 meta[name="date"] 변형
    for tag in soup.find_all('meta'):
        name = (tag.get('name') or tag.get('property') or '').lower()
        if any(k in name for k in ['date', 'time', 'published', 'issued', 'created']):
            val = tag.get('content') or ''
            if val.strip():
                dt = _try_parse_datetime(val)
                if dt:
                    return dt
    return None

def _extract_from_time_tags(soup: BeautifulSoup) -> Optional[datetime]:
    for t in soup.find_all('time'):
        # <time datetime="..."> 가 가장 신뢰도 높음
        val = t.get('datetime') or ''
        if val.strip():
            dt = _try_parse_datetime(val)
            if dt:
                return dt
        # 텍스트 노드에 날짜가 들어 있는 경우
        txt = _clean_text(t.get_text())
        if txt:
            dt = _try_parse_datetime(txt)
            if dt:
                return dt
    return None

def _extract_from_text_patterns(soup: BeautifulSoup) -> Optional[datetime]:
    # 흔히 쓰는 위치들만 제한적으로 검사(오탐 줄이기)
    candidates: List[str] = []
    for sel in ['.date', '.byline', '.timestamp', '.article_info', '.news_date', '.write', '.author', '.info', '#news_date']:
        for tag in soup.select(sel):
            txt = _clean_text(tag.get_text())
            if txt:
                candidates.append(txt)

    # 상단/하단에 있는 작은 텍스트들도 가끔 날짜 포함
    for tag in soup.find_all(['span', 'em', 'p', 'div'], limit=80):
        txt = _clean_text(tag.get_text())
        if any(key in txt for key in ['입력', '게재', '발행', '업데이트', '수정', 'Published', 'Updated']):
            candidates.append(txt)

    for text in candidates:
        # 직접 파서 시도
        dt = _try_parse_datetime(text)
        if dt:
            return dt
        # 정규식 보조
        for rx in _TEXT_DATE_REGEXES:
            m = rx.search(text)
            if m:
                try:
                    y = int(m.group(1))
                    mo = int(m.group(2))
                    d = int(m.group(3))
                    hh = int(m.group(4)) if m.lastindex and m.lastindex >= 4 and m.group(4) else 0
                    mm = int(m.group(5)) if m.lastindex and m.lastindex >= 5 and m.group(5) else 0
                    dt = datetime(y, mo, d, hh, mm, tzinfo=KST)
                    return dt
                except Exception:
                    continue
    return None

def _extract_from_url(url: str) -> Optional[datetime]:
    for rx in _URL_DATE_REGEXES:
        m = rx.search(url)
        if m:
            try:
                if len(m.groups()) == 3:
                    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                    return datetime(y, mo, d, 0, 0, tzinfo=KST)
                elif len(m.groups()) == 1:
                    ymd = m.group(1)
                    y, mo, d = int(ymd[:4]), int(ymd[4:6]), int(ymd[6:8])
                    return datetime(y, mo, d, 0, 0, tzinfo=KST)
            except Exception:
                continue
    return None

def extract_publish_datetime_from_html(html: str, base_url: Optional[str] = None) -> Optional[str]:
    """
    HTML 문자열에서 기사 작성일을 추출하여 'YYYYMMDD HH:MM'(KST)로 반환.
    실패시 None.
    """
    if not html:
        return None
    soup = BeautifulSoup(html, 'html.parser')

    # 1) ld+json
    dt = _extract_from_ldjson(soup)
    if dt:
        return _to_kst_string(dt)

    # 2) meta
    dt = _extract_from_meta(soup)
    if dt:
        return _to_kst_string(dt)

    # 3) <time>
    dt = _extract_from_time_tags(soup)
    if dt:
        return _to_kst_string(dt)

    # 4) 텍스트 패턴
    dt = _extract_from_text_patterns(soup)
    if dt:
        return _to_kst_string(dt)

    # 5) URL 패턴
    if base_url:
        dt = _extract_from_url(base_url)
        if dt:
            return _to_kst_string(dt)

    return None

def extract_publish_datetime(url: str) -> Optional[str]:
    """
    주어진 기사 URL에서 작성일(발행일)을 'YYYYMMDD HH:MM'(KST)로 반환.
    실패 시 None.
    """
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
    except Exception:
        # URL 패턴만이라도 시도
        dt = _extract_from_url(url)
        return _to_kst_string(dt) if dt else None

    # 우선 HTML에서 시도
    dt_str = extract_publish_datetime_from_html(res.text, base_url=url)
    if dt_str:
        return dt_str

    # newspaper가 date_parsing을 하는 경우도 있으니 보조 시도
    try:
        art = Article(url, language='ko')
        art.download()
        art.parse()
        # newspaper3k Article 객체는 publish_date 속성을 가질 수 있음
        pd = getattr(art, 'publish_date', None)
        if pd and isinstance(pd, datetime):
            return _to_kst_string(pd)
        # 메타에서 못 찾았던 경우 텍스트 재시도
        if art.meta_data:
            # 흔한 키들 재검사
            for key in _META_DATE_KEYS:
                v = art.meta_data.get(key) or (art.meta_data.get('article', {}) or {}).get(key)
                if isinstance(v, str) and v.strip():
                    dt = _try_parse_datetime(v)
                    if dt:
                        return _to_kst_string(dt)
    except Exception:
        pass

    # 그래도 실패하면 URL 패턴
    dt = _extract_from_url(url)
    return _to_kst_string(dt) if dt else None

def extract_article_content_and_date(
    url: str,
    progress_callback: Optional[Callable[[str], None]] = None
) -> Tuple[str, str, Optional[str]]:
    """
    제목/본문/작성일을 한 번에 받고 싶을 때 사용할 수 있는 추가 래퍼.
    기존 extract_article_content 를 그대로 활용하여 본문을 얻고,
    별도로 extract_publish_datetime 으로 날짜를 병행 추출한다.
    """
    if progress_callback:
        progress_callback("[날짜] 발행일 추출 시도")
    published_at = extract_publish_datetime(url)
    if progress_callback and published_at:
        progress_callback(f"[날짜] 발행일 감지: {published_at}")

    title, body = extract_article_content(url, progress_callback=progress_callback)
    return title, body, published_at
