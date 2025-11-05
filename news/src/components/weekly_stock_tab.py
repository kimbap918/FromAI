# weekly_stock_tab.py

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QLabel, QGroupBox, QHBoxLayout,
                           QLineEdit, QPushButton, QTextEdit, QMessageBox, QProgressBar)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont
import platform
import os
from datetime import datetime

from news.src.utils.common_utils import capture_and_generate_news
from news.src.utils.domestic_utils import check_investment_restricted, finance
from news.src.utils.data_manager import data_manager

# ------------------------------------------------------------------
# 기능: 주간(5거래일) 기사 테스트 탭 - stock_tab와 동일한 흐름으로 기사 생성 및 저장
# 주간 OHLC는 info_LLM.py에서 weekly_stock_utils와 연결되어 자동 주입됩니다.
# ------------------------------------------------------------------
class WeeklyWorker(QThread):
    finished = pyqtSignal(str, str)  # combined_news, error
    progress = pyqtSignal(str, str)  # message, current_keyword
    progress_all = pyqtSignal(int, int)  # current, total
    step_progress = pyqtSignal(int, int)  # current_step, total_steps

    def __init__(self, keywords: str):
        super().__init__()
        self.keywords = [k.strip() for k in keywords.split(',') if k.strip()]
        self.results = []
        self.is_running = True

    def stop(self):
        self.is_running = False
        self.quit()
        self.wait()

    def run(self):
        self.results = []
        try:
            if not self.keywords:
                self.finished.emit("", "유효한 키워드가 없습니다.")
                return

            total = len(self.keywords)
            self.progress.emit(f"총 {total}개의 종목을 처리합니다.", "")

            new_listing_statuses = {}

            for idx, keyword in enumerate(self.keywords, 1):
                if not self.is_running:
                    self.progress.emit("작업이 중지되었습니다.", "")
                    return

                self.progress.emit(f"[{idx}/{total}] {keyword} 처리 중...", keyword)
                self.progress_all.emit(idx, total)

                try:
                    stock_code = finance(keyword)

                    is_newly_listed_stock = False
                    if stock_code:
                        try:
                            if data_manager.is_newly_listed(keyword) or data_manager.is_newly_listed(stock_code):
                                new_listing_statuses[keyword] = True
                                is_newly_listed_stock = True
                                message = f"[{keyword}]는 신규상장종목입니다."
                                self.progress.emit(f"✅ {message}", keyword)
                        except Exception as e:
                            print(f"{keyword}의 신규상장 정보 확인 중 오류: {e}")

                        if not is_newly_listed_stock:
                            if check_investment_restricted(stock_code, None, keyword):
                                message = f"[{keyword}]는 거래금지종목입니다."
                                self.results.append((keyword, "", message))
                                self.progress.emit(f"❌ {message}", keyword)
                                continue
                    else:
                        pass

                except Exception as e:
                    message = f"{keyword} 거래금지 확인 중 오류 발생: {str(e)}"
                    self.results.append((keyword, "", message))
                    self.progress.emit(f"❌ {message}", keyword)
                    continue

                try:
                    def progress_callback(msg, k=keyword):
                        if not self.is_running:
                            return
                        self.progress.emit(msg, k)

                    def step_callback(current, total):
                        if not self.is_running:
                            return
                        self.step_progress.emit(current, total)

                    def is_running_callback():
                        return self.is_running

                    news = capture_and_generate_news(
                        keyword,
                        progress_callback=progress_callback,
                        is_running_callback=is_running_callback,
                        step_callback=step_callback,
                        domain="week"  # 주간 전용 도메인
                    )

                    if not self.is_running:
                        self.progress.emit("작업이 중지되었습니다.", "")
                        return

                    if news:
                        self.results.append((keyword, news, ""))
                        self.progress.emit(f"✅ {keyword} 처리 완료", keyword)
                    else:
                        error_msg = f"{keyword}: 기사 생성에 실패했습니다."
                        self.results.append((keyword, "", error_msg))
                        self.progress.emit(f"❌ {error_msg}", keyword)

                except Exception as e:
                    if not self.is_running:
                        self.progress.emit("사용자 요청으로 작업이 중지되었습니다.", "")
                        return
                    error_msg = f"{keyword} 처리 중 오류: {str(e)}"
                    self.results.append((keyword, "", error_msg))
                    self.progress.emit(f"❌ {error_msg}", keyword)

            combined_news = []
            for keyword, news, error in self.results:
                display_keyword = f"[ {keyword} ]"
                if new_listing_statuses.get(keyword):
                    display_keyword = f"[ {keyword} 신규상장입니다. ]"
                if news:
                    combined_news.append(f"{display_keyword}\n{news}")
                elif error:
                    combined_news.append(f"{display_keyword}\n{error}")

            self.finished.emit("\n\n" + "="*50 + "\n".join(combined_news), "")

        except Exception as e:
            self.progress.emit(f"오류 발생: {str(e)}", "")
            self.finished.emit("", str(e))


class WeeklyStockTab(QWidget):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        title_label = QLabel("📅 주간 테스트 (5거래일 OHLC 기사)")
        title_label.setFont(QFont("Arial", 16, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        input_group = QGroupBox("입력")
        input_layout = QVBoxLayout()

        keyword_layout = QHBoxLayout()
        keyword_label = QLabel("회사명 또는 종목코드:")
        self.keyword_input = QLineEdit()
        self.keyword_input.setPlaceholderText("예: 삼성전자, 005930 (여러 개 입력 시 쉼표로 구분)")
        self.keyword_input.returnPressed.connect(self.generate_news)
        keyword_layout.addWidget(keyword_label)
        keyword_layout.addWidget(self.keyword_input)
        input_layout.addLayout(keyword_layout)
        input_group.setLayout(input_layout)
        layout.addWidget(input_group)

        button_layout = QHBoxLayout()
        self.generate_btn = QPushButton("📰 기사 생성")
        self.generate_btn.clicked.connect(self.generate_news)
        self.reset_btn = QPushButton("🔄 리셋")
        self.reset_btn.clicked.connect(self.reset_inputs)
        self.cancel_btn = QPushButton("❌ 취소")
        self.cancel_btn.clicked.connect(self.cancel)
        self.cancel_btn.setEnabled(False)
        self.open_article_folder_btn = QPushButton("📰 기사 폴더 열기")
        self.open_article_folder_btn.clicked.connect(self.open_article_folder)

        button_layout.addWidget(self.generate_btn)
        button_layout.addWidget(self.reset_btn)
        button_layout.addWidget(self.cancel_btn)
        button_layout.addWidget(self.open_article_folder_btn)
        layout.addLayout(button_layout)

        self.progress_label = QLabel("")
        self.progress_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.progress_label)

        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setMinimumHeight(200)
        layout.addWidget(self.result_text)

        self.overall_progress_label = QLabel("전체 진행률")
        self.overall_progress_label.setVisible(False)
        layout.addWidget(self.overall_progress_label)

        self.overall_progress_bar = QProgressBar(self)
        self.overall_progress_bar.setVisible(False)
        self.overall_progress_bar.setFormat("%v / %m")
        layout.addWidget(self.overall_progress_bar)

        self.step_progress_label = QLabel("현재 항목 진행률")
        self.step_progress_label.setVisible(False)
        layout.addWidget(self.step_progress_label)

        self.step_progress_bar = QProgressBar(self)
        self.step_progress_bar.setVisible(False)
        self.step_progress_bar.setTextVisible(True)
        self.step_progress_bar.setFormat('%p%')
        layout.addWidget(self.step_progress_bar)

        self.setLayout(layout)

    def reset_inputs(self):
        self.keyword_input.clear()
        self.result_text.clear()
        self.progress_label.setText("")
        self.generate_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

    def open_article_folder(self):
        today = datetime.now().strftime('%Y%m%d')
        folder_path = os.path.join("생성된 기사", f"기사{today}")
        if os.path.exists(folder_path):
            if platform.system() == "Windows":
                os.startfile(folder_path)
            elif platform.system() == "Darwin":
                os.system(f"open {folder_path}")
            elif platform.system() == "Linux":
                os.system(f"xdg-open {folder_path}")
        else:
            QMessageBox.information(self, "폴더 없음", "아직 생성된 기사가 없습니다.")

    def generate_news(self):
        keywords = self.keyword_input.text().strip()
        if not keywords:
            QMessageBox.warning(self, "입력 오류", "회사명 또는 종목코드를 입력해주세요.")
            return

        self.generate_btn.setEnabled(False)
        self.reset_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.result_text.clear()
        self.progress_label.setText("처리 준비 중...")
        self.result_text.append("주간 기사 생성을 시작합니다...\n" + "="*50 + "\n")

        self.worker = WeeklyWorker(keywords)
        self.worker.progress.connect(self.update_progress)
        self.worker.progress_all.connect(self.update_overall_progress)
        self.worker.step_progress.connect(self.update_step_progress)
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

        self.overall_progress_label.setVisible(False)
        self.overall_progress_bar.setVisible(False)
        self.step_progress_label.setVisible(False)
        self.step_progress_bar.setVisible(False)

    def cancel(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
        self.progress_label.setText("⛔️ 처리 취소됨")
        self.generate_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.reset_btn.setEnabled(True)

    def update_progress(self, message, keyword=""):
        display_msg = f"{keyword}: {message}" if keyword else message
        self.progress_label.setText(display_msg)

        if any(x in message for x in ["✅", "완료", "성공"]):
            self.progress_label.setStyleSheet("color: green;")
        elif any(x in message for x in ["❌", "실패", "오류"]):
            self.progress_label.setStyleSheet("color: red;")
        elif keyword:
            self.progress_label.setStyleSheet("color: blue;")
        else:
            self.progress_label.setStyleSheet("")

        if any(x in message for x in ["✅", "❌", "완료", "실패", "오류"]):
            self.result_text.append(display_msg)
            self.result_text.verticalScrollBar().setValue(self.result_text.verticalScrollBar().maximum())

    def update_overall_progress(self, current, total):
        self.overall_progress_label.setVisible(True)
        self.overall_progress_bar.setVisible(True)
        self.overall_progress_bar.setMaximum(total)
        self.overall_progress_bar.setValue(current)

    def update_step_progress(self, current, total):
        self.step_progress_label.setVisible(True)
        self.step_progress_bar.setVisible(True)
        self.step_progress_bar.setMaximum(total)
        self.step_progress_bar.setValue(current)

    def on_finished(self, news, error):
        self.generate_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.reset_btn.setEnabled(True)

        self.overall_progress_label.setVisible(False)
        self.overall_progress_bar.setVisible(False)
        self.step_progress_label.setVisible(False)
        self.step_progress_bar.setVisible(False)

        if error:
            self.progress_label.setText("")
            QMessageBox.warning(self, "실패", error)
            self.result_text.append(f"❌ 오류 발생: {error}")
            return

        if news and news.strip():
            self.result_text.append("\n" + "="*50 + "\n")
            self.result_text.append("\n✅ 모든 처리가 완료되었습니다!")
            self.progress_label.setText("기사 생성 완료!")
        else:
            self.result_text.append("\n⚠️ 처리할 결과가 없습니다.")
            self.progress_label.setText("처리할 결과가 없습니다.")

        self.result_text.verticalScrollBar().setValue(self.result_text.verticalScrollBar().maximum())
