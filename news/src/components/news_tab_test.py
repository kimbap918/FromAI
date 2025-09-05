from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QGroupBox, QHBoxLayout, QLineEdit, QPushButton, QTextEdit, QMessageBox, QShortcut, QSplitter
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QKeySequence
import pyperclip
import webbrowser
import urllib.parse
import os
import subprocess
from datetime import datetime
import sys

from news.src.utils.article_utils import extract_article_content
from news.src.services import news_LLM

CHATBOT_URL = "https://chatgpt.com/g/g-67abdb7e8f1c8191978db654d8a57b86-gisa-jaeguseong-caesbos?model=gpt-4o"

BLOCKED_SITES = {
    "ichannela": "채널A",
    "moneys": "머니S",
    "chosun": "조선일보",
    "jtbc": "JTBC",
    "seoul.co.kr": "서울신문",
    "dt.co.kr": "디지털타임스",
    "biz.sbs": "SBS Biz",
    "news1": "뉴스1",
    "kmib": "국민일보",
}

def is_blocked_url(url: str):
    try:
        parsed = urllib.parse.urlparse(url)
        host = (parsed.netloc or "").lower()
        for pattern, name in BLOCKED_SITES.items():
            if pattern in host:
                return True, name
        return False, ""
    except Exception:
        return False, ""

# -------------------------- Workers --------------------------
class NewsCrawlerWorker(QThread):
    finished = pyqtSignal(str, str, str)  # title, body, error
    progress = pyqtSignal(str)

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self):
        try:
            self.progress.emit("기사 다운로드 중...")
            title, body = extract_article_content(self.url, progress_callback=self.progress.emit)
            if self.isInterruptionRequested():
                self.finished.emit("", "", "크롤링이 취소되었습니다.")
                return
            self.progress.emit("본문 길이 확인 중...")
            if not body or len(body) < 300:
                self.finished.emit("", "", "기사 본문을 추출하지 못했거나 너무 짧습니다.")
                return
            self.finished.emit(title, body, "")
        except Exception as e:
            self.progress.emit(f"크롤링 중 오류 발생: {str(e)}")
            self.finished.emit("", "", f"크롤링 중 오류 발생: {str(e)}")

class NewsLLMWorker(QThread):
    finished = pyqtSignal(dict, str)  # result, error
    progress = pyqtSignal(str)

    def __init__(self, url: str, keyword: str, title: str, body: str):
        super().__init__()
        self.url = url
        self.keyword = keyword
        self.title = title
        self.body = body

    def run(self):
        try:
            self.progress.emit("LLM을 통한 기사 생성 중...")
            result = news_LLM.generate_article({
                "url": self.url,
                "keyword": self.keyword,
                "title": self.title,
                "body": self.body
            })
            if self.isInterruptionRequested():
                self.finished.emit({}, "LLM 처리가 취소되었습니다.")
                return
            if isinstance(result, dict) and result.get("error"):
                self.finished.emit({}, result.get("error"))
                return
            self.finished.emit(result if isinstance(result, dict) else {}, "")
        except Exception as e:
            self.progress.emit(f"LLM 처리 중 오류 발생: {str(e)}")
            self.finished.emit({}, f"LLM 처리 중 오류 발생: {str(e)}")

# -------------------------- Main UI --------------------------
class NewsTabTest(QWidget):
    def __init__(self):
        super().__init__()
        self.crawler_worker = None
        self.llm_worker = None
        self.current_title = ""
        self.current_body = ""
        self.current_keyword = ""
        self.current_url = ""
        self._busy = False
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        title_label = QLabel("📰 뉴스 LLM 재구성")
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

        input_group.setLayout(input_layout)
        layout.addWidget(input_group)

        button_layout = QHBoxLayout()
        self.extract_btn = QPushButton("📄 기사 추출")
        self.extract_btn.clicked.connect(self.extract_news)
        self.reset_btn = QPushButton("🔄 리셋")
        self.reset_btn.clicked.connect(self.reset_inputs)
        self.cancel_btn = QPushButton("❌ 취소")
        self.cancel_btn.clicked.connect(self.cancel_extraction)
        self.cancel_btn.setEnabled(False)
        self.open_folder_btn = QPushButton("📁 폴더 열기")
        self.open_folder_btn.clicked.connect(self.open_today_folder)

        for btn in [self.extract_btn, self.reset_btn, self.cancel_btn, self.open_folder_btn]:
            button_layout.addWidget(btn)
        layout.addLayout(button_layout)

        self.progress_label = QLabel("")
        self.progress_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.progress_label)

        # -------------------------- 결과 (좌/우 분할) --------------------------
        splitter = QSplitter(Qt.Horizontal)

        # 원문 그룹
        original_group = QGroupBox("원문")
        original_layout = QVBoxLayout()
        self.original_text = QTextEdit()
        self.original_text.setReadOnly(True)
        self.copy_original_btn = QPushButton("📋 원문 복사")
        self.copy_original_btn.clicked.connect(lambda: self.copy_to_clipboard(self.original_text))
        original_layout.addWidget(self.original_text)
        original_layout.addWidget(self.copy_original_btn)
        original_group.setLayout(original_layout)

        # 재구성 결과 그룹
        llm_group = QGroupBox("재구성 결과")
        llm_layout = QVBoxLayout()
        self.llm_result_text = QTextEdit()
        self.llm_result_text.setReadOnly(True)
        self.copy_llm_btn = QPushButton("📋 재구성 결과 복사")
        self.copy_llm_btn.clicked.connect(lambda: self.copy_to_clipboard(self.llm_result_text))
        llm_layout.addWidget(self.llm_result_text)
        llm_layout.addWidget(self.copy_llm_btn)
        llm_group.setLayout(llm_layout)

        splitter.addWidget(original_group)
        splitter.addWidget(llm_group)
        splitter.setSizes([500, 500])  # 초기 크기 설정

        layout.addWidget(splitter, 1)  # Stretch factor를 1로 설정하여 남는 공간을 모두 차지하도록 함

        self.setLayout(layout)

        # 엔터 단축키
        shortcut_enter = QShortcut(QKeySequence(Qt.Key_Return), self)
        shortcut_enter.activated.connect(self.extract_news)
        shortcut_enter2 = QShortcut(QKeySequence(Qt.Key_Enter), self)
        shortcut_enter2.activated.connect(self.extract_news)

    # -------------------------- 핵심 기능 --------------------------
    def reset_inputs(self):
        self.url_input.clear()
        self.keyword_input.clear()
        self.original_text.clear()
        self.llm_result_text.clear()
        self.progress_label.setText("")

        if self.crawler_worker and self.crawler_worker.isRunning():
            self.crawler_worker.requestInterruption()
        if self.llm_worker and self.llm_worker.isRunning():
            self.llm_worker.requestInterruption()

        self.extract_btn.setEnabled(True)
        self.extract_btn.setText("📄 기사 추출")
        self.cancel_btn.setEnabled(False)
        self._busy = False
        if hasattr(self, 'crawling_done'):
            delattr(self, 'crawling_done')

    def extract_news(self):
        if self._busy:
            QMessageBox.information(self, "작업 중", "작업이 이미 진행 중입니다. 취소 후 다시 시도해주세요.")
            return

        if not hasattr(self, 'crawling_done') or not self.crawling_done:
            self.current_url = self.url_input.text().strip()
            self.current_keyword = self.keyword_input.text().strip()
            if not self.current_url or not self.current_keyword:
                QMessageBox.warning(self, "입력 오류", "URL과 키워드를 모두 입력해주세요.")
                return
            blocked, site_name = is_blocked_url(self.current_url)
            if blocked:
                QMessageBox.warning(self, "지원 불가 URL", f"현재 크롤링을 지원하지 않는 사이트입니다: {site_name}")
                return

            self._busy = True
            self.extract_btn.setEnabled(False)
            self.cancel_btn.setEnabled(True)
            self.progress_label.setText("기사 크롤링 중...")
            self.original_text.clear()
            self.llm_result_text.clear()

            self.crawler_worker = NewsCrawlerWorker(self.current_url)
            self.crawler_worker.finished.connect(self.on_crawling_finished)
            self.crawler_worker.progress.connect(self.update_progress)
            self.crawler_worker.start()
        else:
            self._busy = True
            self.progress_label.setText("LLM 처리 중...")
            self.extract_btn.setEnabled(False)
            self.cancel_btn.setEnabled(True)

            self.llm_worker = NewsLLMWorker(
                self.current_url,
                self.current_keyword,
                self.current_title,
                self.current_body
            )
            self.llm_worker.finished.connect(self.on_llm_finished)
            self.llm_worker.progress.connect(self.update_progress)
            self.llm_worker.start()

    def on_crawling_finished(self, title, body, error):
        self._busy = False
        if error:
            self.progress_label.setText("")
            QMessageBox.critical(self, "크롤링 오류", error)
            self.extract_btn.setEnabled(True)
            self.cancel_btn.setEnabled(False)
            return

        self.current_title = title
        self.current_body = body
        self.crawling_done = True

        separator = "=" * 80
        self.original_text.setPlainText(f"{title}\n{separator}\n\n{body}")

        self.progress_label.setText("크롤링 완료! 엔터나 'LLM 재구성' 클릭 가능.")
        self.extract_btn.setText("🤖 LLM 재구성")
        self.extract_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

    def on_llm_finished(self, result, error):
        self._busy = False
        self.extract_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        if error:
            self.progress_label.setText("")
            QMessageBox.critical(self, "LLM 처리 오류", error)
            self.extract_btn.setText("📄 기사 추출")
            if hasattr(self, 'crawling_done'):
                delattr(self, 'crawling_done')
            return

        display_text = ""
        if isinstance(result, dict):
            display_text = (
                result.get("display_text")
                or result.get("content")
                or result.get("text")
                or result.get("article")
                or result.get("result")
                or ""
            )
        self.llm_result_text.setPlainText(display_text)

        kind = "article"
        if isinstance(result, dict):
            kind = result.get("display_kind") or result.get("kind") or result.get("type") or "article"

        # 기사 완성 시 파일 저장 로직 추가
        if kind == "article" and display_text and self.current_keyword:
            self.save_article_to_file(display_text, self.current_keyword)

        if kind == "article":
            self.progress_label.setText("기사 생성 완료. (사실관계 이상 없음)")
            self.progress_label.setStyleSheet("color: #2E7D32; font-weight: bold;")
        elif kind == "fact_check":
            self.progress_label.setText("사실검증 경고: 문제점을 확인하세요.")
            self.progress_label.setStyleSheet("color: #FF3B30; font-weight: bold;")
        else:
            self.progress_label.setText("처리 완료")
            self.progress_label.setStyleSheet("color: #000000;")

        self.extract_btn.setText("📄 기사 추출")
        if hasattr(self, 'crawling_done'):
            delattr(self, 'crawling_done')

    def update_progress(self, message: str):
        if any(x in message for x in ["성공", "주의", "확인", "오류", "완료"]):
            self.progress_label.setStyleSheet("color: #FFA500; font-weight: bold;")
        else:
            self.progress_label.setStyleSheet("color: black;")
        self.progress_label.setText(message)

    def copy_to_clipboard(self, text_widget: QTextEdit):
        text = text_widget.toPlainText()
        if text:
            pyperclip.copy(text)
            QMessageBox.information(self, "복사 완료", "결과가 클립보드에 복사되었습니다.")
        else:
            QMessageBox.warning(self, "복사 실패", "복사할 내용이 없습니다.")

    def cancel_extraction(self):
        if self.crawler_worker and self.crawler_worker.isRunning():
            self.crawler_worker.requestInterruption()
        if self.llm_worker and self.llm_worker.isRunning():
            self.llm_worker.requestInterruption()
        self.progress_label.setText("취소 요청됨 — 작업이 안전하게 종료될 때까지 기다려주세요.")
        self.extract_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        self._busy = True

    def _get_base_dir(self) -> str:
        if getattr(sys, 'frozen', False):
            return os.path.dirname(sys.executable)
        return os.getcwd()

    def save_article_to_file(self, article_text: str, keyword: str):
        """
        완성된 기사를 사용자 입력 키워드로 폴더에 저장
        :param article_text: 완성된 기사 텍스트 ([제목], [해시태그], [본문] 포함)
        :param keyword: 사용자가 입력한 키워드
        """
        try:
            current_date = datetime.now().strftime("%Y%m%d")
            base_dir = self._get_base_dir()
            folder_path = os.path.join(base_dir, "기사 재생성", f"재생성{current_date}")
            os.makedirs(folder_path, exist_ok=True)
            
            # 키워드를 안전한 파일명으로 변환
            safe_keyword = "".join(c for c in keyword if c.isalnum() or c in (" ", "-", "_")).strip()
            safe_keyword = safe_keyword.replace(" ", "_") or "article"
            
            file_path = os.path.join(folder_path, f"{safe_keyword}.txt")
            
            # 파일에 기사 저장
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(article_text)
            
            self.progress_label.setText(f"기사가 저장되었습니다: {safe_keyword}.txt")
            
        except Exception as e:
            self.progress_label.setText(f"파일 저장 중 오류: {str(e)}")

    def open_today_folder(self):
        try:
            current_date = datetime.now().strftime("%Y%m%d")
            base_dir = self._get_base_dir()
            folder_path = os.path.join(base_dir, "기사 재생성", f"재생성{current_date}")
            os.makedirs(folder_path, exist_ok=True)
            if os.name == 'nt':
                os.startfile(folder_path)
            elif os.name == 'posix':
                if sys.platform == 'darwin':
                    subprocess.run(['open', folder_path], check=True)
                else:
                    subprocess.run(['xdg-open', folder_path], check=True)
        except Exception:
            pass

if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication, QDesktopWidget
    app = QApplication(sys.argv)

    # 화면 크기를 가져와서 창 크기 및 위치 설정
    desktop = QDesktopWidget()
    available_geometry = desktop.availableGeometry()
    screen_width = available_geometry.width()
    screen_height = available_geometry.height()

    window_width = screen_width // 2
    window_height = screen_height

    w = NewsTabTest()
    w.setWindowTitle("뉴스 재구성 테스트 (개별 실행)")
    w.setGeometry(screen_width // 2, available_geometry.top(), window_width, window_height)

    w.show()
    sys.exit(app.exec_())
