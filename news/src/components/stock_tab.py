# stock_tab.py

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QGroupBox, QHBoxLayout, QLineEdit, QPushButton, QTextEdit, QMessageBox
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont
import pyperclip
import platform
import webbrowser
import os
from datetime import datetime

from news.src.utils.capture_utils import capture_wrap_company_area, get_stock_info_from_search

STOCK_CHATBOT_URL = "https://chatgpt.com/g/g-67a44d9d833c8191bf2974019d233d4e-jeongboseong-gisa-caesbos-culceo-sanggwaneobseum"

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-09
# 버전 : 1.0.0
# 기능 : PyQt5에서 주식 코드 검색 후 차트 캡처하는 기능(프론트)
# ------------------------------------------------------------------
class StockWorker(QThread):
    finished = pyqtSignal(str, str)  # image_path, error
    progress = pyqtSignal(str)

    def __init__(self, keyword):
        super().__init__()
        self.keyword = keyword

    def run(self):
        try:
            self.progress.emit("주식 코드 검색 중...")
            stock_code = get_stock_info_from_search(self.keyword)
            if not stock_code:
                self.finished.emit("", "주식 코드를 찾을 수 없습니다.")
                return

            self.progress.emit("주식 차트 캡처 중...")
            image_path = capture_wrap_company_area(stock_code)
            if image_path:
                self.finished.emit(image_path, "")
            else:
                self.finished.emit("", "차트 캡처에 실패했습니다.")

        except Exception as e:
            self.finished.emit("", str(e))

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-09
# 버전 : 1.0.0
# 기능 : PyQt5에서 주식 차트 탭 위젯 및 레이아웃 설정(프론트)
# ------------------------------------------------------------------
class StockTab(QWidget):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.last_image_path = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        title_label = QLabel("📈 주식 차트")
        title_label.setFont(QFont("Arial", 16, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        # 기존 status_label 관련 코드 제거
        # 캡처 완료 시에만 주의 메시지 표시

        input_group = QGroupBox("입력")
        input_layout = QVBoxLayout()

        keyword_layout = QHBoxLayout()
        keyword_label = QLabel("주식 코드 또는 회사명:")
        self.keyword_input = QLineEdit()
        self.keyword_input.setPlaceholderText("예: 삼성전자, 005930 등")
        self.keyword_input.returnPressed.connect(self.capture_chart)
        keyword_layout.addWidget(keyword_label)
        keyword_layout.addWidget(self.keyword_input)
        input_layout.addLayout(keyword_layout)
        input_group.setLayout(input_layout)
        layout.addWidget(input_group)

        button_layout = QHBoxLayout()
        self.capture_btn = QPushButton("📊 차트 캡처")
        self.capture_btn.clicked.connect(self.capture_chart)
        self.reset_btn = QPushButton("🔄 리셋")
        self.reset_btn.clicked.connect(self.reset_inputs)
        self.cancel_btn = QPushButton("❌ 취소")
        self.cancel_btn.clicked.connect(self.cancel_capture)
        self.cancel_btn.setEnabled(False)
        self.open_folder_btn = QPushButton("📁 폴더 열기")
        self.open_folder_btn.clicked.connect(self.open_folder)
        self.open_chatbot_btn = QPushButton("🌐 챗봇 열기")
        self.open_chatbot_btn.clicked.connect(lambda: webbrowser.open(STOCK_CHATBOT_URL))

        button_layout.addWidget(self.capture_btn)
        button_layout.addWidget(self.reset_btn)
        button_layout.addWidget(self.cancel_btn)
        button_layout.addWidget(self.open_folder_btn)
        button_layout.addWidget(self.open_chatbot_btn)
        layout.addLayout(button_layout)

        self.progress_label = QLabel("")
        self.progress_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.progress_label)

        self.result_label = QLabel("")
        self.result_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.result_label)

        self.setLayout(layout)

    # ------------------------------------------------------------------
    # 작성자 : 최준혁
    # 작성일 : 2025-07-09
    # 기능 : PyQt5에서 입력 필드 리셋하는 함수(프론트)
    # ------------------------------------------------------------------
    def reset_inputs(self):
        self.keyword_input.clear()
        self.result_label.setText("")
        self.progress_label.setText("")
        self.capture_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

    # ------------------------------------------------------------------
    # 작성자 : 최준혁
    # 작성일 : 2025-07-09
    # 기능 : PyQt5에서 주식 차트 폴더 열기 함수(프론트)
    # ------------------------------------------------------------------
    def open_folder(self):
        today = datetime.now().strftime('%Y%m%d')
        folder_path = os.path.join("주식차트", f"주식{today}")
        if os.path.exists(folder_path):
            if platform.system() == "Windows":
                os.startfile(folder_path)
            elif platform.system() == "Darwin":
                os.system(f"open {folder_path}")
            elif platform.system() == "Linux":
                os.system(f"xdg-open {folder_path}")
        else:
            QMessageBox.information(self, "폴더 없음", "아직 캡처된 이미지가 없습니다.")

    # ------------------------------------------------------------------
    # 작성자 : 최준혁
    # 작성일 : 2025-07-09
    # 기능 : PyQt5에서 주식 차트 캡처 함수(프론트)
    # ------------------------------------------------------------------
    def capture_chart(self):
        keyword = self.keyword_input.text().strip()
        if not keyword:
            QMessageBox.warning(self, "입력 오류", "주식 코드 또는 회사명을 입력해주세요.")
            return

        self.capture_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.result_label.setText("")
        self.progress_label.setText("처리 중...")

        self.worker = StockWorker(keyword)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.on_capture_finished)
        self.worker.start()

    # ------------------------------------------------------------------
    # 작성자 : 최준혁
    # 작성일 : 2025-07-09
    # 기능 : PyQt5에서 주식 차트 캡처 취소 함수(프론트)
    # ------------------------------------------------------------------
    def cancel_capture(self):
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
        self.progress_label.setText("⛔️ 캡처 취소됨")
        self.capture_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

    # ------------------------------------------------------------------
    # 작성자 : 최준혁
    # 작성일 : 2025-07-09
    # 기능 : PyQt5에서 주식 차트 캡처 진행 상태 업데이트하는 함수(프론트)
    # ------------------------------------------------------------------
    def update_progress(self, message):
        self.progress_label.setText(message)

    # ------------------------------------------------------------------
    # 작성자 : 최준혁
    # 작성일 : 2025-07-09
    # 기능 : PyQt5에서 주식 차트 캡처 완료 시 처리하는 함수(프론트)
    # ------------------------------------------------------------------
    def on_capture_finished(self, image_path, error):
        self.capture_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        if error:
            QMessageBox.warning(self, "캡처 실패", error)
            self.progress_label.setText("")
            return

        pyperclip.copy(image_path)
        self.result_label.setText(f"저장됨: {image_path}\n이미지가 클립보드에 복사되었습니다.")
        self.progress_label.setText("기사 작성시 내용의 오류가 없는지 확인하세요!")
        self.progress_label.setStyleSheet("color: #FFA500; font-weight: bold;")
