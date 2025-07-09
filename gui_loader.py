# gui_loader.py

import sys
import os
from PyQt5.QtWidgets import QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QLabel
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt

from news.src.components.news_tab import NewsTab
from news.src.components.stock_tab import StockTab
from news.src.components.hwan_tab import HwanTab

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-09
# 버전 : 1.0.0
# 기능 : PyQt5에서 메인 윈도우 설정(프론트)
# ------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("통합 뉴스 도구 - 제작자: 최준혁")
        self.setGeometry(100, 100, 800, 600)

        # 메인 레이아웃
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout()

        # 탭 위젯
        tab_widget = QTabWidget()
        tab_widget.addTab(NewsTab(), "📰 뉴스 재구성")
        tab_widget.addTab(HwanTab(), "💱 환율 차트")
        tab_widget.addTab(StockTab(), "📈 주식 차트")
        layout.addWidget(tab_widget)

        # 상태 라벨
        status_label = QLabel("✅ 모든 기능이 준비되었습니다.")
        status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(status_label)

        # 제작자 정보
        creator_label = QLabel("제작자: 최준혁")
        creator_label.setAlignment(Qt.AlignCenter)
        creator_label.setStyleSheet("color: gray; font-size: 10px; margin-top: 5px;")
        layout.addWidget(creator_label)

        central_widget.setLayout(layout)


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setFont(QFont("Arial", 9))

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
