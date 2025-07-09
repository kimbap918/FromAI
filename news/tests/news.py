import webbrowser
import pyperclip
import requests
from bs4 import BeautifulSoup
from newspaper import Article
from urllib.parse import urljoin
import time

# Selenium 관련 import
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

# 설정
CHATBOT_URL = "https://chatgpt.com/g/g-67abdb7e8f1c8191978db654d8a57b86-gisa-jaeguseong-caesbos?model=gpt-4o"
MIN_BODY_LENGTH = 300

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'ko-KR,ko;q=0.8,en-US;q=0.5,en;q=0.3',
}

def extract_with_newspaper(url):
    """newspaper 라이브러리를 사용한 기본 추출"""
    article = Article(url, language='ko')
    article.download()
    article.parse()
    
    title = article.title.strip()
    body = article.text.strip()
    
    if len(body) < MIN_BODY_LENGTH:
        raise ValueError(f"본문이 너무 짧음: {len(body)}자")
    
    return title, body

def extract_with_smart_parser(url):
    """범용 스마트 기사 추출"""
    headers = HEADERS.copy()
    headers['Referer'] = url
    
    res = requests.get(url, headers=headers)
    soup = BeautifulSoup(res.text, 'html.parser')
    
    # 제목 추출
    title_selectors = [
        'h1', 'h2.media_end_head_headline', '.articleSubject',
        '.title', '.article-title', '.news-title', '.post-title'
    ]
    
    title = "제목 없음"
    for selector in title_selectors:
        title_tag = soup.select_one(selector)
        if title_tag and len(title_tag.text.strip()) > 5:
            title = title_tag.text.strip()
            if ' - ' in title:
                title = title.split(' - ')[0].strip()
            if ' | ' in title:
                title = title.split(' | ')[0].strip()
            break
    
    # 본문 추출
    body_selectors = [
        'article#dic_area', '.articleBody', '.article_body',
        '.article-content', '.news-content', '.view_content',
        '.content', '.post-content', 'article', '.entry-content'
    ]
    
    body = ""
    for selector in body_selectors:
        body_area = soup.select_one(selector)
        if body_area:
            # 불필요한 요소 제거
            for unwanted in body_area.find_all([
                'script', 'style', 'nav', 'aside', 'footer', 'header',
                '.ad', '.advertisement', '.related', '.comment', '.social'
            ]):
                unwanted.decompose()
            
            body = body_area.get_text(separator="\n").strip()
            if len(body) > 200:
                break
    
    # CSS 셀렉터 실패 시 패턴 기반 추출
    if len(body) < 200:
        body = extract_by_pattern(soup)
    
    # 제목 중복 제거
    if title != "제목 없음" and title in body:
        body = body.replace(title, '', 1).strip()
    
    # 제목이 없으면 본문에서 추출
    if title == "제목 없음" and body:
        first_lines = body.split('\n')[:3]
        for line in first_lines:
            if 10 <= len(line) <= 100 and '=' not in line and '기자' not in line:
                title = line
                body = body.replace(line, '', 1).strip()
                break
    
    return title, body

def extract_by_pattern(soup):
    """패턴 기반 본문 추출"""
    all_text = soup.get_text()
    lines = [line.strip() for line in all_text.split('\n') if line.strip()]
    
    # 기사 시작점 찾기
    start_idx = -1
    start_patterns = [
        lambda line: '기자' in line and ('=' in line or '@' in line),
        lambda line: any(outlet in line for outlet in ['뉴시스]', '연합뉴스]', 'YTN]']),
        lambda line: len(line) > 50 and '다고' in line and ('밝혔다' in line or '말했다' in line),
    ]
    
    for i, line in enumerate(lines):
        for pattern in start_patterns:
            if pattern(line):
                start_idx = i
                break
        if start_idx != -1:
            break
    
    # 기사 끝점 찾기
    end_idx = len(lines)
    if start_idx != -1:
        end_patterns = [
            'Copyright', '저작권', '무단', '재배포', 'ⓒ', '©',
            '많이 본', '관련기사', '추천기사', '실시간',
            '기자수첩', '오피니언', '사진', '동영상',
            '구독', '팔로우', '공유', '댓글'
        ]
        
        for i in range(start_idx + 1, len(lines)):
            line = lines[i]
            if any(pattern in line for pattern in end_patterns):
                end_idx = i
                break
            
            # 메뉴 감지
            if i > start_idx + 30:
                menu_keywords = ['정치', '경제', '사회', '문화', '스포츠', '연예', '국제']
                if sum(1 for keyword in menu_keywords if keyword in line) >= 2:
                    end_idx = i
                    break
    
    # 본문 정제
    if start_idx != -1 and end_idx > start_idx:
        article_lines = lines[start_idx:end_idx]
        filtered_lines = []
        
        skip_patterns = [
            '클릭', '바로가기', '더보기', '전체보기', '이전', '다음',
            '목록', '홈으로', '앱 다운', '구독하기', '로그인', '회원가입',
            'SNS', '페이스북', '트위터', '인스타그램', 'AD', '광고'
        ]
        
        for line in article_lines:
            if len(line) < 3:
                continue
            if any(pattern in line for pattern in skip_patterns):
                continue
            if line in ['정치', '경제', '사회', '문화', '스포츠', '연예', '국제', '금융', '산업', 'IT']:
                continue
            filtered_lines.append(line)
        
        return '\n'.join(filtered_lines)
    
    return ""

def extract_with_iframe(url):
    """iframe 기반 추출"""
    res = requests.get(url, headers=HEADERS)
    soup = BeautifulSoup(res.text, 'html.parser')
    
    # 제목 추출
    title_tag = soup.select_one('h2') or soup.select_one('title')
    title = title_tag.text.strip() if title_tag else "제목 없음"
    
    # iframe 처리
    body = ""
    iframe_tags = soup.select("iframe[src*='proc_view_body']")
    
    for iframe in iframe_tags:
        iframe_src = iframe.get("src")
        iframe_url = urljoin(url, iframe_src)
        
        try:
            iframe_res = requests.get(iframe_url, headers=HEADERS)
            iframe_soup = BeautifulSoup(iframe_res.text, 'html.parser')
            iframe_text = iframe_soup.get_text(separator="\n").strip()
            if iframe_text:
                body += "\n" + iframe_text
        except Exception:
            continue
    
    return title, body.strip()

def extract_with_selenium(url):
    """Selenium 기반 추출"""
    if not SELENIUM_AVAILABLE:
        raise ImportError("Selenium이 설치되지 않았습니다")
    
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    
    driver = None
    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.get(url)
        time.sleep(3)
        
        # 제목 추출
        try:
            title_element = driver.find_element(By.TAG_NAME, "h2")
            title = title_element.text.strip()
        except:
            try:
                title_element = driver.find_element(By.TAG_NAME, "title")
                title = title_element.text.strip()
            except:
                title = "제목 없음"
        
        # iframe 처리
        body = ""
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "iframe"))
            )
            
            iframes = driver.find_elements(By.TAG_NAME, "iframe")
            
            for iframe in iframes:
                try:
                    iframe_src = iframe.get_attribute("src")
                    if iframe_src and "proc_view_body" in iframe_src:
                        driver.switch_to.frame(iframe)
                        time.sleep(2)
                        
                        body_element = driver.find_element(By.TAG_NAME, "body")
                        iframe_text = body_element.text.strip()
                        if iframe_text:
                            body += "\n" + iframe_text
                        
                        driver.switch_to.default_content()
                except Exception:
                    driver.switch_to.default_content()
                    continue
                    
        except Exception:
            # iframe이 없으면 전체 페이지 텍스트 추출
            try:
                body_element = driver.find_element(By.TAG_NAME, "body")
                body = body_element.text.strip()
            except:
                body = "본문 추출 실패"
        
        return title, body.strip()
        
    finally:
        if driver:
            driver.quit()

def extract_article_content(url):
    """통합 기사 추출"""
    extractors = [
        ("newspaper", extract_with_newspaper),
        ("스마트 파서", extract_with_smart_parser),
        ("iframe", extract_with_iframe),
    ]
    
    if SELENIUM_AVAILABLE:
        extractors.append(("Selenium", extract_with_selenium))
    
    for name, extractor in extractors:
        try:
            print(f"{name} 시도 중...")
            title, body = extractor(url)
            
            if len(body) >= MIN_BODY_LENGTH:
                print(f"{name} 성공: {len(body)}자")
                return title, body
            else:
                print(f"{name} 실패: 본문 너무 짧음 ({len(body)}자)")
                
        except Exception as e:
            print(f"{name} 실패: {e}")
    
    raise Exception("모든 추출 방법이 실패했습니다")

def main():
    print("기사 재구성 챗봇 자동 연결기")
    print("0 입력 시 종료\n")
    
    if not SELENIUM_AVAILABLE:
        print("Selenium 미설치 - iframe 추출 기능 제한됨")
        print("설치: pip install selenium\n")
    
    first_time = True
    
    while True:
        url = input("기사 링크 입력 (0: 종료): ").strip()
        if url == "0":
            print("프로그램을 종료합니다.")
            break
        
        keyword = input("키워드 입력: ").strip()
        
        try:
            print("\n기사 추출 중...")
            title, body = extract_article_content(url)
            
            if len(body) < MIN_BODY_LENGTH:
                print("본문이 너무 짧습니다. 다른 링크를 시도해보세요.")
                continue
            
            # 결과 준비
            result_text = f"{keyword}, {title}, {body}"
            pyperclip.copy(result_text)
            
            print(f"\n추출 완료!")
            print(f"제목: {title}")
            print(f"본문: {len(body)}자")
            print("결과가 클립보드에 복사되었습니다.")
            
            # 브라우저 열기
            if first_time:
                print("브라우저를 열고 있습니다...")
                webbrowser.open(CHATBOT_URL, new=0)
                first_time = False
            
            print("Ctrl+V로 붙여넣기하세요.\n")
            
        except Exception as e:
            print(f"추출 실패: {e}")
            print("원문 보기 버튼이나 다른 뉴스 사이트를 시도해보세요.\n")

if __name__ == "__main__":
    main() 