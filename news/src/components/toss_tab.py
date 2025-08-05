from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QLineEdit, QPushButton,
    QMessageBox, QCheckBox, QTableWidget, QTableWidgetItem
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

    def __init__(self, min_pct, max_pct, min_price, up_check, down_check, limit, start_rank=1, end_rank=None):
        super().__init__()
        self.min_pct = min_pct
        self.max_pct = max_pct
        self.min_price = min_price
        self.up_check = up_check
        self.down_check = down_check
        self.limit = limit
        self.start_rank = start_rank
        self.end_rank = end_rank

    def run(self):
        try:
            df = toss_service.get_toss_stock_data(start_rank=self.start_rank, end_rank=self.end_rank)
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
class TossTab(QWidget):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        title = QLabel("📈 토스 인기 종목 추출")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        input_group = QGroupBox("필터 입력")
        input_layout = QVBoxLayout()

        self.min_pct_input = QLineEdit()
        self.min_pct_input.setPlaceholderText("최소 등락률 %")
        self.max_pct_input = QLineEdit()
        self.max_pct_input.setPlaceholderText("최대 등락률 %")
        self.min_price_input = QLineEdit()
        self.min_price_input.setPlaceholderText("최소 현재가 (KRW)")

        self.up_check = QCheckBox("상승만")
        self.down_check = QCheckBox("하락만")

        self.limit_input = QLineEdit()
        self.limit_input.setPlaceholderText("가져올 개수")

        self.start_rank_input = QLineEdit()
        self.start_rank_input.setPlaceholderText("시작 순위 (예: 1)")
        self.end_rank_input = QLineEdit()
        self.end_rank_input.setPlaceholderText("끝 순위 (예: 30)")

        input_layout.addWidget(self.start_rank_input)
        input_layout.addWidget(self.end_rank_input)
        input_layout.addWidget(self.min_pct_input)
        input_layout.addWidget(self.max_pct_input)
        input_layout.addWidget(self.min_price_input)
        input_layout.addWidget(self.up_check)
        input_layout.addWidget(self.down_check)
        input_layout.addWidget(self.limit_input)

        # 엔터 입력 시 조회
        self.start_rank_input.returnPressed.connect(self.start_extraction)
        self.end_rank_input.returnPressed.connect(self.start_extraction)
        self.min_pct_input.returnPressed.connect(self.start_extraction)
        self.max_pct_input.returnPressed.connect(self.start_extraction)
        self.min_price_input.returnPressed.connect(self.start_extraction)
        self.limit_input.returnPressed.connect(self.start_extraction)

        input_group.setLayout(input_layout)
        layout.addWidget(input_group)

        # 버튼을 한 줄(HBox)로 배치
        button_layout = QHBoxLayout()
        self.extract_btn = QPushButton("📊 조회")
        self.extract_btn.clicked.connect(self.start_extraction)
        button_layout.addWidget(self.extract_btn)

        self.generate_articles_btn = QPushButton("📰 기사 생성")
        self.generate_articles_btn.clicked.connect(self.generate_articles)
        button_layout.addWidget(self.generate_articles_btn)

        self.reset_btn = QPushButton("🔄 리셋")
        self.reset_btn.clicked.connect(self.reset_inputs)
        button_layout.addWidget(self.reset_btn)

        self.cancel_btn = QPushButton("❌ 취소")
        self.cancel_btn.clicked.connect(self.cancel_extraction)
        self.cancel_btn.setEnabled(False)
        button_layout.addWidget(self.cancel_btn)

        self.open_toss_folder_btn = QPushButton("📁 토스 기사 폴더 열기")
        self.open_toss_folder_btn.clicked.connect(self.open_toss_article_folder)
        button_layout.addWidget(self.open_toss_folder_btn)

        layout.addLayout(button_layout)

        # ✅ 표 형태로 결과를 표시
        self.result_table = QTableWidget()
        layout.addWidget(self.result_table)

        self.setLayout(layout)

    def reset_inputs(self):
        self.min_pct_input.clear()
        self.max_pct_input.clear()
        self.min_price_input.clear()
        self.limit_input.clear()
        self.up_check.setChecked(False)
        self.down_check.setChecked(False)
        self.result_table.setRowCount(0)
        self.cancel_btn.setEnabled(False)
        self.extract_btn.setEnabled(True)
        self.generate_articles_btn.setEnabled(True)

    def cancel_extraction(self):
        # 토스 워커 취소 (Thread 강제 종료)
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
        self.cancel_btn.setEnabled(False)
        self.extract_btn.setEnabled(True)
        self.generate_articles_btn.setEnabled(True)
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

        self.worker = TossWorker(
            min_pct, max_pct, min_price,
            self.up_check.isChecked(),
            self.down_check.isChecked(),
            limit,
            start_rank,
            end_rank
        )
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

    # 기사 생성 함수 (토스 인기 종목)
    def generate_articles(self):
        # 최근 조회된 DataFrame이 있으면 종목명만 추출
        if hasattr(self, 'last_df') and self.last_df is not None and not self.last_df.empty:
            names = self.last_df['종목명'].tolist()
            names_str = '\n'.join(names)
            # 재확인 모달
            reply = QMessageBox.question(
                self,
                "기사 생성 확인",
                f"총 {len(names)}개 종목에 대해 토스 인기기사 생성/저장 하시겠습니까?\n\n{names_str}",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                from news.src.utils.common_utils import capture_and_generate_news
                from datetime import datetime
                import os
                today = datetime.now().strftime('%Y%m%d')
                toss_folder = os.path.join(os.getcwd(), '토스기사', f'토스{today}')
                os.makedirs(toss_folder, exist_ok=True)
                success_cnt = 0
                for name in names:
                    news = capture_and_generate_news(name, domain="stock")
                    if news:
                        # 기사 저장 (토스 폴더에 저장)
                        filename = f"{name}_toss_news.txt"
                        file_path = os.path.join(toss_folder, filename)
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(news)
                        success_cnt += 1
                QMessageBox.information(self, "기사 생성 완료", f"{success_cnt}개 토스 기사 생성 및 저장 완료!")
            else:
                QMessageBox.information(self, "취소됨", "기사 생성이 취소되었습니다.")
        else:
            QMessageBox.warning(self, "오류", "조회된 데이터가 없습니다.")

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

