import sys
import os
from pathlib import Path
from dotenv import load_dotenv
from PyQt5.QtWidgets import (QApplication, QMainWindow, QTabWidget, QWidget, 
                            QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                            QDialog, QLineEdit, QMessageBox, QAction)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt

from news.src.components.news_tab import NewsTab
from news.src.components.news_tab_test import NewsTabTest
from news.src.components.stock_tab import StockTab
from news.src.components.hwan_tab import HwanTab
from news.src.components.toss_tab import TossTab
from news.src.components.settings_dialog import SettingsDialog

def get_env_path():
    """환경 설정 파일 경로를 반환합니다."""
    if getattr(sys, 'frozen', False) and sys.platform == 'win32':
        # exe로 빌드된 경우
        app_data = os.getenv('APPDATA')
        app_name = 'NewsGenerator'
        return Path(app_data) / app_name / '.env'
    else:
        # 개발 환경
        return Path(__file__).parent / '.env'

def update_api_key(api_key: str):
    """API 키를 업데이트하고 .env 파일에 저장합니다."""
    env_path = get_env_path()
    env_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 기존 .env 파일이 있으면 읽기 (API 키 제외)
    existing_content = []
    if env_path.exists():
        with open(env_path, 'r', encoding='utf-8') as f:
            existing_content = [line.strip() for line in f if line.strip() and not line.strip().startswith('GOOGLE_API_KEY=')]
    
    # 새로운 API 키와 함께 파일 쓰기
    with open(env_path, 'w', encoding='utf-8') as f:
        for line in existing_content:
            f.write(f"{line}\n")
        f.write(f"GOOGLE_API_KEY={api_key}\n")
    
    # 환경 변수 다시 로드
    load_dotenv(env_path, override=True)
    return True

def initialize_environment():
    """PyInstaller로 빌드된 exe가 처음 실행될 때 환경을 초기화합니다."""
    env_path = get_env_path()
    env_path.parent.mkdir(parents=True, exist_ok=True)
    
    # .env 파일이 없으면 기본 템플릿으로 생성
    if not env_path.exists():
        with open(env_path, 'w', encoding='utf-8') as f:
            f.write("# FromAI News Generator 환경 설정 파일\n")
            f.write("# Google API Key를 설정하세요\n")
            f.write("GOOGLE_API_KEY=your_api_key_here\n")
    
    # 환경 변수 로드
    load_dotenv(env_path, override=True)
    return str(env_path)


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
        self.setWindowTitle("통합 뉴스 도구v2.0.0 - 제작자: 최준혁, 곽은규")
        self.setGeometry(100, 100, 800, 600)

        # 메인 레이아웃
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

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
        self.status_label = QLabel("✅ 모든 기능이 준비되었습니다.")
        self.status_label.setAlignment(Qt.AlignCenter)
        bottom_layout.addWidget(self.status_label)
        
        # 제작자 정보 (오른쪽 정렬)
        creator_label = QLabel("© 2025 FromAI 최준혁")
        creator_label.setAlignment(Qt.AlignRight)
        creator_label.setStyleSheet("color: gray; font-size: 9px;")
        bottom_layout.addWidget(creator_label)
        
        layout.addLayout(bottom_layout)
        
        # 메뉴바 설정
        self.init_menubar()

    def init_menubar(self):
        """메뉴바 초기화"""
        menubar = self.menuBar()
        
        # 설정 메뉴
        settings_menu = menubar.addMenu('설정')
        
        # API 키 설정 액션
        api_action = QAction('API 키 설정', self)
        api_action.triggered.connect(self.show_api_settings)
        settings_menu.addAction(api_action)

    def show_api_settings(self):
        """API 키 설정 다이얼로그 표시"""
        dialog = QDialog(self)
        dialog.setWindowTitle('API 키 설정')
        dialog.setFixedSize(400, 150)
        
        layout = QVBoxLayout()
        
        # API 키 입력 필드
        label = QLabel('Google API 키:')
        self.api_input = QLineEdit()
        
        # 현재 API 키가 있으면 표시
        current_key = os.getenv('GOOGLE_API_KEY', '')
        if current_key and current_key != 'your_api_key_here':
            self.api_input.setText(current_key)
        
        # 버튼 레이아웃
        button_layout = QHBoxLayout()
        save_btn = QPushButton('저장')
        cancel_btn = QPushButton('취소')
        
        save_btn.clicked.connect(lambda: self.save_api_key(self.api_input.text(), dialog))
        cancel_btn.clicked.connect(dialog.reject)
        
        button_layout.addStretch()
        button_layout.addWidget(save_btn)
        button_layout.addWidget(cancel_btn)
        
        # 레이아웃에 위젯 추가
        layout.addWidget(label)
        layout.addWidget(self.api_input)
        layout.addLayout(button_layout)
        
        dialog.setLayout(layout)
        dialog.exec_()
    
    def save_api_key(self, api_key, dialog):
        """API 키 저장"""
        api_key = api_key.strip()
        if not api_key:
            QMessageBox.warning(self, '오류', 'API 키를 입력해주세요.')
            return
            
        if update_api_key(api_key):
            QMessageBox.information(self, '성공', 'API 키가 성공적으로 업데이트되었습니다.')
            dialog.accept()
        else:
            QMessageBox.critical(self, '오류', 'API 키 업데이트에 실패했습니다.')

    def open_settings_dialog(self):
        """설정 다이얼로그를 엽니다."""
        dialog = SettingsDialog(self)
        dialog.exec_()

def main():
    # PyInstaller로 빌드된 exe의 경우 환경 초기화
    env_path = initialize_environment()
    print(f"환경 설정 파일 경로: {env_path}")
    
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setFont(QFont("Arial", 9))

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
