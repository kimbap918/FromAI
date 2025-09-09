# article_generator_app.py - 메인 앱
# ===================================================================================
# 파일명     : article_generator_app.py
# 작성자     : 하승주, 홍석원
# 최초작성일 : 2025-09-04
# 설명       : 전체 프로그램의 실행 진입점으로, PyQt 기반 UI를 초기화하며
#              여행 탭(travel_tab)과 날씨 탭(weather_tab)을 포함한 통합 앱 구성
# ===================================================================================
#
# 【주요 기능】
# - PyQt5 기반 GUI 애플리케이션의 메인 엔트리포인트
# - 여행지 검색 탭과 날씨 조회 탭을 통합한 탭 구조 제공
# - SQLite DB 연결 및 초기화 담당
# - AI 챗봇, 날씨 API, 카테고리 매핑 등 핵심 컴포넌트 초기화
#
# 【작동 방식】
# 1. 애플리케이션 시작 시 DB 파일 존재 여부 확인
# 2. 필요한 API 인스턴스들(WeatherAPI, TravelChatbot) 생성
# 3. 카테고리 매핑 데이터를 DB에서 로드
# 4. 탭 위젯 생성 및 각 탭에 필요한 의존성 주입
# 5. UI 표시 후 이벤트 루프 시작
#
# 【의존성】
# - travel_tab.py: 여행지 검색 및 기사 생성 탭
# - weather_tab.py: 날씨 조회 및 기상특보 탭  
# - db_manager.py: SQLite DB 연결/조회
# - chatbot_app.py: AI 기사 생성
# - weather_api.py: 날씨 데이터 수집
#
# 【참고사항】
# - PyInstaller로 실행파일 빌드 시 리소스 경로 처리 포함
# - DB 파일이 없으면 오류 메시지 표시 후 종료
# ===================================================================================

import sys
import os
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QTabWidget, QMessageBox
from PyQt5.QtCore import Qt
from datetime import datetime

# 분리된 모듈들 import
from ui_components import IntItem
from weather_tab import WeatherTabWidget, WEATHER_AVAILABLE
from travel_tab import TravelTabWidget

# 기존 모듈들 (그대로 유지)
from category_utils import normalize_category_for_ui
from visitor_reviews_utils import normalize_review_for_ui
from weather_api import WeatherAPI
import db_manager
import chatbot_app
import shutil
import tempfile



def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

def extract_to_temp(rel_path, filename):
    src = resource_path(rel_path)
    temp_dir = tempfile.gettempdir()
    dst = os.path.join(temp_dir, filename)
    if not os.path.exists(dst):
        shutil.copy2(src, dst)
    return dst

class ArticleGeneratorApp(QWidget):
    """메인 애플리케이션 클래스 - 기존 기능 그대로 유지"""
    
    def __init__(self):
        super().__init__()
        
        # 기존 초기화 코드 그대로 유지
        self.chatbot = chatbot_app.TravelChatbot()
        if getattr(sys, 'frozen', False):
            base_path = os.path.dirname(sys.executable)
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))

        self.db_path = os.path.join(base_path, "crw_data", "naver_travel_places.db")
        if not os.path.exists(self.db_path):
            QMessageBox.critical(self, "DB 오류",
                f"DB 파일을 찾을 수 없습니다:\n{self.db_path}\n\nDB를 같은 폴더에 넣어주세요.")
            raise FileNotFoundError(self.db_path)

        self.category_mapping = db_manager.get_category_mapping(self.db_path)
        self.dong_mapping = {}  # 동 매핑 초기화
        self.weather_api = WeatherAPI()  # WeatherAPI 인스턴스 생성
        
        self.initUI()

    def initUI(self):
        """UI 초기화 - 탭 구조는 그대로 유지"""
        self.setWindowTitle('여행&날씨 기사 생성기 개발자 : 하승주, 홍석원')
        self.setGeometry(100, 100, 1400, 800)

        main_layout = QVBoxLayout()
        tabs = QTabWidget()

        # 여행지 검색 탭 (분리된 모듈 사용)
        travel_tab = TravelTabWidget(self)
        tabs.addTab(travel_tab, "🛏️ 여행지 검색")

        # 날씨 조회 탭 (분리된 모듈 사용)
        if WEATHER_AVAILABLE:
            weather_tab = WeatherTabWidget(self)
            tabs.addTab(weather_tab, "🌤️ 상세 날씨 조회")

        main_layout.addWidget(tabs)
        self.setLayout(main_layout)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8') # Add this line
    app = QApplication(sys.argv)
    ex = ArticleGeneratorApp()
    ex.show()
    sys.exit(app.exec_())
