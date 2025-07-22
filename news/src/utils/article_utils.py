# utils/article_utils.py

# ------------------------------------------------------------------
# 기사 추출 관련 함수 (driver_utils.py에서 이동)
# ------------------------------------------------------------------
from .driver_utils import initialize_driver
import requests
from bs4 import BeautifulSoup
from newspaper import Article
from typing import Callable, Optional, Tuple
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time
import nltk
from urllib.parse import urljoin
import os
from datetime import datetime
try:
    from zoneinfo import ZoneInfo
    def get_today_kst_str():
        return datetime.now(ZoneInfo('Asia/Seoul')).strftime('%Y%m%d %H:%M')
    def get_today_kst_date_str():
        return datetime.now(ZoneInfo('Asia/Seoul')).strftime('%Y%m%d')
except ImportError:
    import pytz
    def get_today_kst_str():
        return datetime.now(pytz.timezone('Asia/Seoul')).strftime('%Y%m%d %H:%M')
    def get_today_kst_date_str():
        return datetime.now(pytz.timezone('Asia/Seoul')).strftime('%Y%m%d')

# NLTK 데이터 경로 설정
nltk_data_path = './nltk_data'
if os.path.exists(nltk_data_path):
    nltk.data.path.append(nltk_data_path)

# 최소 본문 길이
MIN_BODY_LENGTH = 300

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'ko-KR,ko;q=0.8,en-US;q=0.5,en;q=0.3',
}

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-09
# 기능 : 기사 본문 추출 함수(기사 재생성)
# ------------------------------------------------------------------
def extract_article_content(
    url: str,
    progress_callback: Optional[Callable[[str], None]] = None
) -> Tuple[str, str]:
    """
    주어진 기사 URL로부터 제목과 본문을 추출합니다.
    여러 방식으로 시도하여 충분한 길이의 본문을 얻으면 성공
    :param url: 뉴스 기사 URL
    :return: (제목, 본문)
    """
    extractors = [
        extract_with_newspaper,
        extract_with_smart_parser,
        extract_with_iframe,
    ]

    for extractor in extractors:
        try:
            title, body = extractor(url)
            if len(body) >= MIN_BODY_LENGTH:
                return title, body
        except Exception:
            continue

    raise ValueError("기사 본문 추출 실패")

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-09
# 기능 : newspaper 라이브러리를 사용하여 기사 본문 추출 함수(기사 재생성)
# ------------------------------------------------------------------
def extract_with_newspaper(url: str) -> tuple[str, str]:
    article = Article(url, language='ko')
    article.download()
    article.parse()
    return article.title.strip(), article.text.strip()

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-09
# 기능 : BeautifulSoup 라이브러리를 사용하여 기사 본문 추출 함수(기사 재생성)
# ------------------------------------------------------------------
def extract_with_smart_parser(url: str) -> tuple[str, str]:
    res = requests.get(url, headers=HEADERS, timeout=10)
    soup = BeautifulSoup(res.text, 'html.parser')

    title = "제목 없음"
    for selector in ['h1', '.article-title', '.news-title', '.entry-title']:
        tag = soup.select_one(selector)
        if tag and tag.text.strip():
            title = tag.text.strip()
            break

    body = ""
    for selector in ['article', '.articleBody', '.view_content', '.post-content']:
        body_area = soup.select_one(selector)
        if body_area:
            for unwanted in body_area.select('script, style, .ad, .comment'):
                unwanted.decompose()
            body = body_area.get_text("\n").strip()
            if len(body) > 200:
                break

    return title, body

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-09
# 기능 : iframe 태그인 경우 기사 본문 추출하는 함수(기사 재생성)
# ------------------------------------------------------------------
def extract_with_iframe(url: str) -> tuple[str, str]:
    res = requests.get(url, headers=HEADERS)
    soup = BeautifulSoup(res.text, 'html.parser')
    title_tag = soup.select_one('h1') or soup.select_one('title')
    title = title_tag.text.strip() if title_tag else "제목 없음"

    best_body = ""
    iframes = soup.select("iframe[src*='proc_view_body']")
    for iframe in iframes:
        iframe_url = urljoin(url, iframe.get("src"))
        try:
            iframe_res = requests.get(iframe_url, headers=HEADERS)
            iframe_soup = BeautifulSoup(iframe_res.text, 'html.parser')
            # 스마트 파싱 시도 (기사 영역 우선)
            body = ""
            for selector in ['article', '.articleBody', '.view_content', '.post-content']:
                body_area = iframe_soup.select_one(selector)
                if body_area:
                    for unwanted in body_area.select('script, style, .ad, .comment'):
                        unwanted.decompose()
                    body = body_area.get_text("\n").strip()
                    if len(body) > 200:
                        break
            # 만약 스마트 파싱 실패 시 전체 텍스트 fallback
            if not body or len(body) < 100:
                body = iframe_soup.get_text("\n").strip()
            # 가장 긴 본문을 선택
            if len(body) > len(best_body):
                best_body = body
        except:
            continue

    return title, best_body