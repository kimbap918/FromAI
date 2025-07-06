import sys
import os
import time
import io
import re
import platform
import subprocess
from datetime import datetime
from PIL import Image
import pyperclip
import webbrowser
import requests
from bs4 import BeautifulSoup
from newspaper import Article
from urllib.parse import urljoin

# PyQt5 imports
from PyQt5.QtWidgets import (QApplication, QMainWindow, QTabWidget, QWidget, 
                             QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
                             QPushButton, QTextEdit, QScrollArea, QFrame,
                             QMessageBox, QProgressBar, QGroupBox)
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QPixmap, QFont, QPalette, QColor

# Selenium imports
# selenium과 webdriver-manager가 설치되어 있는지 확인합니다.
# 설치 명령어: pip install selenium webdriver-manager
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

# Windows clipboard imports
try:
    import win32clipboard
    import win32con
    CLIPBOARD_AVAILABLE = True
except ImportError:
    CLIPBOARD_AVAILABLE = False

# 빌드된 exe에서 실행될 때 경로 설정
def get_resource_path(relative_path):
    """빌드된 exe에서 리소스 경로를 올바르게 가져오는 함수"""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    
    return os.path.join(base_path, relative_path)

# 설정
CHATBOT_URL = "https://chatgpt.com/g/g-67abdb7e8f1c8191978db654d8a57b86-gisa-jaeguseong-caesbos?model=gpt-4o"
INFO_CHATBOT_URL = "https://chatgpt.com/g/g-67abdb7e8f1c8191978db654d8a57b86-gisa-jaeguseong-caesbos?model=gpt-4o"
MIN_BODY_LENGTH = 300

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'ko-KR,ko;q=0.8,en-US;q=0.5,en;q=0.3',
}





def initialize_driver(headless=True):
    """
    Selenium Chrome 드라이버 인스턴스를 초기화하고 반환합니다.
    Selenium Manager를 사용하여 드라이버를 자동으로 관리하고, 안정성을 높인 옵션을 적용합니다.
    """
    if not SELENIUM_AVAILABLE:
        raise Exception("Selenium 라이브러리가 설치되지 않았습니다. 'pip install selenium'으로 설치해주세요.")

    options = Options()
    options.add_argument('--start-maximized')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-software-rasterizer')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--log-level=3')
    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    options.add_experimental_option('useAutomationExtension', False)
    
    if headless:
        options.add_argument("--headless=new")

    try:
        # Service() 객체를 인자 없이 생성하면 Selenium Manager가 자동으로 드라이버를 관리합니다.
        # 이것이 가장 최신이고 안정적인 방법입니다.
        service = Service()
        driver = webdriver.Chrome(service=service, options=options)
        return driver
    except Exception as e:
        # 오류 메시지를 더 구체적으로 개선
        if 'WinError 193' in str(e):
            selenium_cache_path = os.path.join(os.path.expanduser('~'), '.cache', 'selenium')
            wdm_cache_path = os.path.join(os.path.expanduser('~'), '.wdm')
            
            error_msg = (
                f"크롬드라이버 실행에 실패했습니다. (WinError 193)\n\n"
                "이 오류는 시스템에 캐시된 크롬드라이버 파일이 손상되었을 때 주로 발생합니다.\n\n"
                "**가장 확실한 해결 방법:**\n"
                "1. 아래 경로의 폴더를 **전부 삭제**하여 드라이버 캐시를 초기화하세요.\n"
                f"   - Selenium 캐시: {selenium_cache_path}\n"
                f"   - Webdriver-Manager 캐시: {wdm_cache_path}\n"
                "   (위 폴더들을 삭제해도 안전합니다)\n"
                "2. 프로그램을 다시 실행하여 드라이버를 새로 다운로드 받으세요."
            )
        else:
            error_msg = f"크롬드라이버 실행에 실패했습니다.\n\n"
            error_msg += f"오류: {e}\n\n"
            error_msg += "해결 방법:\n1. 크롬 브라우저를 최신 버전으로 업데이트해주세요.\n2. 프로그램을 관리자 권한으로 실행해보세요.\n3. 인터넷 연결을 확인하세요."
        raise Exception(error_msg)

class NewsWorker(QThread):
    finished = pyqtSignal(str, str, str)  # title, body, error
    progress = pyqtSignal(str)
    
    def __init__(self, url, keyword):
        super().__init__()
        self.url = url
        self.keyword = keyword
    
    def run(self):
        try:
            self.progress.emit("기사 추출 중...")
            title, body = self.extract_article_content(self.url)
            
            if len(body) < MIN_BODY_LENGTH:
                self.finished.emit("", "", "본문이 너무 짧습니다. 다른 링크를 시도해보세요.")
                return
            
            result_text = f"{self.keyword}, {title}, {body}"
            pyperclip.copy(result_text)
            
            self.finished.emit(title, body, "")
            
        except Exception as e:
            error_msg = f"추출 실패: {str(e)}"
            self.progress.emit(f"오류 발생: {error_msg}")
            self.finished.emit("", "", error_msg)
    
    def extract_article_content(self, url):
        """통합 기사 추출"""
        extractors = [
            ("newspaper", self.extract_with_newspaper),
            ("스마트 파서", self.extract_with_smart_parser),
            ("강화 스마트 파서", self.extract_with_enhanced_smart_parser),
            ("iframe", self.extract_with_iframe),
        ]
        
        if SELENIUM_AVAILABLE:
            extractors.append(("Selenium", self.extract_with_selenium))
        
        last_error = None
        for name, extractor in extractors:
            try:
                self.progress.emit(f"{name} 시도 중...")
                title, body = extractor(url)
                
                if len(body) >= MIN_BODY_LENGTH:
                    self.progress.emit(f"{name} 성공: {len(body)}자")
                    return title, body
                else:
                    self.progress.emit(f"{name} 실패: 본문 너무 짧음 ({len(body)}자)")
                    
            except Exception as e:
                last_error = e
                self.progress.emit(f"{name} 실패: {e}")
        
        if last_error:
            raise Exception(f"모든 추출 방법이 실패했습니다. 마지막 오류: {last_error}")
        else:
            raise Exception("모든 추출 방법이 실패했습니다")
    
    def extract_with_newspaper(self, url):
        """newspaper 라이브러리를 사용한 기본 추출"""
        try:
            self.progress.emit("newspaper: Article 객체 생성 중...")
            article = Article(url, language='ko')
            
            self.progress.emit("newspaper: 기사 다운로드 중...")
            article.download()
            
            self.progress.emit("newspaper: 기사 파싱 중...")
            article.parse()
            
            title = article.title.strip() if article.title else "제목 없음"
            body = article.text.strip() if article.text else ""
            
            self.progress.emit(f"newspaper: 제목 길이 {len(title)}, 본문 길이 {len(body)}")
            
            if len(body) < MIN_BODY_LENGTH:
                raise ValueError(f"본문이 너무 짧음: {len(body)}자")
            
            return title, body
            
        except Exception as e:
            self.progress.emit(f"newspaper 상세 오류: {str(e)}")
            raise e
    
    def extract_with_smart_parser(self, url):
        """범용 스마트 기사 추출"""
        try:
            headers = HEADERS.copy()
            headers['Referer'] = url
            
            self.progress.emit("스마트 파서: 웹페이지 요청 중...")
            res = requests.get(url, headers=headers, timeout=30)
            res.raise_for_status()  # HTTP 오류 체크
            
            self.progress.emit("스마트 파서: HTML 파싱 중...")
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
                body = self.extract_by_pattern(soup)
            
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
        except Exception as e:
            self.progress.emit(f"스마트 파서 오류: {e}")
            raise
    
    def extract_with_enhanced_smart_parser(self, url):
        """강화된 스마트 기사 추출 (newspaper 실패 시 대안)"""
        try:
            headers = HEADERS.copy()
            headers['Referer'] = url

            self.progress.emit("강화 스마트 파서: 웹페이지 요청 중...")
            res = requests.get(url, headers=headers, timeout=30)
            res.raise_for_status()  # HTTP 오류 체크

            self.progress.emit("강화 스마트 파서: HTML 파싱 중...")
            soup = BeautifulSoup(res.text, 'html.parser')

            # 더 많은 제목 셀렉터 추가
            title_selectors = [
                'h1', 'h2.media_end_head_headline', '.articleSubject',
                '.title', '.article-title', '.news-title', '.post-title',
                'h1.article_title', 'h2.article_title', '.headline',
                '.article-headline', '.news-headline', '.post-headline',
                'h1.entry-title', 'h2.entry-title', '.entry-title',
                'h1.page-title', 'h2.page-title', '.page-title'
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

            # 더 많은 본문 셀렉터 추가
            body_selectors = [
                'article#dic_area', '.articleBody', '.article_body',
                '.article-content', '.news-content', '.view_content',
                '.content', '.post-content', 'article', '.entry-content',
                '.article-text', '.news-text', '.post-text',
                '.article-main', '.news-main', '.post-main',
                '.article-detail', '.news-detail', '.post-detail',
                '.article-wrapper', '.news-wrapper', '.post-wrapper',
                '.article-container', '.news-container', '.post-container'
            ]

            body = ""
            for selector in body_selectors:
                body_area = soup.select_one(selector)
                if body_area:
                    # 불필요한 요소 제거
                    for unwanted in body_area.find_all([
                        'script', 'style', 'nav', 'aside', 'footer', 'header',
                        '.ad', '.advertisement', '.related', '.comment', '.social',
                        '.sidebar', '.widget', '.banner', '.popup', '.modal'
                    ]):
                        unwanted.decompose()

                    body = body_area.get_text(separator="\n").strip()
                    if len(body) > 200:
                        break

            # CSS 셀렉터 실패 시 패턴 기반 추출
            if len(body) < 200:
                body = self.extract_by_pattern(soup)

            # 제목 중복 제거
            if title != "제목 없음" and title in body:
                body = body.replace(title, '', 1).strip()

            # 제목이 없으면 본문에서 추출
            if title == "제목 없음" and body:
                first_lines = body.split('\n')[:5]  # 3개에서 5개로 증가
                for line in first_lines:
                    if 10 <= len(line) <= 150 and '=' not in line and '기자' not in line:
                        title = line
                        body = body.replace(line, '', 1).strip()
                        break

            return title, body
        except Exception as e:
            self.progress.emit(f"강화 스마트 파서 오류: {e}")
            raise
    
    def extract_by_pattern(self, soup):
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
    
    def extract_with_iframe(self, url):
        """iframe 기반 추출"""
        try:
            self.progress.emit("iframe: 웹페이지 요청 중...")
            res = requests.get(url, headers=HEADERS, timeout=30)
            res.raise_for_status()  # HTTP 오류 체크
            
            self.progress.emit("iframe: HTML 파싱 중...")
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
        except Exception as e:
            self.progress.emit(f"iframe 추출 오류: {e}")
            raise
    
    def extract_with_selenium(self, url):
        """Selenium 기반 추출"""
        driver = None
        try:
            driver = initialize_driver(headless=True)
            driver.get(url)
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            
            title = driver.title
            body = driver.find_element(By.TAG_NAME, "body").text.strip()
            
            return title, body
        finally:
            if driver:
                driver.quit()

class ExchangeWorker(QThread):
    finished = pyqtSignal(str, str)  # image_path, error
    progress = pyqtSignal(str)
    
    def __init__(self, keyword):
        super().__init__()
        self.keyword = keyword
    
    def run(self):
        try:
            self.progress.emit("환율 차트 캡처 중...")
            image_path = self.capture_exchange_chart(self.keyword)
            
            if image_path:
                self.finished.emit(image_path, "")
            else:
                self.finished.emit("", "환율 차트 캡처에 실패했습니다.")
                
        except Exception as e:
            self.finished.emit("", f"오류 발생: {str(e)}")
    
    def copy_image_to_clipboard(self, image_path):
        if not CLIPBOARD_AVAILABLE:
            return False
        try:
            image = Image.open(image_path).convert('RGB')
            output = io.BytesIO()
            image.save(output, 'BMP')
            data = output.getvalue()[14:]
            output.close()
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32con.CF_DIB, data)
            win32clipboard.CloseClipboard()
            return True
        except:
            try:
                win32clipboard.CloseClipboard()
            except:
                pass
            return False
    
    def capture_exchange_chart(self, keyword):
        driver = None
        try:
            driver = initialize_driver(headless=True)
            url = f"https://search.naver.com/search.naver?query={keyword}"
            driver.get(url)
            WebDriverWait(driver, 10).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            time.sleep(1)  # 0.2초에서 1초로 복원

            try:
                top = driver.find_element(By.CSS_SELECTOR, "div.exchange_top.up")
                bottom = driver.find_element(By.CSS_SELECTOR, "div.invest_wrap")
            except Exception as e:
                print(f"환율 차트 요소를 찾을 수 없습니다: {e}")
                return None

            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", top)
            time.sleep(0.5)  # 0.2초에서 0.5초로 복원

            zoom = driver.execute_script("return window.devicePixelRatio || 1;")
            start_y = int(top.location['y'] * zoom)
            end_y = int((bottom.location['y'] + bottom.size['height']) * zoom)

            # 정밀 보정값 적용
            left_offset = 395
            crop_width = 670
            top_offset = -5
            bottom_trim = 20

            # 전체 페이지 스크린샷을 메모리에서 바로 처리
            screenshot_bytes = driver.get_screenshot_as_png()
            image = Image.open(io.BytesIO(screenshot_bytes))

            top_coord = max(0, start_y + top_offset)
            bottom_coord = min(image.height, end_y - bottom_trim)

            cropped = image.crop((left_offset, top_coord, left_offset + crop_width, bottom_coord))

            # 통화코드 추출
            if top.text is None:
                currency = "환율"
            else:
                try:
                    currency = top.text.split('\n')[0].strip().replace(' ', '')
                    if not currency:
                        currency = "환율"
                except:
                    currency = "환율"
            
            today = datetime.now().strftime('%Y%m%d')
            folder = os.path.join("환율차트", today)
            os.makedirs(folder, exist_ok=True)
            filename = f"{today}_{currency}_환율차트.png"
            output_path = os.path.join(folder, filename)
            cropped.save(output_path)
            
            self.copy_image_to_clipboard(output_path)
            return output_path

        except Exception as e:
            print(f"오류 발생: {e}")
            return None
        finally:
            try:
                driver.quit()
            except:
                pass

class StockWorker(QThread):
    finished = pyqtSignal(str, str)  # image_path, error
    progress = pyqtSignal(str)
    
    def __init__(self, keyword):
        super().__init__()
        self.keyword = keyword
    
    def run(self):
        try:
            self.progress.emit("주식 코드 검색 중...")
            stock_code = self.get_stock_info_from_search(self.keyword)
            
            if not stock_code:
                self.finished.emit("", "주식 코드를 찾을 수 없습니다.")
                return
            
            self.progress.emit("주식 차트 캡처 중...")
            image_path = self.capture_wrap_company_area(stock_code)
            
            if image_path:
                self.finished.emit(image_path, "")
            else:
                self.finished.emit("", "주식 차트 캡처에 실패했습니다.")
                
        except Exception as e:
            self.finished.emit("", f"오류 발생: {str(e)}")
    
    def copy_image_to_clipboard(self, image_path):
        if not CLIPBOARD_AVAILABLE:
            return False
        try:
            image = Image.open(image_path).convert('RGB')
            output = io.BytesIO()
            image.save(output, 'BMP')
            data = output.getvalue()[14:]
            output.close()
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32con.CF_DIB, data)
            win32clipboard.CloseClipboard()
            return True
        except:
            try:
                win32clipboard.CloseClipboard()
            except:
                pass
            return False
    
    def open_image(self, path):
        try:
            if platform.system() == "Windows":
                os.startfile(path)
            elif platform.system() == "Darwin":
                subprocess.run(["open", path])
            elif platform.system() == "Linux":
                subprocess.run(["xdg-open", path])
        except:
            pass
    
    def wait_for_page_load(self, driver, timeout=10):  # 5초에서 10초로 복원
        try:
            WebDriverWait(driver, timeout).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except:
            pass
    
    def has_tab_elements(self, driver):
        return bool(driver.find_elements(By.CSS_SELECTOR, "a.top_tab_link"))
    
    def click_krx_tab(self, driver):
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, "a.top_tab_link")
            for el in elements:
                if 'KRX' in el.text.upper() and el.is_displayed():
                    driver.execute_script("arguments[0].click();", el)
                    time.sleep(0.2)  # 0.1초에서 0.2초로 복원
                    return True
        except:
            pass
        return False
    
    def find_wrap_company_element(self, driver):
        selectors = ["div.wrap_company", "div[class='wrap_company']", "div[class*='wrap_company']", ".wrap_company"]
        for selector in selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                for el in elements:
                    if el.is_displayed():
                        return el
            except:
                continue
        return None
    
    def extract_stock_name(self, driver):
        try:
            el = driver.find_element(By.CSS_SELECTOR, "div.wrap_company h2 a")
            if el.text is None:
                return "Unknown"
            name = el.text.strip()
            if name:
                return name
        except:
            pass
        return "Unknown"
    
    def generate_output_path(self, stock_code: str, stock_name: str, base_folder: str = "주식차트") -> str:
        today = datetime.now().strftime("%Y%m%d")
        folder = os.path.join(base_folder, today)
        os.makedirs(folder, exist_ok=True)
        
        # stock_name이 None이거나 빈 문자열인 경우 처리
        if stock_name is None or not stock_name.strip():
            stock_name = "Unknown"
        
        clean_name = stock_name.replace(" ", "").replace("/", "_").replace("\\", "_")
        filename = f"{stock_code}_{clean_name}.png"
        return os.path.join(folder, filename)
    
    def capture_wrap_company_area(self, stock_code: str) -> str:
        driver = None
        try:
            driver = initialize_driver(headless=True)
            url = f"https://finance.naver.com/item/main.naver?code={stock_code}"
            driver.get(url)
            self.wait_for_page_load(driver, 10)  # 5초에서 10초로 복원
            time.sleep(0.3)  # 0.1초에서 0.3초로 복원

            stock_name = self.extract_stock_name(driver)

            if self.has_tab_elements(driver):
                self.click_krx_tab(driver)
                time.sleep(0.3)  # 0.1초에서 0.3초로 복원

            el = self.find_wrap_company_element(driver)
            if not el:
                print("wrap_company 요소를 찾지 못했습니다.")
                return None

            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
            time.sleep(0.3)  # 0.1초에서 0.3초로 복원

            screenshot_path = os.path.abspath("full_screenshot.png")
            driver.save_screenshot(screenshot_path)

            location = el.location
            zoom = driver.execute_script("return window.devicePixelRatio || 1;")
            start_x = int(location['x'] * zoom)
            start_y = int(location['y'] * zoom)
            width, height = 700, 515
            left = max(0, start_x)
            top = max(0, start_y)
            right = left + width
            bottom = top + height

            image = Image.open(screenshot_path)
            right = min(right, image.width)
            bottom = min(bottom, image.height)
            left = max(0, right - width)
            top = max(0, bottom - height)
            cropped = image.crop((left, top, right, bottom))

            output_path = self.generate_output_path(stock_code, stock_name)
            cropped.save(output_path)

            if os.path.exists(screenshot_path):
                os.remove(screenshot_path)

            self.copy_image_to_clipboard(output_path)
            return output_path

        except Exception as e:
            print(f"오류 발생: {e}")
            return None
        finally:
            try:
                driver.quit()
            except:
                pass
    
    def get_stock_info_from_search(self, keyword: str):
        if keyword.isdigit() and len(keyword) == 6:
            return keyword

        driver = None
        try:
            driver = initialize_driver(headless=True)
            search_url = f"https://search.naver.com/search.naver?query={keyword}+주식"
            print(f" 검색 시도: {search_url}")
            driver.get(search_url)
            time.sleep(0.5)  # 0.2초에서 0.5초로 복원

            finance_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='finance.naver.com/item/main']")
            for link in finance_links:
                href = link.get_attribute('href')
                match = re.search(r"code=(\d{6})", href)
                if match:
                    stock_code = match.group(1)
                    print(f" 코드 추출 성공: {stock_code}")
                    return stock_code

            return None
        except Exception as e:
            print(f" 검색 중 오류: {e}")
            return None
        finally:
            if driver:
                driver.quit()

class NewsTab(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.worker = None
        self.first_time = True
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        # 제목
        title_label = QLabel("📰 뉴스 재구성")
        title_label.setFont(QFont("Arial", 16, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        # 입력 그룹
        input_group = QGroupBox("입력")
        input_layout = QVBoxLayout()
        
        # URL 입력
        url_layout = QHBoxLayout()
        url_label = QLabel("기사 URL:")
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://...")
        url_layout.addWidget(url_label)
        url_layout.addWidget(self.url_input)
        input_layout.addLayout(url_layout)
        
        # 키워드 입력
        keyword_layout = QHBoxLayout()
        keyword_label = QLabel("키워드:")
        self.keyword_input = QLineEdit()
        self.keyword_input.setPlaceholderText("예: AI, 경제, 기술...")
        keyword_layout.addWidget(keyword_label)
        keyword_layout.addWidget(self.keyword_input)
        input_layout.addLayout(keyword_layout)
        
        # 엔터키 이벤트 연결
        self.url_input.returnPressed.connect(self.extract_news)
        self.keyword_input.returnPressed.connect(self.extract_news)
        
        input_group.setLayout(input_layout)
        layout.addWidget(input_group)
        
        # 버튼
        button_layout = QHBoxLayout()
        self.extract_btn = QPushButton("📄 기사 추출")
        self.extract_btn.clicked.connect(self.extract_news)
        self.cancel_btn = QPushButton("❌ 취소")
        self.cancel_btn.clicked.connect(self.cancel_extraction)
        self.cancel_btn.setEnabled(False)  # 초기에는 비활성화
        self.open_chatbot_btn = QPushButton("🌐 챗봇 열기")
        self.open_chatbot_btn.clicked.connect(self.open_chatbot)
        button_layout.addWidget(self.extract_btn)
        button_layout.addWidget(self.cancel_btn)
        button_layout.addWidget(self.open_chatbot_btn)
        layout.addLayout(button_layout)
        
        # 진행률 표시
        self.progress_label = QLabel("")
        self.progress_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.progress_label)
        
        # 결과 표시
        result_group = QGroupBox("결과")
        result_layout = QVBoxLayout()
        
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setMaximumHeight(200)
        result_layout.addWidget(self.result_text)
        
        # 복사하기 버튼 추가
        copy_button_layout = QHBoxLayout()
        self.copy_result_btn = QPushButton("📋 복사하기")
        self.copy_result_btn.clicked.connect(self.copy_result)
        self.copy_result_btn.setEnabled(False)  # 초기에는 비활성화
        copy_button_layout.addWidget(self.copy_result_btn)
        result_layout.addLayout(copy_button_layout)
        
        result_group.setLayout(result_layout)
        layout.addWidget(result_group)
        
        self.setLayout(layout)
    
    def extract_news(self):
        url = self.url_input.text().strip()
        keyword = self.keyword_input.text().strip()
        
        if not url or not keyword:
            QMessageBox.warning(self, "입력 오류", "URL과 키워드를 모두 입력해주세요.")
            return
        
        self.extract_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)  # 취소 버튼 활성화
        self.copy_result_btn.setEnabled(False)  # 복사하기 버튼 비활성화
        self.progress_label.setText("처리 중...")
        self.result_text.clear()
        
        self.worker = NewsWorker(url, keyword)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.on_extraction_finished)
        self.worker.start()
    
    def update_progress(self, message):
        self.progress_label.setText(message)
    
    def on_extraction_finished(self, title, body, error):
        self.extract_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)  # 취소 버튼 비활성화
        
        if error:
            self.progress_label.setText("")
            QMessageBox.warning(self, "추출 실패", error)
            self.copy_result_btn.setEnabled(False)
            return
        
        self.progress_label.setText("추출 완료! 클립보드에 복사되었습니다.")
        
        # 결과를 그대로 표시 (키워드, 제목, 본문)
        result_text = f"{self.keyword_input.text().strip()}, {title}, {body}"
        self.result_text.setText(result_text)
        
        # 복사하기 버튼 활성화
        self.copy_result_btn.setEnabled(True)
    
    def open_chatbot(self):
        webbrowser.open(CHATBOT_URL, new=0)
        QMessageBox.information(self, "챗봇 열기", "챗봇이 열렸습니다. Ctrl+V로 붙여넣기하세요.")

    def copy_result(self):
        text = self.result_text.toPlainText()
        pyperclip.copy(text)
        QMessageBox.information(self, "복사 완료", "결과가 클립보드에 복사되었습니다.")

    def cancel_extraction(self):
        self.worker.terminate()
        self.progress_label.setText("취소됨")
        self.extract_btn.setEnabled(True)
        self.copy_result_btn.setEnabled(False)

class ExchangeTab(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.worker = None
        self.last_image_path = None
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        # 제목
        title_label = QLabel("💱 환율 차트")
        title_label.setFont(QFont("Arial", 16, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        # 입력 그룹
        input_group = QGroupBox("입력")
        input_layout = QVBoxLayout()
        
        # 키워드 입력
        keyword_layout = QHBoxLayout()
        keyword_label = QLabel("환율 키워드:")
        self.keyword_input = QLineEdit()
        self.keyword_input.setPlaceholderText("예: 달러환율, 유로환율, 엔환율...")
        keyword_layout.addWidget(keyword_label)
        keyword_layout.addWidget(self.keyword_input)
        input_layout.addLayout(keyword_layout)
        
        # 엔터키 이벤트 연결
        self.keyword_input.returnPressed.connect(self.capture_chart)
        
        input_group.setLayout(input_layout)
        layout.addWidget(input_group)
        
        # 버튼들
        button_layout = QHBoxLayout()
        self.capture_btn = QPushButton("📊 차트 캡처")
        self.capture_btn.clicked.connect(self.capture_chart)
        self.cancel_btn = QPushButton("❌ 취소")
        self.cancel_btn.clicked.connect(self.cancel_capture)
        self.cancel_btn.setEnabled(False)  # 초기에는 비활성화
        self.open_folder_btn = QPushButton("📁 폴더 열기")
        self.open_folder_btn.clicked.connect(self.open_folder)
        self.open_chatbot_btn = QPushButton("🌐 챗봇 열기")
        self.open_chatbot_btn.clicked.connect(self.open_chatbot)
        
        button_layout.addWidget(self.capture_btn)
        button_layout.addWidget(self.cancel_btn)
        button_layout.addWidget(self.open_folder_btn)
        button_layout.addWidget(self.open_chatbot_btn)
        layout.addLayout(button_layout)
        
        # 진행률 표시
        self.progress_label = QLabel("")
        self.progress_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.progress_label)
        
        # 결과 표시
        result_group = QGroupBox("결과")
        result_layout = QVBoxLayout()
        
        self.result_label = QLabel("")
        self.result_label.setAlignment(Qt.AlignCenter)
        result_layout.addWidget(self.result_label)
        
        result_group.setLayout(result_layout)
        layout.addWidget(result_group)
        
        self.setLayout(layout)
    
    def open_folder(self):
        """환율차트 폴더 열기"""
        today = datetime.now().strftime('%Y%m%d')
        folder_path = os.path.join("환율차트", today)
        
        if os.path.exists(folder_path):
            if platform.system() == "Windows":
                os.startfile(folder_path)
            elif platform.system() == "Darwin":
                subprocess.run(["open", folder_path])
            elif platform.system() == "Linux":
                subprocess.run(["xdg-open", folder_path])
        else:
            QMessageBox.information(self, "폴더 없음", "아직 캡처된 이미지가 없습니다.")
    
    def open_chatbot(self):
        """정보성 기사 챗봇 열기"""
        webbrowser.open(INFO_CHATBOT_URL, new=0)
        QMessageBox.information(self, "챗봇 열기", "정보성 기사 챗봇이 열렸습니다.")
    
    def capture_chart(self):
        keyword = self.keyword_input.text().strip()
        
        if not keyword:
            QMessageBox.warning(self, "입력 오류", "환율 키워드를 입력해주세요.")
            return
        
        self.capture_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)  # 취소 버튼 활성화
        self.progress_label.setText("처리 중...")
        self.result_label.setText("")
        
        self.worker = ExchangeWorker(keyword)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.on_capture_finished)
        self.worker.start()
    
    def update_progress(self, message):
        self.progress_label.setText(message)
    
    def on_capture_finished(self, image_path, error):
        self.capture_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)  # 취소 버튼 비활성화
        
        if error:
            self.progress_label.setText("")
            QMessageBox.warning(self, "캡처 실패", error)
            return
        
        self.last_image_path = image_path
        self.progress_label.setText("캡처 완료!")
        self.result_label.setText(f"저장됨: {image_path}\n이미지가 클립보드에 복사되었습니다.")

    def cancel_capture(self):
        self.worker.terminate()
        self.progress_label.setText("취소됨")
        self.capture_btn.setEnabled(True)

class StockTab(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.worker = None
        self.last_image_path = None
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        # 제목
        title_label = QLabel("📈 주식 차트")
        title_label.setFont(QFont("Arial", 16, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        # 입력 그룹
        input_group = QGroupBox("입력")
        input_layout = QVBoxLayout()
        
        # 키워드 입력
        keyword_layout = QHBoxLayout()
        keyword_label = QLabel("주식 코드 또는 회사명:")
        self.keyword_input = QLineEdit()
        self.keyword_input.setPlaceholderText("예: 005930, 삼성전자...")
        keyword_layout.addWidget(keyword_label)
        keyword_layout.addWidget(self.keyword_input)
        input_layout.addLayout(keyword_layout)
        
        # 엔터키 이벤트 연결
        self.keyword_input.returnPressed.connect(self.capture_chart)
        
        input_group.setLayout(input_layout)
        layout.addWidget(input_group)
        
        # 버튼들
        button_layout = QHBoxLayout()
        self.capture_btn = QPushButton("📊 차트 캡처")
        self.capture_btn.clicked.connect(self.capture_chart)
        self.cancel_btn = QPushButton("❌ 취소")
        self.cancel_btn.clicked.connect(self.cancel_capture)
        self.cancel_btn.setEnabled(False)  # 초기에는 비활성화
        self.open_folder_btn = QPushButton("📁 폴더 열기")
        self.open_folder_btn.clicked.connect(self.open_folder)
        self.open_chatbot_btn = QPushButton("🌐 챗봇 열기")
        self.open_chatbot_btn.clicked.connect(self.open_chatbot)
        button_layout.addWidget(self.capture_btn)
        button_layout.addWidget(self.cancel_btn)
        button_layout.addWidget(self.open_folder_btn)
        button_layout.addWidget(self.open_chatbot_btn)
        layout.addLayout(button_layout)
        
        # 진행률 표시
        self.progress_label = QLabel("")
        self.progress_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.progress_label)
        
        # 결과 표시
        result_group = QGroupBox("결과")
        result_layout = QVBoxLayout()
        
        self.result_label = QLabel("")
        self.result_label.setAlignment(Qt.AlignCenter)
        result_layout.addWidget(self.result_label)
        
        result_group.setLayout(result_layout)
        layout.addWidget(result_group)
        
        self.setLayout(layout)
    
    def open_folder(self):
        today = datetime.now().strftime('%Y%m%d')
        folder_path = os.path.join("주식차트", today)
        if os.path.exists(folder_path):
            if platform.system() == "Windows":
                os.startfile(folder_path)
            elif platform.system() == "Darwin":
                subprocess.run(["open", folder_path])
            elif platform.system() == "Linux":
                subprocess.run(["xdg-open", folder_path])
        else:
            QMessageBox.information(self, "폴더 없음", "아직 캡처된 이미지가 없습니다.")
    
    def open_chatbot(self):
        webbrowser.open(INFO_CHATBOT_URL, new=0)
        QMessageBox.information(self, "챗봇 열기", "정보성 기사 챗봇이 열렸습니다.")
    
    def capture_chart(self):
        keyword = self.keyword_input.text().strip()
        
        if not keyword:
            QMessageBox.warning(self, "입력 오류", "주식 코드 또는 회사명을 입력해주세요.")
            return
        
        self.capture_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)  # 취소 버튼 활성화
        self.progress_label.setText("처리 중...")
        self.result_label.setText("")
        
        self.worker = StockWorker(keyword)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.on_capture_finished)
        self.worker.start()
    
    def update_progress(self, message):
        self.progress_label.setText(message)
    
    def on_capture_finished(self, image_path, error):
        self.capture_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)  # 취소 버튼 비활성화
        
        if error:
            self.progress_label.setText("")
            QMessageBox.warning(self, "캡처 실패", error)
            return
        
        self.last_image_path = image_path
        self.progress_label.setText("캡처 완료!")
        self.result_label.setText(f"저장됨: {image_path}\n이미지가 클립보드에 복사되었습니다.")

    def cancel_capture(self):
        self.worker.terminate()
        self.progress_label.setText("취소됨")
        self.capture_btn.setEnabled(True)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.init_ui()
    
    def init_ui(self):
        self.setWindowTitle("통합 뉴스 도구 - 제작자: 최준혁(kimbap918)")
        self.setGeometry(100, 100, 800, 600)
        
        # 중앙 위젯
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 메인 레이아웃
        layout = QVBoxLayout()
        
        # 탭 위젯
        self.tab_widget = QTabWidget()
        
        # 탭들 추가
        self.news_tab = NewsTab()
        self.exchange_tab = ExchangeTab()
        self.stock_tab = StockTab()
        
        self.tab_widget.addTab(self.news_tab, "📰 뉴스 재구성")
        self.tab_widget.addTab(self.exchange_tab, "💱 환율 차트")
        self.tab_widget.addTab(self.stock_tab, "📈 주식 차트")
        
        layout.addWidget(self.tab_widget)
        
        # 상태 표시
        status_label = QLabel("")
        if not SELENIUM_AVAILABLE:
            status_label.setText("⚠️ Selenium이 설치되지 않았습니다. 일부 기능이 제한될 수 있습니다.")
        elif not CLIPBOARD_AVAILABLE:
            status_label.setText("⚠️ 클립보드 기능이 제한됩니다.")
        else:
            status_label.setText("✅ 모든 기능이 준비되었습니다.")
        
        status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(status_label)
        
        # 제작자 정보
        creator_label = QLabel("제작자: 최준혁")
        creator_label.setAlignment(Qt.AlignCenter)
        creator_label.setStyleSheet("color: gray; font-size: 10px; margin-top: 5px;")
        layout.addWidget(creator_label)
        
        central_widget.setLayout(layout)

def main():
    app = QApplication(sys.argv)
    
    # 스타일 설정
    app.setStyle('Fusion')
    
    # 폰트 설정
    font = QFont("Arial", 9)
    app.setFont(font)
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main() 