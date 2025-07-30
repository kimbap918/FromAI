from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QGroupBox, QLineEdit, QPushButton,
    QMessageBox, QCheckBox, QTableWidget, QTableWidgetItem
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont
import pandas as pd
from news.src.services import toss_service


class TossWorker(QThread):
    finished = pyqtSignal(pd.DataFrame, str)

    def __init__(self, min_pct, max_pct, min_price, up_check, down_check, limit):
        super().__init__()
        self.min_pct = min_pct
        self.max_pct = max_pct
        self.min_price = min_price
        self.up_check = up_check
        self.down_check = down_check
        self.limit = limit

    def run(self):
        try:
            df = toss_service.get_toss_stock_data()
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

        for w in [self.min_pct_input, self.max_pct_input, self.min_price_input, self.up_check, self.down_check, self.limit_input]:
            input_layout.addWidget(w)

        input_group.setLayout(input_layout)
        layout.addWidget(input_group)

        self.extract_btn = QPushButton("📊 추출")
        self.extract_btn.clicked.connect(self.start_extraction)
        layout.addWidget(self.extract_btn)

        # ✅ 표 형태로 결과를 표시
        self.result_table = QTableWidget()
        layout.addWidget(self.result_table)

        self.setLayout(layout)

    def start_extraction(self):
        try:
            min_pct = float(self.min_pct_input.text()) if self.min_pct_input.text() else None
            max_pct = float(self.max_pct_input.text()) if self.max_pct_input.text() else None
            min_price = int(self.min_price_input.text()) if self.min_price_input.text() else None
            limit = int(self.limit_input.text()) if self.limit_input.text() else None
        except ValueError:
            QMessageBox.warning(self, "입력 오류", "숫자 입력값을 확인하세요.")
            return

        self.worker = TossWorker(
            min_pct, max_pct, min_price,
            self.up_check.isChecked(),
            self.down_check.isChecked(),
            limit
        )
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

    def on_finished(self, df, error):
        if error:
            QMessageBox.warning(self, "오류 발생", error)
            return

        if df.empty:
            QMessageBox.information(self, "결과 없음", "조건에 맞는 종목이 없습니다.")
            self.result_table.setRowCount(0)
            return

        # ✅ DataFrame → TableWidget 변환
        self.result_table.setColumnCount(len(df.columns))
        self.result_table.setRowCount(len(df))
        self.result_table.setHorizontalHeaderLabels(df.columns)

        for i in range(len(df)):
            for j in range(len(df.columns)):
                value = str(df.iloc[i, j])
                self.result_table.setItem(i, j, QTableWidgetItem(value))

        self.result_table.resizeColumnsToContents()
