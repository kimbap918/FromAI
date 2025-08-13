from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QGroupBox, QHBoxLayout, QLineEdit, QPushButton, QTextEdit, QMessageBox
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont
import pyperclip
import webbrowser

from news.src.services import news_LLM

CHATBOT_URL = "https://chatgpt.com/g/g-67abdb7e8f1c8191978db654d8a57b86-gisa-jaeguseong-caesbos?model=gpt-4o"

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-09
# 버전 : 1.1.0
# 기능 : LLM을 이용한 기사 재구성 테스트 탭(프론트)
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


# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-09
# 기능 : PyQt5에서 뉴스 재구성(테스트) 탭 위젯 및 레이아웃 설정(프론트)
# ------------------------------------------------------------------
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

        button_layout.addWidget(self.extract_btn)
        button_layout.addWidget(self.reset_btn)
        button_layout.addWidget(self.cancel_btn)
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

        keyword = result.get("keyword", "")
        title = result.get("title", "")
        generated = result.get("generated_article", "")
        fact_check = result.get("fact_check_result", "")

        self.progress_label.setText("기사 생성 완료. 사실관계 검증 결과를 확인하세요.")
        self.progress_label.setStyleSheet("color: #FFA500; font-weight: bold;")

        display_text = f"{keyword}, {title}\n\n{generated}\n\n[사실검증]\n{fact_check}"
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