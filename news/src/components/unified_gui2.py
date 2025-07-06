import sys
import os
import time
import io
import re
import platform
import subprocess
import shutil
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
# pywin32가 설치되어 있는지 확인합니다.
# 설치 명령어: pip install pywin32
try:
    import win32clipboard
    import win32con
    CLIPBOARD_AVAILABLE = True
except ImportError:
    CLIPBOARD_AVAILABLE = False

# 설정
CHATBOT_URL = "https://chatgpt.com/g/g-67abdb7e8f1c8191978db654d8a57b86-gisa-jaeguseong-caesbos?model=gpt-4o"
INFO_CHATBOT_URL = "https://chatgpt.com/g/g-67abdb7e8f1c8191978db654d8a57b86-gisa-jaeguseong-caesbos?model=gpt-4o"
MIN_BODY_LENGTH = 300

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'ko-KR,ko;q=0.8,en-US;q=0.5,en;q=0.3',
}

def get_chrome_version():
    """Windows 환경에서 설치된 크롬 브라우저의 버전을 감지합니다."""
    try:
        process = subprocess.Popen(
            ['reg', 'query', r'HKEY_CURRENT_USER\Software\Google\Chrome\BLBeacon', '/v', 'version'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW
        )
        stdout, _ = process.communicate()
        match = re.search(r'version\s+REG_SZ\s+([\d.]+)', stdout)
        if match:
            return match.group(1)
    except Exception:
        pass
    return None

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
            chrome_version = get_chrome_version()
            error_msg = f"크롬드라이버 실행에 실패했습니다.\n\n"
            if chrome_version:
                error_msg += f"현재 크롬 버전: {chrome_version}\n"
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
                self.finished.emit("", "", f"본문이 너무 짧습니다 ({len(body)}자). 다른 링크를 시도해보세요.")
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
                
                if title and body and len(body) >= MIN_BODY_LENGTH:
                    self.progress.emit(f"{name} 성공: {len(body)}자")
                    return title, body
                else:
                    self.progress.emit(f"{name} 실패: 본문이 너무 짧거나 내용이 없습니다 ({len(body)}자)")
                    
            except Exception as e:
                last_error = e
                self.progress.emit(f"{name} 실패: {e}")
        
        if last_error:
            raise Exception(f"모든 추출 방법이 실패했습니다. 마지막 오류: {last_error}")
        else:
            raise Exception("모든 추출 방법이 실패했으며, 유효한 기사 내용을 찾을 수 없습니다.")
    
    def extract_with_newspaper(self, url):
        """newspaper 라이브러리를 사용한 기본 추출"""
        try:
            article = Article(url, language='ko')
            article.download()
            article.parse()
            title = article.title.strip() if article.title else "제목 없음"
            body = article.text.strip() if article.text else ""
            if len(body) < MIN_BODY_LENGTH:
                raise ValueError(f"본문이 너무 짧음: {len(body)}자")
            return title, body
        except Exception as e:
            raise e
    
    def extract_with_smart_parser(self, url):
        """범용 스마트 기사 추출"""
        try:
            res = requests.get(url, headers=HEADERS, timeout=30)
            res.raise_for_status()
            soup = BeautifulSoup(res.text, 'html.parser')
            
            title = "제목 없음"
            title_selectors = ['h1', 'h2.media_end_head_headline', '.articleSubject', '.title', '.article-title', '.news-title', '.post-title']
            for selector in title_selectors:
                title_tag = soup.select_one(selector)
                if title_tag and len(title_tag.text.strip()) > 5:
                    title = title_tag.text.strip().split(' - ')[0].split(' | ')[0]
                    break
            
            body = ""
            body_selectors = ['article#dic_area', '.articleBody', '.article_body', '.article-content', '.news-content', '.view_content', '.content', '.post-content', 'article', '.entry-content']
            for selector in body_selectors:
                body_area = soup.select_one(selector)
                if body_area:
                    for unwanted in body_area.find_all(['script', 'style', 'nav', 'aside', 'footer', 'header', '.ad', '.advertisement', '.related', '.comment', '.social']):
                        unwanted.decompose()
                    body = body_area.get_text(separator="\n").strip()
                    if len(body) > 200:
                        break
            
            if title != "제목 없음" and title in body:
                body = body.replace(title, '', 1).strip()
            
            return title, body
        except Exception as e:
            raise e

    def extract_with_enhanced_smart_parser(self, url):
        """강화된 스마트 기사 추출"""
        try:
            res = requests.get(url, headers=HEADERS, timeout=30)
            res.raise_for_status()
            soup = BeautifulSoup(res.text, 'html.parser')

            title_selectors = [
                'h1', 'h2.media_end_head_headline', '.articleSubject', '.title', '.article-title', 
                '.news-title', '.post-title', 'h1.article_title', 'h2.article_title', '.headline'
            ]
            title = "제목 없음"
            for selector in title_selectors:
                title_tag = soup.select_one(selector)
                if title_tag and len(title_tag.text.strip()) > 5:
                    title = title_tag.text.strip().split(' - ')[0].split(' | ')[0]
                    break

            body_selectors = [
                'article#dic_area', '.articleBody', '.article_body', '.article-content', 
                '.news-content', '.view_content', '.content', '.post-content', 'article'
            ]
            body = ""
            for selector in body_selectors:
                body_area = soup.select_one(selector)
                if body_area:
                    for unwanted in body_area.find_all([
                        'script', 'style', 'nav', 'aside', 'footer', 'header', '.ad', 
                        '.advertisement', '.related', '.comment', '.social', '.sidebar'
                    ]):
                        unwanted.decompose()
                    body = body_area.get_text(separator="\n").strip()
                    if len(body) > 200:
                        break

            if title != "제목 없음" and title in body:
                body = body.replace(title, '', 1).strip()
            return title, body
        except Exception as e:
            raise e
    
    def extract_with_iframe(self, url):
        """iframe 기반 추출"""
        try:
            res = requests.get(url, headers=HEADERS, timeout=30)
            res.raise_for_status()
            soup = BeautifulSoup(res.text, 'html.parser')
            
            title_tag = soup.select_one('h2') or soup.select_one('title')
            title = title_tag.text.strip() if title_tag else "제목 없음"
            
            body = ""
            iframe_tags = soup.select("iframe[src*='proc_view_body']")
            
            for iframe in iframe_tags:
                iframe_src = iframe.get("src")
                if iframe_src:
                    iframe_url = urljoin(url, iframe_src)
                    try:
                        iframe_res = requests.get(iframe_url, headers=HEADERS)
                        iframe_soup = BeautifulSoup(iframe_res.text, 'html.parser')
                        body += "\n" + iframe_soup.get_text(separator="\n").strip()
                    except Exception:
                        continue
            
            return title, body.strip()
        except Exception as e:
            raise e
    
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
            self.progress.emit("클립보드 기능 사용 불가 (pywin32 미설치)")
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
        except Exception as e:
            self.progress.emit(f"클립보드 복사 실패: {e}")
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
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.exchange_top")))
            
            top = driver.find_element(By.CSS_SELECTOR, "div.exchange_top")
            bottom = driver.find_element(By.CSS_SELECTOR, "div.invest_wrap")

            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", top)
            time.sleep(0.5)

            screenshot_bytes = driver.get_screenshot_as_png()
            image = Image.open(io.BytesIO(screenshot_bytes))

            zoom = driver.execute_script("return window.devicePixelRatio || 1;")
            start_y = int(top.location['y'] * zoom)
            end_y = int((bottom.location['y'] + bottom.size['height']) * zoom)
            
            left_offset = 395 * zoom
            crop_width = 670 * zoom
            top_offset = -20 * zoom
            bottom_trim = 20 * zoom

            left = left_offset
            top_coord = max(0, start_y + top_offset)
            right = left + crop_width
            bottom_coord = min(image.height, end_y - bottom_trim)

            cropped = image.crop((left, top_coord, right, bottom_coord))

            currency_text = top.text.split('\n')[0].strip()
            currency = "".join(re.findall(r'[\w]+', currency_text)) or "환율"
            
            today = datetime.now().strftime('%Y%m%d')
            folder = os.path.join("환율차트", today)
            os.makedirs(folder, exist_ok=True)
            filename = f"{today}_{currency}_환율차트.png"
            output_path = os.path.join(folder, filename)
            cropped.save(output_path)
            
            if self.copy_image_to_clipboard(output_path):
                self.progress.emit("클립보드에 복사 완료!")
            return output_path
        finally:
            if driver:
                driver.quit()

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
                self.finished.emit("", f"'{self.keyword}'에 대한 주식 코드를 찾을 수 없습니다.")
                return
            
            self.progress.emit(f"주식 코드({stock_code})로 차트 캡처 중...")
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
        except Exception:
            try:
                win32clipboard.CloseClipboard()
            except:
                pass
            return False
    
    def open_image(self, path):
        try:
            if platform.system() == "Windows":
                os.startfile(os.path.abspath(path))
            else:
                subprocess.run(["open", os.path.abspath(path)])
        except Exception as e:
            self.progress.emit(f"이미지 파일 열기 실패: {e}")
    
    def capture_wrap_company_area(self, stock_code: str) -> str:
        driver = None
        try:
            driver = initialize_driver(headless=True)
            url = f"https://finance.naver.com/item/main.naver?code={stock_code}"
            driver.get(url)
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.wrap_company")))

            stock_name = driver.find_element(By.CSS_SELECTOR, "div.wrap_company h2 a").text.strip() or "Unknown"

            el = driver.find_element(By.CSS_SELECTOR, "div.wrap_company")
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
            time.sleep(0.5)

            location = el.location
            size = el.size
            
            screenshot_bytes = driver.get_screenshot_as_png()
            image = Image.open(io.BytesIO(screenshot_bytes))

            zoom = driver.execute_script("return window.devicePixelRatio || 1;")
            left = location['x'] * zoom
            top = location['y'] * zoom
            right = (location['x'] + size['width']) * zoom
            bottom = (location['y'] + size['height']) * zoom
            
            cropped = image.crop((left, top, right, bottom))

            today = datetime.now().strftime("%Y%m%d")
            folder = os.path.join("주식차트", today)
            os.makedirs(folder, exist_ok=True)
            clean_name = re.sub(r'[\\/*?:"<>|]', "", stock_name)
            filename = f"{stock_code}_{clean_name}.png"
            output_path = os.path.join(folder, filename)
            cropped.save(output_path)

            if self.copy_image_to_clipboard(output_path):
                 self.progress.emit("클립보드에 복사 완료!")
            self.open_image(output_path)
            return output_path
        finally:
            if driver:
                driver.quit()
    
    def get_stock_info_from_search(self, keyword: str):
        if keyword.isdigit() and len(keyword) == 6:
            return keyword

        driver = None
        try:
            driver = initialize_driver(headless=True)
            search_url = f"https://search.naver.com/search.naver?query={keyword}+주식"
            driver.get(search_url)
            
            try:
                finance_link = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='finance.naver.com/item/main.naver?code=']"))
                )
                href = finance_link.get_attribute('href')
                match = re.search(r"code=(\d{6})", href)
                if match:
                    return match.group(1)
            except Exception:
                pass 

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
        
        title_label = QLabel("📰 뉴스 재구성")
        title_label.setFont(QFont("Arial", 16, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        input_group = QGroupBox("입력")
        input_layout = QVBoxLayout()
        
        url_layout = QHBoxLayout()
        url_label = QLabel("기사 URL:")
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://...")
        url_layout.addWidget(url_label)
        url_layout.addWidget(self.url_input)
        input_layout.addLayout(url_layout)
        
        keyword_layout = QHBoxLayout()
        keyword_label = QLabel("키워드:")
        self.keyword_input = QLineEdit()
        self.keyword_input.setPlaceholderText("예: AI, 경제, 기술...")
        keyword_layout.addWidget(keyword_label)
        keyword_layout.addWidget(self.keyword_input)
        input_layout.addLayout(keyword_layout)
        
        self.url_input.returnPressed.connect(self.extract_news)
        self.keyword_input.returnPressed.connect(self.extract_news)
        
        input_group.setLayout(input_layout)
        layout.addWidget(input_group)
        
        button_layout = QHBoxLayout()
        self.extract_btn = QPushButton("📄 기사 추출")
        self.extract_btn.clicked.connect(self.extract_news)
        self.cancel_btn = QPushButton("❌ 취소")
        self.cancel_btn.clicked.connect(self.cancel_extraction)
        self.cancel_btn.setEnabled(False)
        self.open_chatbot_btn = QPushButton("🌐 챗봇 열기")
        self.open_chatbot_btn.clicked.connect(self.open_chatbot)
        button_layout.addWidget(self.extract_btn)
        button_layout.addWidget(self.cancel_btn)
        button_layout.addWidget(self.open_chatbot_btn)
        layout.addLayout(button_layout)
        
        self.progress_label = QLabel("")
        self.progress_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.progress_label)
        
        result_group = QGroupBox("결과")
        result_layout = QVBoxLayout()
        
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setMaximumHeight(200)
        result_layout.addWidget(self.result_text)
        
        self.copy_result_btn = QPushButton("📋 복사하기")
        self.copy_result_btn.clicked.connect(self.copy_result)
        self.copy_result_btn.setEnabled(False)
        result_layout.addWidget(self.copy_result_btn)
        
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
        self.cancel_btn.setEnabled(True)
        self.copy_result_btn.setEnabled(False)
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
        self.cancel_btn.setEnabled(False)
        
        if error:
            self.progress_label.setText("오류 발생")
            QMessageBox.warning(self, "추출 실패", error)
            self.copy_result_btn.setEnabled(False)
            return
        
        self.progress_label.setText("추출 완료! 클립보드에 복사되었습니다.")
        result_text = f"{self.keyword_input.text().strip()}, {title}, {body}"
        self.result_text.setText(result_text)
        self.copy_result_btn.setEnabled(True)
        
        if self.first_time:
            self.open_chatbot()
            self.first_time = False
    
    def open_chatbot(self):
        webbrowser.open(CHATBOT_URL, new=0)
        QMessageBox.information(self, "챗봇 열기", "챗봇이 열렸습니다. Ctrl+V로 붙여넣기하세요.")

    def copy_result(self):
        text = self.result_text.toPlainText()
        if text:
            pyperclip.copy(text)
            QMessageBox.information(self, "복사 완료", "결과가 클립보드에 복사되었습니다.")
        else:
            QMessageBox.warning(self, "복사 실패", "복사할 내용이 없습니다.")

    def cancel_extraction(self):
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait()
        self.progress_label.setText("취소됨")
        self.extract_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.copy_result_btn.setEnabled(False)

class ExchangeTab(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.worker = None
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        title_label = QLabel("💱 환율 차트")
        title_label.setFont(QFont("Arial", 16, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        input_group = QGroupBox("입력")
        input_layout = QVBoxLayout()
        
        keyword_layout = QHBoxLayout()
        keyword_label = QLabel("환율 키워드:")
        self.keyword_input = QLineEdit()
        self.keyword_input.setPlaceholderText("예: 달러환율, 유로환율, 엔환율...")
        keyword_layout.addWidget(keyword_label)
        keyword_layout.addWidget(self.keyword_input)
        input_layout.addLayout(keyword_layout)
        
        self.keyword_input.returnPressed.connect(self.capture_chart)
        
        input_group.setLayout(input_layout)
        layout.addWidget(input_group)
        
        button_layout = QHBoxLayout()
        self.capture_btn = QPushButton("📊 차트 캡처")
        self.capture_btn.clicked.connect(self.capture_chart)
        self.cancel_btn = QPushButton("❌ 취소")
        self.cancel_btn.clicked.connect(self.cancel_capture)
        self.cancel_btn.setEnabled(False)
        self.open_folder_btn = QPushButton("📁 폴더 열기")
        self.open_folder_btn.clicked.connect(self.open_folder)
        self.open_chatbot_btn = QPushButton("🌐 챗봇 열기")
        self.open_chatbot_btn.clicked.connect(self.open_chatbot)
        
        button_layout.addWidget(self.capture_btn)
        button_layout.addWidget(self.cancel_btn)
        button_layout.addWidget(self.open_folder_btn)
        button_layout.addWidget(self.open_chatbot_btn)
        layout.addLayout(button_layout)
        
        self.progress_label = QLabel("")
        self.progress_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.progress_label)
        
        result_group = QGroupBox("결과")
        result_layout = QVBoxLayout()
        
        self.result_label = QLabel("")
        self.result_label.setAlignment(Qt.AlignCenter)
        result_layout.addWidget(self.result_label)
        
        result_group.setLayout(result_layout)
        layout.addWidget(result_group)
        
        self.setLayout(layout)
    
    def open_folder(self):
        folder_path = os.path.abspath("환율차트")
        os.makedirs(folder_path, exist_ok=True)
        try:
            if platform.system() == "Windows":
                os.startfile(folder_path)
            else:
                subprocess.run(["open", folder_path])
        except Exception as e:
            QMessageBox.warning(self, "폴더 열기 실패", str(e))
    
    def open_chatbot(self):
        webbrowser.open(INFO_CHATBOT_URL, new=0)
        QMessageBox.information(self, "챗봇 열기", "정보성 기사 챗봇이 열렸습니다.")
    
    def capture_chart(self):
        keyword = self.keyword_input.text().strip()
        
        if not keyword:
            QMessageBox.warning(self, "입력 오류", "환율 키워드를 입력해주세요.")
            return
        
        self.capture_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
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
        self.cancel_btn.setEnabled(False)
        
        if error:
            self.progress_label.setText("오류 발생")
            QMessageBox.warning(self, "캡처 실패", error)
            return
        
        self.progress_label.setText("캡처 완료!")
        self.result_label.setText(f"저장됨: {os.path.abspath(image_path)}")

    def cancel_capture(self):
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait()
        self.progress_label.setText("취소됨")
        self.capture_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

class StockTab(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.worker = None
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        title_label = QLabel("📈 주식 차트")
        title_label.setFont(QFont("Arial", 16, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        input_group = QGroupBox("입력")
        input_layout = QVBoxLayout()
        
        keyword_layout = QHBoxLayout()
        keyword_label = QLabel("주식 코드 또는 회사명:")
        self.keyword_input = QLineEdit()
        self.keyword_input.setPlaceholderText("예: 005930, 삼성전자...")
        keyword_layout.addWidget(keyword_label)
        keyword_layout.addWidget(self.keyword_input)
        input_layout.addLayout(keyword_layout)
        
        self.keyword_input.returnPressed.connect(self.capture_chart)
        
        input_group.setLayout(input_layout)
        layout.addWidget(input_group)
        
        button_layout = QHBoxLayout()
        self.capture_btn = QPushButton("📊 차트 캡처")
        self.capture_btn.clicked.connect(self.capture_chart)
        self.cancel_btn = QPushButton("❌ 취소")
        self.cancel_btn.clicked.connect(self.cancel_capture)
        self.cancel_btn.setEnabled(False)
        self.open_folder_btn = QPushButton("📁 폴더 열기")
        self.open_folder_btn.clicked.connect(self.open_folder)
        self.open_chatbot_btn = QPushButton("� 챗봇 열기")
        self.open_chatbot_btn.clicked.connect(self.open_chatbot)
        button_layout.addWidget(self.capture_btn)
        button_layout.addWidget(self.cancel_btn)
        button_layout.addWidget(self.open_folder_btn)
        button_layout.addWidget(self.open_chatbot_btn)
        layout.addLayout(button_layout)
        
        self.progress_label = QLabel("")
        self.progress_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.progress_label)
        
        result_group = QGroupBox("결과")
        result_layout = QVBoxLayout()
        
        self.result_label = QLabel("")
        self.result_label.setAlignment(Qt.AlignCenter)
        result_layout.addWidget(self.result_label)
        
        result_group.setLayout(result_layout)
        layout.addWidget(result_group)
        
        self.setLayout(layout)
    
    def open_folder(self):
        folder_path = os.path.abspath("주식차트")
        os.makedirs(folder_path, exist_ok=True)
        try:
            if platform.system() == "Windows":
                os.startfile(folder_path)
            else:
                subprocess.run(["open", folder_path])
        except Exception as e:
            QMessageBox.warning(self, "폴더 열기 실패", str(e))
    
    def open_chatbot(self):
        webbrowser.open(INFO_CHATBOT_URL, new=0)
        QMessageBox.information(self, "챗봇 열기", "정보성 기사 챗봇이 열렸습니다.")
    
    def capture_chart(self):
        keyword = self.keyword_input.text().strip()
        
        if not keyword:
            QMessageBox.warning(self, "입력 오류", "주식 코드 또는 회사명을 입력해주세요.")
            return
        
        self.capture_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
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
        self.cancel_btn.setEnabled(False)
        
        if error:
            self.progress_label.setText("오류 발생")
            QMessageBox.warning(self, "캡처 실패", error)
            return
        
        self.progress_label.setText("캡처 완료!")
        self.result_label.setText(f"저장됨: {os.path.abspath(image_path)}")

    def cancel_capture(self):
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait()
        self.progress_label.setText("취소됨")
        self.capture_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.init_ui()
    
    def init_ui(self):
        self.setWindowTitle("통합 뉴스 도구 - 제작자: 최준혁(kimbap918)")
        self.setGeometry(100, 100, 800, 600)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout()
        
        self.tab_widget = QTabWidget()
        
        self.news_tab = NewsTab()
        self.exchange_tab = ExchangeTab()
        self.stock_tab = StockTab()
        
        self.tab_widget.addTab(self.news_tab, "📰 뉴스 재구성")
        self.tab_widget.addTab(self.exchange_tab, "💱 환율 차트")
        self.tab_widget.addTab(self.stock_tab, "📈 주식 차트")
        
        layout.addWidget(self.tab_widget)
        
        status_label = QLabel("")
        status_messages = []
        if not SELENIUM_AVAILABLE:
            status_messages.append("⚠️ Selenium/webdriver-manager 미설치 (차트 캡처 기능 제한)")
        if not CLIPBOARD_AVAILABLE:
            status_messages.append("⚠️ pywin32 미설치 (클립보드 복사 기능 제한)")
        
        if not status_messages:
            status_label.setText("✅ 모든 기능이 준비되었습니다.")
        else:
            status_label.setText(" | ".join(status_messages))
            status_label.setStyleSheet("color: orange;")
        
        status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(status_label)
        
        creator_label = QLabel("제작자: 최준혁")
        creator_label.setAlignment(Qt.AlignCenter)
        creator_label.setStyleSheet("color: gray; font-size: 10px; margin-top: 5px;")
        layout.addWidget(creator_label)
        
        central_widget.setLayout(layout)

def main():
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    font = QFont("Malgun Gothic", 9)
    app.setFont(font)
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()