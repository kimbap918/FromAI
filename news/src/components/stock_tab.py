# stock_tab.py

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
# 작성자 : 최준혁
# 작성일 : 2025-07-09
# 버전 : 1.0.0
# 기능 : PyQt5에서 주식 코드 검색 후 차트 캡처하는 기능
# ------------------------------------------------------------------
class StockWorker(QThread):
    # 다중 주식 처리 모드 
    finished = pyqtSignal(str, str)  # combined_news, error
    progress = pyqtSignal(str, str)  # message, current_keyword
    progress_all = pyqtSignal(int, int)  # current, total
    step_progress = pyqtSignal(int, int)  # current_step, total_steps

    def __init__(self, keywords):
        super().__init__()
        # 다중 주식 처리 모드 
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
                # 더 자주 취소 체크를 위해 루프 시작 시 확인
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
                            # 신규상장 확인 로직을 'or' 조건으로 변경하여 안정성 향상
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
                    # 진행 상황 콜백 래퍼
                    def progress_callback(msg, k=keyword):
                        # UI 업데이트 전에 취소 확인
                        if not self.is_running:
                            return
                        self.progress.emit(msg, k)
                    
                    # 단계 진행 상황 콜백
                    def step_callback(current, total):
                        if not self.is_running:
                            return
                        self.step_progress.emit(current, total)
                    
                    # 취소 확인을 위한 콜백
                    def is_running_callback():
                        return self.is_running
                    
                    # 비동기로 실행하거나, 실행 중간에 취소 체크를 더 자주 할 수 있도록 수정
                    news = capture_and_generate_news(
                        keyword, 
                        progress_callback=progress_callback,
                        is_running_callback=is_running_callback,
                        step_callback=step_callback
                    )
                    
                    # 결과 처리 전 취소 확인
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

            # Combine all results
            combined_news = []
            for keyword, news, error in self.results:
                display_keyword = f"[ {keyword} ]"
                if new_listing_statuses.get(keyword): # get(keyword)는 키가 없으면 None을 반환하여 안전
                    display_keyword = f"[ {keyword} 신규상장입니다. ]"
                if news:
                    combined_news.append(f"{display_keyword}\n{news}")
                elif error:
                    combined_news.append(f"{display_keyword}\n{error}")

            self.finished.emit("\n\n" + "="*50 + "\n\n".join(combined_news), "")
            
        except Exception as e:
            self.progress.emit(f"오류 발생: {str(e)}", "")
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
        self.keyword_input.setPlaceholderText("예: 삼성전자, 005930, 애플, AAPL (여러 개 입력 시 쉼표로 구분)")
        self.keyword_input.returnPressed.connect(self.capture_chart)
        keyword_layout.addWidget(keyword_label)
        keyword_layout.addWidget(self.keyword_input)
        input_layout.addLayout(keyword_layout)
        input_group.setLayout(input_layout)
        layout.addWidget(input_group)

        button_layout = QHBoxLayout()
        self.capture_btn = QPushButton("📰 기사 생성")
        self.capture_btn.clicked.connect(self.capture_chart)
        self.reset_btn = QPushButton("🔄 리셋")
        self.reset_btn.clicked.connect(self.reset_inputs)
        self.cancel_btn = QPushButton("❌ 취소")
        self.cancel_btn.clicked.connect(self.cancel_capture)
        self.cancel_btn.setEnabled(False)
        self.open_article_folder_btn = QPushButton("📰 기사 폴더 열기")
        self.open_article_folder_btn.clicked.connect(self.open_article_folder)

        button_layout.addWidget(self.capture_btn)
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

        # 전체 진행률 프로그레스바
        self.overall_progress_label = QLabel("전체 진행률")
        self.overall_progress_label.setVisible(False)
        layout.addWidget(self.overall_progress_label)

        self.overall_progress_bar = QProgressBar(self)
        self.overall_progress_bar.setVisible(False)
        self.overall_progress_bar.setFormat("%v / %m")
        layout.addWidget(self.overall_progress_bar)

        # 현재 항목 단계별 프로그레스바
        self.step_progress_label = QLabel("현재 항목 진행률")
        self.step_progress_label.setVisible(False)
        layout.addWidget(self.step_progress_label)

        self.step_progress_bar = QProgressBar(self)
        self.step_progress_bar.setVisible(False)
        self.step_progress_bar.setTextVisible(True)
        self.step_progress_bar.setFormat('%p%')
        layout.addWidget(self.step_progress_bar)

        self.setLayout(layout)

    # ------------------------------------------------------------------
    # 작성자 : 최준혁
    # 작성일 : 2025-07-09
    # 기능 : PyQt5에서 입력 필드 리셋하는 함수(프론트)
    # ------------------------------------------------------------------
    def reset_inputs(self):
        self.keyword_input.clear()
        self.result_text.clear()
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
    # 기사 폴더 열기 (오늘 날짜 기준)
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # 작성자 : 최준혁
    # 작성일 : 2025-07-09
    # 기능 : PyQt5에서 주식 차트 캡처 함수(프론트)
    # ------------------------------------------------------------------
    def capture_chart(self):
        keywords = self.keyword_input.text().strip()
        if not keywords:
            QMessageBox.warning(self, "입력 오류", "주식 코드 또는 회사명을 입력해주세요.")
            return

        self.capture_btn.setEnabled(False)
        self.reset_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.result_text.clear()
        self.progress_label.setText("처리 준비 중...")
        self.result_text.append("주식 차트 및 기사 생성을 시작합니다...\n" + "="*50 + "\n")

        self.worker = StockWorker(keywords)
        self.worker.progress.connect(self.update_progress)
        self.worker.progress_all.connect(self.update_overall_progress)
        self.worker.step_progress.connect(self.update_step_progress)
        self.worker.finished.connect(self.on_capture_finished)
        self.worker.start()
        
        # Reset progress bars
        self.overall_progress_label.setVisible(False)
        self.overall_progress_bar.setVisible(False)
        self.step_progress_label.setVisible(False)
        self.step_progress_bar.setVisible(False)

    # ------------------------------------------------------------------
    # 작성자 : 최준혁
    # 작성일 : 2025-07-09
    # 기능 : PyQt5에서 주식 차트 캡처 취소 함수(프론트)
    # ------------------------------------------------------------------
    def cancel_capture(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
        self.progress_label.setText("⛔️ 처리 취소됨")
        self.capture_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.reset_btn.setEnabled(True)

    # ------------------------------------------------------------------
    # 작성자 : 최준혁
    # 작성일 : 2025-07-09
    # 기능 : PyQt5에서 주식 차트 캡처 진행 상태 업데이트하는 함수(프론트)
    # ------------------------------------------------------------------
    def update_progress(self, message, keyword=""):
        display_msg = f"{keyword}: {message}" if keyword else message
        self.progress_label.setText(display_msg)
        
        # Update style based on message content
        if any(x in message for x in ["✅", "완료", "성공"]):
            self.progress_label.setStyleSheet("color: green;")
        elif any(x in message for x in ["❌", "실패", "오류"]):
            self.progress_label.setStyleSheet("color: red;")
        elif keyword:
            self.progress_label.setStyleSheet("color: blue;")
        else:
            self.progress_label.setStyleSheet("")
            
        # Add important messages to the result text
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

    def append_to_result(self, message, keyword=""):
        display_msg = f"{keyword}: {message}" if keyword else message
        self.result_text.append(display_msg)
        self.result_text.verticalScrollBar().setValue(self.result_text.verticalScrollBar().maximum())

    # ------------------------------------------------------------------
    # 작성자 : 최준혁
    # 작성일 : 2025-07-09
    # 기능 : PyQt5에서 주식 차트 캡처 완료 시 처리하는 함수(프론트)
    # ------------------------------------------------------------------
    def on_capture_finished(self, news, error):
        self.capture_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.reset_btn.setEnabled(True)
        
        # Hide progress bars when done
        self.overall_progress_label.setVisible(False)
        self.overall_progress_bar.setVisible(False)
        self.step_progress_label.setVisible(False)
        self.step_progress_bar.setVisible(False)
        
        if error:
            self.progress_label.setText("")
            QMessageBox.warning(self, "실패", error)
            self.result_text.append(f"❌ 오류 발생: {error}")
            return
            
        # Display completion status without showing the actual news content
        if news and news.strip():
            self.result_text.append("\n" + "="*50 + "\n")
            self.result_text.append("\n✅ 모든 처리가 완료되었습니다!")
            self.progress_label.setText("기사 생성 완료!")
        else:
            self.result_text.append("\n⚠️ 처리할 결과가 없습니다.")
            self.progress_label.setText("처리할 결과가 없습니다.")
            
        # Scroll to the bottom to show the latest messages
        self.result_text.verticalScrollBar().setValue(self.result_text.verticalScrollBar().maximum())