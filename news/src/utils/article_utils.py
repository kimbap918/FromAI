# ------------------------------------------------------------------
# 작성자 : 최준혁
# 기능 : 기사 본문 추출 모듈
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
        """
        현재 한국 시간(KST)을 'YYYYMMDD HH:MM' 형식의 문자열로 반환.
        zoneinfo 라이브러리가 가능할 경우 사용.
        """
        return datetime.now(ZoneInfo('Asia/Seoul')).strftime('%Y%m%d %H:%M')
    def get_today_kst_date_str():
        """
        현재 한국 시간(KST)의 날짜를 'YYYYMMDD' 형식의 문자열로 반환.
        zoneinfo 라이브러리가 가능할 경우 사용.
        """
        return datetime.now(ZoneInfo('Asia/Seoul')).strftime('%Y%m%d')
except ImportError:
    import pytz
    def get_today_kst_str():
        """
        현재 한국 시간(KST)을 'YYYYMMDD HH:MM' 형식의 문자열로 반환.
        pytz 라이브러리 사용.
        """
        return datetime.now(pytz.timezone('Asia/Seoul')).strftime('%Y%m%d %H:%M')
    def get_today_kst_date_str():
        """
        현재 한국 시간(KST)의 날짜를 'YYYYMMDD' 형식의 문자열로 반환.
        pytz 라이브러리 사용.
        """
        return datetime.now(pytz.timezone('Asia/Seoul')).strftime('%Y%m%d')


# NLTK 데이터 경로 설정
nltk_data_path = './nltk_data'
# 지정 경로에 NLTK 데이터가 있으면, NLTK가 해당 경로에서 데이터를 찾도록 설정.
if os.path.exists(nltk_data_path):
    nltk.data.path.append(nltk_data_path)

# 최소 본문 길이
MIN_BODY_LENGTH = 300

# HTTP 요청 시 사용될 기본 헤더.
# 일반 웹 브라우저의 요청처럼 보이게 해 차단을 피하는 데 도움.
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
    주어진 기사 URL에서 제목과 본문을 추출.
    여러 방식으로 시도해 충분한 길이의 본문을 얻으면 성공.
    :param url: 뉴스 기사 URL
    :param progress_callback: (선택 사항) 진행 상태를 알리기 위한 콜백 함수
    :return: (제목, 본문)
    """
    # 본문 추출을 시도할 함수 목록
    extractors = [
        extract_with_newspaper,
        extract_with_smart_parser,
        extract_with_iframe,
    ]

    # 각 추출 방식을 순서대로 시도.
    for extractor in extractors:
        try:
            # 현재 추출 방식 실행으로 제목과 본문 획득.
            title, body = extractor(url)
            # 본문 길이가 최소 요구 길이(MIN_BODY_LENGTH) 이상인지 확인.
            if len(body) >= MIN_BODY_LENGTH:
                return title, body
        except Exception:
            # 오류 발생 시 다음 방식으로 이동.
            continue

    # 모든 방식이 실패하면 예외 발생.
    raise ValueError("기사 본문 추출 실패")

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-09
# 기능 : newspaper 라이브러리를 사용하여 기사 본문 추출 함수(기사 재생성)
# ------------------------------------------------------------------
def extract_with_newspaper(url: str) -> tuple[str, str]:
    """
    'newspaper' 라이브러리로 기사 본문 추출.
    다양한 웹사이트 구조를 자동으로 분석해 기사 내용 파싱.
    :param url: 뉴스 기사 URL
    :return: (제목, 본문)
    """
    article = Article(url, language='ko') # 한국어 설정으로 Article 객체 생성
    article.download() # HTML 콘텐츠 다운로드
    article.parse()    # 제목, 본문, 이미지 등 파싱
    return article.title.strip(), article.text.strip() # 제목과 본문 텍스트 반환

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-09
# 기능 : BeautifulSoup 라이브러리를 사용하여 기사 본문 추출 함수(기사 재생성)
# ------------------------------------------------------------------
def extract_with_smart_parser(url: str) -> tuple[str, str]:
    """
    'BeautifulSoup'을 사용한 스마트 파싱 함수.
    기사 영역을 나타내는 일반적인 CSS 선택자(class, tag) 이용.
    :param url: 뉴스 기사 URL
    :return: (제목, 본문)
    """
    res = requests.get(url, headers=HEADERS, timeout=10) # 요청 전송
    soup = BeautifulSoup(res.text, 'html.parser') # HTML 파싱

    title = "제목 없음"
    # 흔히 쓰이는 제목 영역 CSS 선택자 순회로 제목 탐색.
    for selector in ['h1', '.article-title', '.news-title', '.entry-title']:
        tag = soup.select_one(selector)
        if tag and tag.text.strip():
            title = tag.text.strip()
            break # 제목 찾으면 루프 종료

    body = ""
    # 흔히 쓰이는 본문 영역 CSS 선택자 순회로 본문 탐색.
    for selector in ['article', '.articleBody', '.view_content', '.post-content']:
        body_area = soup.select_one(selector)
        if body_area:
            # 본문 영역에서 스크립트, 스타일, 광고, 댓글 등 불필요한 태그 제거.
            for unwanted in body_area.select('script, style, .ad, .comment'):
                unwanted.decompose()
            body = body_area.get_text("\n").strip() # 텍스트 추출 및 정리.
            if len(body) > 200: # 충분한 길이의 본문 찾으면 탐색 중단.
                break

    return title, body

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-09
# 기능 : iframe 태그인 경우 기사 본문 추출하는 함수(기사 재생성)
# ------------------------------------------------------------------
def extract_with_iframe(url: str) -> tuple[str, str]:
    """
    기사 본문이 iframe 내에 포함된 경우, iframe 소스 URL로 접근해 본문 추출.
    :param url: 뉴스 기사 URL
    :return: (제목, 본문)
    """
    res = requests.get(url, headers=HEADERS)
    soup = BeautifulSoup(res.text, 'html.parser')
    
    # 메인 페이지에서 제목 찾기.
    title_tag = soup.select_one('h1') or soup.select_one('title')
    title = title_tag.text.strip() if title_tag else "제목 없음"

    best_body = ""
    # src 속성에 'proc_view_body' 포함된 모든 iframe 태그 탐색.
    iframes = soup.select("iframe[src*='proc_view_body']")
    for iframe in iframes:
        # iframe의 상대 경로를 절대 경로로 변환.
        iframe_url = urljoin(url, iframe.get("src"))
        try:
            # iframe URL에 다시 요청 전송.
            iframe_res = requests.get(iframe_url, headers=HEADERS)
            iframe_soup = BeautifulSoup(iframe_res.text, 'html.parser')
            
            # iframe 내부에서 'extract_with_smart_parser'와 유사하게 본문 파싱.
            body = ""
            for selector in ['article', '.articleBody', '.view_content', '.post-content']:
                body_area = iframe_soup.select_one(selector)
                if body_area:
                    # 불필요한 태그 제거.
                    for unwanted in body_area.select('script, style, .ad, .comment'):
                        unwanted.decompose()
                    body = body_area.get_text("\n").strip()
                    if len(body) > 200:
                        break
            
            # 스마트 파싱 실패 시 iframe의 모든 텍스트를 본문으로 사용.
            if not body or len(body) < 100:
                body = iframe_soup.get_text("\n").strip()

            # 여러 iframe 중 가장 긴 본문 선택 후 저장.
            if len(body) > len(best_body):
                best_body = body
        except:
            continue

    return title, best_body