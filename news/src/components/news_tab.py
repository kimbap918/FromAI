# news_tab.py

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QGroupBox, QHBoxLayout, QLineEdit, QPushButton, QTextEdit, QMessageBox
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont
import pyperclip
import webbrowser

from news.src.utils.article_utils import extract_article_content

CHATBOT_URL = "https://chatgpt.com/g/g-67abdb7e8f1c8191978db654d8a57b86-gisa-jaeguseong-caesbos?model=gpt-4o"
MIN_BODY_LENGTH = 300

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-09
# 버전 : 1.0.0
# 기능 : PyQt5에서 기사 추출 작업 진행 상태 업데이트하는 함수(프론트)
# ------------------------------------------------------------------
class NewsWorker(QThread):
    finished = pyqtSignal(str, str, str)  # title, body, error
    progress = pyqtSignal(str)

    def __init__(self, url, keyword):
        super().__init__()
        self.url = url
        self.keyword = keyword

    def run(self):
        try:
            self.progress.emit("기사 다운로드 중...")
            title, body = extract_article_content(self.url, progress_callback=self.progress.emit)

            self.progress.emit("본문 길이 확인 중...")
            if len(body) < MIN_BODY_LENGTH:
                self.finished.emit("", "", "본문이 너무 짧습니다. 다른 링크를 시도해보세요.")
                return

            result_text = f"{self.keyword}, {title}, {body}"
            pyperclip.copy(result_text)

            self.progress.emit("기사 추출 성공! 결과가 클립보드에 복사되었습니다.")
            self.finished.emit(title, body, "")

        except Exception as e:
            self.progress.emit(f"오류 발생: {str(e)}")
            self.finished.emit("", "", f"오류 발생: {str(e)}")

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-09
# 버전 : 1.0.0
# 기능 : PyQt5에서 뉴스 탭 위젯 및 레이아웃 설정(프론트)
# ------------------------------------------------------------------
class NewsTab(QWidget):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.init_ui()

    # ------------------------------------------------------------------
    # 작성자 : 최준혁
    # 작성일 : 2025-07-09
    # 기능 : PyQt5에서 뉴스 탭 위젯 및 레이아웃 설정(프론트)
    # ------------------------------------------------------------------
    def init_ui(self):
        layout = QVBoxLayout()

        title_label = QLabel("📰 뉴스 재구성")
        title_label.setFont(QFont("Arial", 16, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        # 기존 status_label 관련 코드 제거
        # 기사 추출/작업 완료 시에만 주의 메시지 표시

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
        self.extract_btn = QPushButton("📄 기사 추출")
        self.extract_btn.clicked.connect(self.extract_news)
        self.reset_btn = QPushButton("🔄 리셋")
        self.reset_btn.clicked.connect(self.reset_inputs)
        self.cancel_btn = QPushButton("❌ 취소")
        self.cancel_btn.clicked.connect(self.cancel_extraction)
        self.cancel_btn.setEnabled(False)
        self.open_chatbot_btn = QPushButton("🌐 챗봇 열기")
        self.open_chatbot_btn.clicked.connect(self.open_chatbot)
        button_layout.addWidget(self.extract_btn)
        button_layout.addWidget(self.reset_btn)
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

        copy_button_layout = QHBoxLayout()
        self.copy_result_btn = QPushButton("📋 복사하기")
        self.copy_result_btn.clicked.connect(self.copy_result)
        self.copy_result_btn.setEnabled(False)
        copy_button_layout.addWidget(self.copy_result_btn)
        result_layout.addLayout(copy_button_layout)

        result_group.setLayout(result_layout)
        layout.addWidget(result_group)

        self.setLayout(layout)

    # ------------------------------------------------------------------
    # 작성자 : 최준혁
    # 작성일 : 2025-07-09
    # 기능 : PyQt5에서 입력 필드 리셋하는 함수(프론트)
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # 작성자 : 최준혁
    # 작성일 : 2025-07-09
    # 기능 : PyQt5에서 기사 추출 함수(프론트)
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # 작성자 : 최준혁
    # 작성일 : 2025-07-09
    # 기능 : PyQt5에서 기사 추출 진행 상태 업데이트하는 함수(프론트)
    # ------------------------------------------------------------------
    def update_progress(self, message):
        # 마지막 메시지(성공/주의/경고)는 주황색, 그 외는 검정색
        if any(x in message for x in ["성공", "주의", "확인", "오류"]):
            self.progress_label.setStyleSheet("color: #FFA500; font-weight: bold;")
        else:
            self.progress_label.setStyleSheet("color: black;")
        self.progress_label.setText(message)

    # ------------------------------------------------------------------
    # 작성자 : 최준혁
    # 작성일 : 2025-07-09
    # 기능 : PyQt5에서 기사 추출 완료 시 처리하는 함수(프론트)
    # ------------------------------------------------------------------
    def on_extraction_finished(self, title, body, error):
        self.extract_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

        if error:
            self.progress_label.setText("")
            QMessageBox.warning(self, "추출 실패", error)
            self.copy_result_btn.setEnabled(False)
            return

        self.progress_label.setText("기사 작성시 내용의 오류가 없는지 확인하세요!")
        self.progress_label.setStyleSheet("color: #FFA500; font-weight: bold;")
        result_text = f"{self.keyword_input.text().strip()}, {title}, {body}"
        self.result_text.setText(result_text)
        self.copy_result_btn.setEnabled(True)

    # ------------------------------------------------------------------
    # 작성자 : 최준혁
    # 작성일 : 2025-07-09
    # 기능 : PyQt5에서 챗봇 열기 함수(프론트)
    # ------------------------------------------------------------------
    def open_chatbot(self):
        webbrowser.open(CHATBOT_URL, new=0)
        QMessageBox.information(self, "챗봇 열기", "챗봇이 열렸습니다. Ctrl+V로 붙여넣기하세요.")

    # ------------------------------------------------------------------
    # 작성자 : 최준혁
    # 작성일 : 2025-07-09
    # 기능 : PyQt5에서 결과 복사 함수(프론트)
    # ------------------------------------------------------------------
    def copy_result(self):
        text = self.result_text.toPlainText()
        pyperclip.copy(text)

    # ------------------------------------------------------------------
    # 작성자 : 최준혁
    # 작성일 : 2025-07-09
    # 기능 : PyQt5에서 기사 추출 취소 함수(프론트)
    # ------------------------------------------------------------------
    def cancel_extraction(self):
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
        self.progress_label.setText("취소됨")
        self.extract_btn.setEnabled(True)
        self.copy_result_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)