# gui_loader.py

import sys
import os
from PyQt5.QtWidgets import QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt

from news.src.components.news_tab import NewsTab
from news.src.components.news_tab_test import NewsTabTest
from news.src.components.stock_tab import StockTab
from news.src.components.hwan_tab import HwanTab
from news.src.components.toss_tab import TossTab
from news.src.components.settings_dialog import SettingsDialog

def initialize_environment():
    """PyInstaller로 빌드된 exe가 처음 실행될 때 환경을 초기화합니다."""
    if getattr(sys, 'frozen', False):
        # exe로 빌드된 경우
        if sys.platform == 'win32':
            app_data = os.getenv('APPDATA')
            app_name = 'NewsGenerator'
            app_dir = os.path.join(app_data, app_name)
            
            # 디렉토리 생성
            os.makedirs(app_dir, exist_ok=True)
            
            # .env 파일 경로
            env_path = os.path.join(app_dir, '.env')
            
            # .env 파일이 없으면 기본 템플릿으로 생성
            if not os.path.exists(env_path):
                try:
                    with open(env_path, 'w', encoding='utf-8') as f:
                        f.write("# FromAI News Generator 환경 설정 파일\n")
                        f.write("# Google API Key를 설정하세요\n")
                        f.write("GOOGLE_API_KEY=your_api_key_here\n")
                    print(f"✅ 새로운 .env 파일을 생성했습니다: {env_path}")
                except Exception as e:
                    print(f"⚠️ .env 파일 생성 중 오류: {e}")
            
            # 현재 실행 중인 세션의 환경 변수에 .env 파일 로드
            try:
                from dotenv import load_dotenv
                load_dotenv(env_path)
                print(f"✅ 환경 변수를 로드했습니다: {env_path}")
            except Exception as e:
                print(f"⚠️ 환경 변수 로드 중 오류: {e}")

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-09
# 버전 : 1.0.4
# 기능 : PyQt5에서 메인 윈도우 설정(프론트)
# ------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("통합 뉴스 도구v1.1.5 - 제작자: 최준혁, 곽은규")
        self.setGeometry(100, 100, 800, 600)

        # 메인 레이아웃
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout()

        # 탭 위젯
        tab_widget = QTabWidget()
        tab_widget.addTab(NewsTab(), "📰 뉴스 재구성")
        tab_widget.addTab(NewsTabTest(), "🧪 뉴스 재구성(테스트)")
        tab_widget.addTab(HwanTab(), "💱 환율 차트")
        tab_widget.addTab(StockTab(), "📈 주식 차트")
        tab_widget.addTab(TossTab(), "📈 토스 인기 종목")
        layout.addWidget(tab_widget)

        # 하단 레이아웃 (상태 메시지, 제작자 정보)
        bottom_layout = QVBoxLayout()
        bottom_layout.setSpacing(0)  # 위젯 간 간격 제거
        bottom_layout.setContentsMargins(0, 5, 0, 5)  # 여백 최소화
        
        # 상태 메시지 (가운데 정렬)
        status_label = QLabel("✅ 모든 기능이 준비되었습니다.")
        status_label.setAlignment(Qt.AlignCenter)
        status_label.setStyleSheet("margin-bottom: 0px; padding: 0px;")
        
        # 설정 버튼 (왼쪽에 고정)
        self.settings_btn = QPushButton("⚙️ API 키 설정")
        self.settings_btn.clicked.connect(self.open_settings_dialog)
        self.settings_btn.setFixedWidth(100)  # 고정 너비 설정
        self.settings_btn.setStyleSheet("margin: 0px; padding: 0px;")
        
        # 상태 메시지를 위한 중앙 정렬 레이아웃
        status_layout = QHBoxLayout()
        status_layout.setSpacing(0)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.addStretch()
        status_layout.addWidget(status_label)
        status_layout.addStretch()
        
        # 설정 버튼을 오버레이로 추가하기 위한 컨테이너
        container = QWidget()
        container.setLayout(QHBoxLayout())
        container.layout().setContentsMargins(10, 0, 0, 0)  # 왼쪽에 약간의 여백만 남김
        container.layout().setSpacing(0)
        container.layout().addWidget(self.settings_btn, 0, Qt.AlignLeft | Qt.AlignBottom)
        
        # 메인 레이아웃에 추가
        bottom_layout.addLayout(status_layout)
        bottom_layout.addWidget(container)  # 설정 버튼을 오버레이로 추가
        
        # 제작자 정보 (가운데 정렬)
        creator_label = QLabel("제작자: 최준혁")
        creator_label.setAlignment(Qt.AlignCenter)
        creator_label.setStyleSheet("color: gray; font-size: 10px; margin: 0px; padding: 0px;")
        
        # 레이아웃에 위젯 추가
        bottom_layout.addWidget(creator_label)
        layout.addLayout(bottom_layout)

        central_widget.setLayout(layout)

    def open_settings_dialog(self):
        dialog = SettingsDialog(self)
        dialog.exec_()

def main():
    # PyInstaller로 빌드된 exe의 경우 환경 초기화
    initialize_environment()
    
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setFont(QFont("Arial", 9))

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
