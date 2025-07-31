from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QLineEdit, QPushButton, QMessageBox, QCheckBox, QTableWidget, QTableWidgetItem
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QColor
import pandas as pd
import os, platform
from datetime import datetime
from news.src.services import toss_service
from news.src.utils.capture_utils import (
    capture_wrap_company_area,
    capture_naver_foreign_stock_chart,
    get_stock_info_from_search,
    capture_and_generate_news
)
import shutil

# ✅ 토스 API 데이터 조회용 워커
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

# ✅ 기사+차트 생성용 워커
class ArticleWorker(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(int)

    def __init__(self, names, folder):
        super().__init__()
        self.names = names
        self.folder = folder
        self._cancel = False

    def run(self):
        success_cnt = 0
        for name in self.names:
            if self._cancel:
                break

            self.progress.emit(f"{name} 기사+차트 생성 중...")

            stock_code = get_stock_info_from_search(name)
            if stock_code:
                img_path, *_ = capture_wrap_company_area(stock_code)
            else:
                img_path, _, _ = capture_naver_foreign_stock_chart(name)

            safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in name)

            # ✅ 캡처 이미지 토스 폴더로 이동
            if img_path and os.path.exists(img_path):
                new_img_path = os.path.join(self.folder, f"{safe_name}_chart.png")
                try:
                    shutil.move(img_path, new_img_path)
                except:
                    shutil.copy(img_path, new_img_path)

            # ✅ 기사 생성 후 토스 폴더에만 저장
            news = capture_and_generate_news(name, domain="stock")
            if news:
                news_path = os.path.join(self.folder, f"{safe_name}_기사.txt")
                with open(news_path, "w", encoding="utf-8") as f:
                    f.write(news)
                success_cnt += 1

        self.finished.emit(success_cnt)

    def stop(self):
        self._cancel = True

# ✅ TossTab UI 클래스
class TossTab(QWidget):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.article_worker = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        title = QLabel("📈 토스 인기 종목 추출")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        input_group = QGroupBox("필터 입력")
        input_layout = QVBoxLayout()
        self.min_pct_input = QLineEdit(); self.min_pct_input.setPlaceholderText("최소 등락률 %")
        self.max_pct_input = QLineEdit(); self.max_pct_input.setPlaceholderText("최대 등락률 %")
        self.min_price_input = QLineEdit(); self.min_price_input.setPlaceholderText("최소 현재가 (KRW)")
        self.up_check = QCheckBox("상승만")
        self.down_check = QCheckBox("하락만")
        self.limit_input = QLineEdit(); self.limit_input.setPlaceholderText("가져올 개수")

        for w in [self.min_pct_input, self.max_pct_input, self.min_price_input,
                  self.up_check, self.down_check, self.limit_input]:
            input_layout.addWidget(w)

        input_group.setLayout(input_layout)
        layout.addWidget(input_group)

        # 버튼들
        button_layout = QHBoxLayout()
        self.extract_btn = QPushButton("📊 조회")
        self.extract_btn.clicked.connect(self.start_extraction)
        button_layout.addWidget(self.extract_btn)

        self.generate_articles_btn = QPushButton("📰 기사+차트 생성")
        self.generate_articles_btn.clicked.connect(self.generate_articles)
        button_layout.addWidget(self.generate_articles_btn)

        self.reset_btn = QPushButton("🔄 리셋")
        self.reset_btn.clicked.connect(self.reset_inputs)
        button_layout.addWidget(self.reset_btn)

        self.cancel_btn = QPushButton("❌ 취소")
        self.cancel_btn.clicked.connect(self.cancel_task)
        self.cancel_btn.setEnabled(False)
        button_layout.addWidget(self.cancel_btn)

        self.open_folder_btn = QPushButton("📁 토스 폴더 열기")
        self.open_folder_btn.clicked.connect(self.open_toss_folder)
        button_layout.addWidget(self.open_folder_btn)

        layout.addLayout(button_layout)

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

    def cancel_task(self):
        if self.article_worker and self.article_worker.isRunning():
            self.article_worker.stop()
        if self.worker and self.worker.isRunning():
            self.worker.terminate()

        self.cancel_btn.setEnabled(False)
        QMessageBox.information(self, "취소됨", "작업이 취소되었습니다.")

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

    def generate_articles(self):
        if not hasattr(self, "last_df") or self.last_df.empty:
            QMessageBox.warning(self, "오류", "조회된 데이터가 없습니다.")
            return

        names = self.last_df["종목명"].tolist()
        reply = QMessageBox.question(
            self,
            "기사 생성 확인",
            f"총 {len(names)}개 종목에 대해 기사+차트를 생성하시겠습니까?\n\n" + "\n".join(names),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        today = datetime.now().strftime("%Y%m%d")
        self.folder = os.path.join(os.getcwd(), "토스", f"토스{today}")
        os.makedirs(self.folder, exist_ok=True)

        self.article_worker = ArticleWorker(names, self.folder)
        self.article_worker.finished.connect(self.on_articles_finished)
        self.article_worker.start()
        self.cancel_btn.setEnabled(True)

    def on_articles_finished(self, count):
        QMessageBox.information(self, "완료", f"{count}개 기사+차트 생성 완료!")
        self.cancel_btn.setEnabled(False)

    def on_finished(self, df, error):
        if error:
            QMessageBox.warning(self, "오류 발생", error)
            return

        if df.empty:
            QMessageBox.information(self, "결과 없음", "조건에 맞는 종목이 없습니다.")
            self.result_table.setRowCount(0)
            return

        self.last_df = df.copy()
        self.result_table.setColumnCount(len(df.columns))
        self.result_table.setRowCount(len(df))
        self.result_table.setHorizontalHeaderLabels(df.columns)

        for i in range(len(df)):
            for j, col in enumerate(df.columns):
                value = str(df.iloc[i, j])
                item = QTableWidgetItem(value)
                if col == "등락":
                    item.setForeground(QColor("red") if value == "UP" else QColor("blue"))
                elif col == "등락률(%)":
                    try:
                        item.setText(f"{float(value):.2f}%")
                    except:
                        pass
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.result_table.setItem(i, j, item)

        self.result_table.resizeColumnsToContents()

    def open_toss_folder(self):
        today = datetime.now().strftime("%Y%m%d")
        folder = os.path.join(os.getcwd(), "토스", f"토스{today}")
        if os.path.exists(folder):
            if platform.system() == "Windows":
                os.startfile(folder)
            elif platform.system() == "Darwin":
                os.system(f"open {folder}")
            else:
                os.system(f"xdg-open {folder}")
        else:
            QMessageBox.information(self, "폴더 없음", "아직 생성된 파일이 없습니다.")
