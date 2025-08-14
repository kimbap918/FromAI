from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QGroupBox, QHBoxLayout, QLineEdit, QPushButton, QTextEdit, QMessageBox
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont
import pyperclip
import webbrowser
import urllib.parse
import os
import subprocess
from datetime import datetime
import sys

from news.src.services import news_LLM

CHATBOT_URL = "https://chatgpt.com/g/g-67abdb7e8f1c8191978db654d8a57b86-gisa-jaeguseong-caesbos?model=gpt-4o"

# 지원 불가 뉴스 사이트 패턴 (도메인 일부 포함)
BLOCKED_SITES = {
    "ichannela": "채널A",
    "moneys": "머니S",
    "chosun": "조선일보",
    "jtbc": "JTBC",
    "seoul.co.kr": "서울신문",
    "dt.co.kr": "디지털타임스",
    "biz.sbs": "SBS Biz",
    "news1": "뉴스1",
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

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-09
# 버전 : 1.1.1
# 기능 : LLM을 이용한 기사 재구성 테스트 탭(프론트)
# 변경 : 사실검증 결과에 따라 표출 내용 분기 (기사만/검증만)
# ------------------------------------------------------------------
class NewsLLMWorker(QThread):
    finished = pyqtSignal(dict, str)  # result, error
    progress = pyqtSignal(str)

    def __init__(self, url: str, keyword: str):
        super().__init__()
        self.url = url
        self.keyword = keyword

    def run(self):
        try:
            self.progress.emit("LLM을 통한 기사 생성 중...")
            result = news_LLM.generate_article({"url": self.url, "keyword": self.keyword})
            if result.get("error"):
                self.finished.emit({}, result.get("error"))
                return
            self.finished.emit(result, "")
        except Exception as e:
            self.finished.emit({}, str(e))


class NewsTabTest(QWidget):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        title_label = QLabel("📰 뉴스 재구성(테스트)")
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
        self.keyword_input.returnPressed.connect(self.extract_news)
        keyword_layout.addWidget(keyword_label)
        keyword_layout.addWidget(self.keyword_input)
        input_layout.addLayout(keyword_layout)

        input_group.setLayout(input_layout)
        layout.addWidget(input_group)

        button_layout = QHBoxLayout()
        self.extract_btn = QPushButton("🤖 LLM 재구성")
        self.extract_btn.clicked.connect(self.extract_news)
        self.reset_btn = QPushButton("🔄 리셋")
        self.reset_btn.clicked.connect(self.reset_inputs)
        self.cancel_btn = QPushButton("❌ 취소")
        self.cancel_btn.clicked.connect(self.cancel_extraction)
        self.cancel_btn.setEnabled(False)
        self.open_folder_btn = QPushButton("📁 폴더 열기")
        self.open_folder_btn.clicked.connect(self.open_today_folder)

        button_layout.addWidget(self.extract_btn)
        button_layout.addWidget(self.reset_btn)
        button_layout.addWidget(self.cancel_btn)
        button_layout.addWidget(self.open_folder_btn)
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

        copy_button_layout = QHBoxLayout()
        self.copy_result_btn = QPushButton("📋 복사하기")
        self.copy_result_btn.clicked.connect(self.copy_result)
        self.copy_result_btn.setEnabled(False)
        copy_button_layout.addWidget(self.copy_result_btn)
        result_layout.addLayout(copy_button_layout)

        result_group.setLayout(result_layout)
        layout.addWidget(result_group)

        self.setLayout(layout)

    def reset_inputs(self):
        self.url_input.clear()
        self.keyword_input.clear()
        self.result_text.clear()
        self.progress_label.setText("")
        self.copy_result_btn.setEnabled(False)
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
        self.extract_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

    def extract_news(self):
        url = self.url_input.text().strip()
        keyword = self.keyword_input.text().strip()

        if not url or not keyword:
            QMessageBox.warning(self, "입력 오류", "URL과 키워드를 모두 입력해주세요.")
            return

        # 지원 불가 도메인 사전 차단
        blocked, site_name = is_blocked_url(url)
        if blocked:
            QMessageBox.warning(
                self,
                "지원 불가 URL",
                f"현재 크롤링을 지원하지 않는 사이트입니다: {site_name}\n다른 기사 URL을 입력해주세요.",
            )
            return

        self.extract_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.copy_result_btn.setEnabled(False)
        self.progress_label.setText("처리 중...")
        self.result_text.clear()

        self.worker = NewsLLMWorker(url, keyword)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.on_generation_finished)
        self.worker.start()
        self.extract_btn.setEnabled(True)

    def update_progress(self, message: str):
        if any(x in message for x in ["성공", "주의", "확인", "오류", "완료"]):
            self.progress_label.setStyleSheet("color: #FFA500; font-weight: bold;")
        else:
            self.progress_label.setStyleSheet("color: black;")
        self.progress_label.setText(message)

    def on_generation_finished(self, result: dict, error: str):
        self.extract_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

        if error:
            self.progress_label.setText("")
            QMessageBox.warning(self, "생성 실패", error)
            self.copy_result_btn.setEnabled(False)
            return

        display_text = result.get("display_text", "")
        kind = result.get("display_kind", "")

        if kind == "article":
            self.progress_label.setText("기사 생성 완료. (사실관계 이상 없음)")
            self.progress_label.setStyleSheet("color: #2E7D32; font-weight: bold;")
        elif kind == "fact_check":
            self.progress_label.setText("사실검증 경고: 문제점을 확인하세요.")
            self.progress_label.setStyleSheet("color: #FF3B30; font-weight: bold;")
        elif kind == "error":
            self.progress_label.setText("오류가 발생했습니다.")
            self.progress_label.setStyleSheet("color: #FF3B30; font-weight: bold;")
        else:
            self.progress_label.setText("처리 완료")
            self.progress_label.setStyleSheet("color: #000000;")

        self.result_text.setText(display_text)
        self.copy_result_btn.setEnabled(True)

    def open_chatbot(self):
        webbrowser.open(CHATBOT_URL, new=0)
        QMessageBox.information(self, "챗봇 열기", "챗봇이 열렸습니다. Ctrl+V로 붙여넣기하세요.")

    def copy_result(self):
        text = self.result_text.toPlainText()
        pyperclip.copy(text)

    def cancel_extraction(self):
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
        self.progress_label.setText("취소됨")
        self.extract_btn.setEnabled(True)
        self.copy_result_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)

    def open_today_folder(self):
        """
        오늘 날짜의 재생성 폴더를 엽니다.
        """
        try:
            # 현재 날짜로 폴더명 생성
            current_date = datetime.now().strftime("%Y%m%d")
            
            # exe 빌드 시와 개발 시를 구분하여 경로 설정
            if getattr(sys, 'frozen', False):
                # exe 빌드 시: 실행 파일이 있는 디렉토리
                base_dir = os.path.dirname(sys.executable)
                folder_path = os.path.join(base_dir, "기사 재생성", f"재생성{current_date}")
            else:
                # 개발 시: 현재 스크립트 위치에서 상위로 이동하여 FromAI1.1.3 2 찾기
                current_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))  # news/src/components -> news/
                base_dir = current_dir
                
                # FromAI1.1.3 2 폴더를 찾을 때까지 상위 디렉토리로 이동
                while base_dir and not os.path.exists(os.path.join(base_dir, "FromAI1.1.3 2")):
                    parent_dir = os.path.dirname(base_dir)
                    if parent_dir == base_dir:  # 루트 디렉토리에 도달
                        break
                    base_dir = parent_dir
                
                # FromAI1.1.3 2 폴더가 없으면 현재 디렉토리 사용
                if not os.path.exists(os.path.join(base_dir, "FromAI1.1.3 2")):
                    base_dir = current_dir
                
                # 폴더 경로 생성
                folder_path = os.path.join(base_dir, "FromAI1.1.3 2", "기사 재생성", f"재생성{current_date}")
            
            # 폴더가 존재하는지 확인
            if not os.path.exists(folder_path):
                # 폴더가 없으면 조용히 생성
                os.makedirs(folder_path, exist_ok=True)
            
            # 운영체제별로 폴더 열기
            if os.name == 'nt':  # Windows
                # Windows에서 경로에 공백이 있을 때 발생하는 문제 해결
                try:
                    subprocess.run(['explorer', folder_path], check=True, shell=True)
                except subprocess.CalledProcessError:
                    # shell=True로도 안되면 직접 경로를 explorer에 전달
                    os.system(f'explorer "{folder_path}"')
            elif os.name == 'posix':  # macOS, Linux
                if os.system('which open') == 0:  # macOS
                    subprocess.run(['open', folder_path], check=True)
                else:  # Linux
                    subprocess.run(['xdg-open', folder_path], check=True)
            
        except Exception as e:
            # 에러가 발생해도 조용히 처리 (모달 없음)
            pass
