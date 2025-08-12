from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QLineEdit, QPushButton,
    QMessageBox, QCheckBox, QTableWidget, QTableWidgetItem, QProgressBar
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont
import pandas as pd
from news.src.services import toss_service

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-31
# 기능 : PyQt5에서 토스증권 API를 이용한 종목 데이터 추출하는 워커
# ------------------------------------------------------------------
class TossWorker(QThread):
    finished = pyqtSignal(pd.DataFrame, str)

    def __init__(self, min_pct, max_pct, min_price, up_check, down_check, limit, start_rank=1, end_rank=None, only_domestic=False, only_foreign=False):
        super().__init__()
        self.min_pct = min_pct
        self.max_pct = max_pct
        self.min_price = min_price
        self.up_check = up_check
        self.down_check = down_check
        self.limit = limit
        self.start_rank = start_rank
        self.end_rank = end_rank
        self.only_domestic = only_domestic
        self.only_foreign = only_foreign

    def run(self):
        try:
            df = toss_service.get_toss_stock_data(
                start_rank=self.start_rank,
                end_rank=self.end_rank,
                only_domestic=self.only_domestic,
                only_foreign=self.only_foreign
            )
            filtered = toss_service.filter_toss_data(
                df,
                self.min_pct,
                self.max_pct,
                self.min_price,
                self.up_check,
                self.down_check,
                self.limit
            )
            self.finished.emit(filtered, "")
        except Exception as e:
            self.finished.emit(pd.DataFrame(), str(e))

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-31
# 기능 : PyQt5에서 토스증권 API를 이용한 종목 데이터 추출하는 탭
# ------------------------------------------------------------------
# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-08-09
# 기능 : 기사 생성을 백그라운드에서 처리하는 워커
# ------------------------------------------------------------------
class ArticleGeneratorWorker(QThread):
    finished = pyqtSignal(int, str)  # 성공 개수, 에러 메시지
    progress_all = pyqtSignal(int, int, str)  # 현재 진행, 전체 개수, 현재 종목명
    step_progress = pyqtSignal(int, int) # 현재 단계, 전체 단계

    def __init__(self, names, parent=None):
        super().__init__(parent)
        self.names = names
        self._is_running = True

    def run(self):
        try:
            total_count = len(self.names)
            success_cnt = 0
            from news.src.utils.common_utils import capture_and_generate_news
            from datetime import datetime
            import os

            today = datetime.now().strftime('%Y%m%d')
            toss_folder = os.path.join(os.getcwd(), '토스기사', f'토스{today}')
            os.makedirs(toss_folder, exist_ok=True)

            for i, name in enumerate(self.names):
                if not self._is_running:
                    break
                
                self.progress_all.emit(i + 1, total_count, name)
                self.step_progress.emit(0, 3) # 단계 프로그레스 초기화 (총 3단계)

                def step_callback(current, total):
                    if not self._is_running:
                        return
                    self.step_progress.emit(current, total)

                news = capture_and_generate_news(
                    name,
                    domain="toss",
                    open_after_save=False,
                    custom_save_dir=toss_folder,  # 일일 폴더에 저장하도록 경로 수정
                    step_callback=step_callback,
                    is_running_callback=lambda: self._is_running
                )
                if news:
                    success_cnt += 1
            
            if not self._is_running:
                self.finished.emit(success_cnt, "기사 생성이 사용자에 의해 취소되었습니다.")
            else:
                self.finished.emit(success_cnt, "")
        except Exception as e:
            self.finished.emit(0, str(e))

    def stop(self):
        self._is_running = False


class TossTab(QWidget):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.article_worker = None
        self.last_df = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        title = QLabel("📈 토스 인기 종목 추출")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        from PyQt5.QtWidgets import QGridLayout
        input_group = QGroupBox("필터 입력")
        input_layout = QGridLayout()

        # 입력 필드 생성
        self.min_pct_input = QLineEdit()
        self.min_pct_input.setPlaceholderText('최소 등락률 (예: 5)')
        
        self.max_pct_input = QLineEdit()
        self.max_pct_input.setPlaceholderText('최대 등락률 (예: 10)')
        
        self.min_price_input = QLineEdit()
        self.min_price_input.setPlaceholderText('최소 가격 (예: 1000)')
        
        self.limit_input = QLineEdit()
        self.limit_input.setPlaceholderText('가져올 개수 (예: 10)')
        
        self.start_rank_input = QLineEdit()
        self.start_rank_input.setPlaceholderText('시작 순위 (기본: 1)')
        
        self.end_rank_input = QLineEdit()
        self.end_rank_input.setPlaceholderText('끝 순위 (기본: 100)')
        self.up_check = QCheckBox()
        self.down_check = QCheckBox()
        self.domestic_check = QCheckBox()
        self.foreign_check = QCheckBox()

        # 순위
        input_layout.addWidget(QLabel("순위:"), 0, 0)
        input_layout.addWidget(self.start_rank_input, 0, 1)
        input_layout.addWidget(self.end_rank_input, 0, 2)

        # 등락률
        input_layout.addWidget(QLabel("등락률(%):"), 1, 0)
        input_layout.addWidget(self.min_pct_input, 1, 1)
        input_layout.addWidget(self.max_pct_input, 1, 2)

        # 현재가
        input_layout.addWidget(QLabel("최소 현재가:"), 2, 0)
        input_layout.addWidget(self.min_price_input, 2, 1, 1, 2)

        # 상승/하락
        dir_widget = QWidget()
        dir_hbox = QHBoxLayout(dir_widget)
        dir_hbox.setContentsMargins(0, 0, 0, 0)
        dir_hbox.setSpacing(10)
        dir_hbox.addWidget(QLabel("상승"))
        dir_hbox.addWidget(self.up_check)
        dir_hbox.addWidget(QLabel("하락"))
        dir_hbox.addWidget(self.down_check)
        dir_hbox.addStretch()
        input_layout.addWidget(QLabel("상승/하락:"), 3, 0)
        input_layout.addWidget(dir_widget, 3, 1, 1, 2)

        # 국내/해외 
        market_widget = QWidget()
        market_hbox = QHBoxLayout(market_widget)
        market_hbox.setContentsMargins(0, 0, 0, 0)
        market_hbox.setSpacing(10)
        market_hbox.addWidget(QLabel("국내"))
        market_hbox.addWidget(self.domestic_check)
        market_hbox.addWidget(QLabel("해외"))
        market_hbox.addWidget(self.foreign_check)
        market_hbox.addStretch()
        input_layout.addWidget(QLabel("국내/해외:"), 4, 0)
        input_layout.addWidget(market_widget, 4, 1, 1, 2)
        
        # 개수
        input_layout.addWidget(QLabel("가져올 개수:"), 5, 0)
        input_layout.addWidget(self.limit_input, 5, 1, 1, 2)

        input_group.setLayout(input_layout)
        layout.addWidget(input_group)

        # 버튼을 한 줄(HBox)로 배치 (필터 바로 아래)
        button_layout = QHBoxLayout()
        self.extract_btn = QPushButton("📊 조회")
        self.extract_btn.clicked.connect(self.start_extraction)
        button_layout.addWidget(self.extract_btn)

        self.generate_button = QPushButton("📰 기사 생성")
        self.generate_button.clicked.connect(self.generate_articles)
        button_layout.addWidget(self.generate_button)

        self.cancel_generate_button = QPushButton("❌ 취소")
        self.cancel_generate_button.clicked.connect(self.cancel_generation)
        self.cancel_generate_button.setEnabled(False)
        button_layout.addWidget(self.cancel_generate_button)

        self.reset_btn = QPushButton("🔄 리셋")
        self.reset_btn.clicked.connect(self.reset_inputs)
        button_layout.addWidget(self.reset_btn)

        self.open_toss_folder_btn = QPushButton("📁 토스 기사 폴더 열기")
        self.open_toss_folder_btn.clicked.connect(self.open_toss_article_folder)
        button_layout.addWidget(self.open_toss_folder_btn)

        layout.addLayout(button_layout)

        # 결과 표시 테이블
        self.result_table = QTableWidget()
        layout.addWidget(self.result_table)

        # 기사 생성 진행률 표시
        self.overall_progress_label = QLabel("전체 진행률")
        self.overall_progress_bar = QProgressBar()
        self.overall_progress_bar.setFormat("%v / %m")
        progress_layout = QHBoxLayout()
        progress_layout.addWidget(self.overall_progress_label)
        progress_layout.addWidget(self.overall_progress_bar)

        # 현재 항목 진행률
        self.step_progress_label = QLabel("현재 항목 진행률")
        self.step_progress_bar = QProgressBar()
        self.step_progress_bar.setFormat("%p%")
        progress_layout.addWidget(self.step_progress_label)
        progress_layout.addWidget(self.step_progress_bar)

        self.overall_progress_label.setVisible(False)
        self.overall_progress_bar.setVisible(False)
        self.step_progress_label.setVisible(False)
        self.step_progress_bar.setVisible(False)
        layout.addLayout(progress_layout)

        self.setLayout(layout)
 
    def reset_inputs(self):
        self.min_pct_input.clear()
        self.max_pct_input.clear()
        self.min_price_input.clear()
        self.limit_input.clear()
        self.start_rank_input.clear()
        self.end_rank_input.clear()
        self.up_check.setChecked(False)
        self.down_check.setChecked(False)
        self.domestic_check.setChecked(False)
        self.foreign_check.setChecked(False)
        self.result_table.setRowCount(0)
        self.cancel_generate_button.setEnabled(False)
        self.extract_btn.setEnabled(True)
        self.generate_button.setEnabled(True)

    def cancel_extraction(self):
        # 토스 워커 취소 (Thread 강제 종료)
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
        self.cancel_generate_button.setEnabled(False)
        self.extract_btn.setEnabled(True)
        self.generate_button.setEnabled(True)
        QMessageBox.information(self, "취소됨", "데이터 조회/기사 생성을 취소했습니다.")

    def start_extraction(self):
        try:
            min_pct = float(self.min_pct_input.text().strip()) if self.min_pct_input.text().strip() else None
            max_pct = float(self.max_pct_input.text().strip()) if self.max_pct_input.text().strip() else None
            min_price = int(self.min_price_input.text().strip()) if self.min_price_input.text().strip() else None
            limit = int(self.limit_input.text().strip()) if self.limit_input.text().strip() else None
            start_rank = int(self.start_rank_input.text().strip()) if self.start_rank_input.text().strip() else 1
            end_rank = int(self.end_rank_input.text().strip()) if self.end_rank_input.text().strip() else None
        except ValueError:
            QMessageBox.warning(self, "입력 오류", "숫자 입력값을 확인하세요.")
            return

        # 진행률/상태 초기화
        self.overall_progress_label.setVisible(False)
        self.overall_progress_bar.setVisible(False)
        self.step_progress_label.setVisible(False)
        self.step_progress_bar.setVisible(False)

        self.worker = TossWorker(
            min_pct, max_pct, min_price,
            self.up_check.isChecked(),
            self.down_check.isChecked(),
            limit,
            start_rank,
            end_rank,
            self.domestic_check.isChecked(),
            self.foreign_check.isChecked()
        )
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

    # 기사 생성 함수 (토스 인기 종목)
    def generate_articles(self):
        if self.last_df is None or self.last_df.empty:
            QMessageBox.warning(self, "오류", "조회된 데이터가 없습니다.")
            return

        names = self.last_df['종목명'].tolist()
        reply = QMessageBox.question(
            self,
            '기사 생성 확인',
            f"{len(names)}개 종목에 대한 기사를 생성하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.generate_button.setEnabled(False)
            self.cancel_generate_button.setEnabled(True)

            self.overall_progress_label.setVisible(True)
            self.overall_progress_bar.setVisible(True)
            self.overall_progress_bar.setMaximum(len(names))
            self.overall_progress_bar.setValue(0)

            self.step_progress_label.setVisible(True)
            self.step_progress_bar.setVisible(True)
            self.step_progress_bar.setValue(0)

            self.article_worker = ArticleGeneratorWorker(names)
            self.article_worker.progress_all.connect(self.on_overall_progress)
            self.article_worker.step_progress.connect(self.on_step_progress)
            self.article_worker.finished.connect(self.on_article_generation_finished)
            self.article_worker.start()

    def cancel_generation(self):
        if self.article_worker and self.article_worker.isRunning():
            self.article_worker.stop()
            self.cancel_generate_button.setEnabled(False)

    def on_overall_progress(self, current, total, name):
        self.overall_progress_bar.setMaximum(total)
        self.overall_progress_bar.setValue(current)
        self.overall_progress_label.setText(f"전체 진행률: {current}/{total} - '{name}' 처리 중...")
        self.step_progress_bar.setValue(0) # 새 항목 시작 시 초기화

    def on_step_progress(self, current, total):
        self.step_progress_bar.setMaximum(total)
        self.step_progress_bar.setValue(current)

    def on_article_generation_finished(self, success_count, error_msg):
        self.generate_button.setEnabled(True)
        self.cancel_generate_button.setEnabled(False)
        self.overall_progress_label.setVisible(False)
        self.overall_progress_bar.setVisible(False)
        self.step_progress_label.setVisible(False)
        self.step_progress_bar.setVisible(False)

        if error_msg and "취소" not in error_msg:
            QMessageBox.critical(self, "오류 발생", f"기사 생성 중 오류가 발생했습니다: {error_msg}")
        elif error_msg:
             QMessageBox.information(self, "취소됨", f"{success_count}개 기사 생성 후 중단되었습니다.")
        else:
            QMessageBox.information(self, "기사 생성 완료", f"{success_count}개 토스 기사 생성 및 저장이 완료되었습니다.")
        
        self.article_worker = None

    # 토스 기사 폴더 열기 함수
    def open_toss_article_folder(self):
        from datetime import datetime
        import os, platform
        today = datetime.now().strftime('%Y%m%d')
        folder_path = os.path.join(os.getcwd(), '토스기사', f'토스{today}')
        if os.path.exists(folder_path):
            if platform.system() == "Windows":
                os.startfile(folder_path)
            elif platform.system() == "Darwin":
                os.system(f"open {folder_path}")
            elif platform.system() == "Linux":
                os.system(f"xdg-open {folder_path}")
        else:
            QMessageBox.information(self, "폴더 없음", "아직 생성된 토스 기사가 없습니다.")

    def on_finished(self, df, error):
        from PyQt5.QtGui import QColor
        # 최근 조회된 DataFrame 저장 변수 보장
        if not hasattr(self, 'last_df'):
            self.last_df = None
        # 최근 조회된 DataFrame 저장
        self.last_df = df.copy() if df is not None else None
        if error:
            QMessageBox.warning(self, "오류 발생", error)
            return

        if df.empty:
            QMessageBox.information(self, "결과 없음", "조건에 맞는 종목이 없습니다.")
            self.result_table.setRowCount(0)
            return

        self.result_table.setColumnCount(len(df.columns))
        self.result_table.setRowCount(len(df))
        self.result_table.setHorizontalHeaderLabels(df.columns)

        for i in range(len(df)):
            for j, col in enumerate(df.columns):
                value = str(df.iloc[i, j])
                item = QTableWidgetItem(value)

                # 등락 컬럼: 색상 적용
                if col == "등락":
                    if value == "UP":
                        item.setForeground(QColor("red"))
                    elif value == "DOWN":
                        item.setForeground(QColor("blue"))

                # 등락률(%) 컬럼: 오른쪽 정렬, % 붙이기
                elif col == "등락률(%)":
                    # 이미 %가 붙어 있지 않으면 붙이기
                    if not value.endswith("%"):
                        try:
                            value = f"{float(value):.2f}%"
                            item.setText(value)
                        except:
                            pass
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

                self.result_table.setItem(i, j, item)

        self.result_table.resizeColumnsToContents()

