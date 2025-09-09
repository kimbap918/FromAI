# weather_tab.py - 날씨 조회 및 기상특보 탭
# ===================================================================================
# 파일명     : weather_tab.py
# 작성자     : 하승주, 홍석원
# 최초작성일 : 2025-09-04
# 설명       : 날씨 정보 조회 및 표시, 전국 기상특보 모니터링 및
#              AI 기반 날씨/특보 기사 생성 기능을 제공하는 탭 형태 UI
# ===================================================================================
#
# 【주요 기능】
# - 날씨 정보 조회 및 표시
# - 전국 기상특보 모니터링
# - AI 기반 날씨/특보 기사 생성
# - 탭 형태의 직관적 UI 제공
#
# 【탭 구성】
# 1. 날씨 정보 탭
#    - 지역 검색: 자유 입력 + 빠른 선택 버튼
#    - 실시간 조회: 기온, 습도, 바람, 강수 정보
#    - 상세 표시: 현재/최저/최고 기온, 오늘/내일 예보
#
# 2. 기상특보 탭
#    - 전국 단위 특보 조회 (지역 선택 불필요)
#    - 활성 특보 목록 및 발효 시각 표시
#    - 특보 종류별 분류 및 지역별 현황
#
# 3. AI 기사 생성 영역
#    - 날씨 기사 생성: 조회된 날씨 정보 기반
#    - 특보 기사 생성: 발효 중인 특보 순환 선택
#    - 기사 복사 기능
#
# 【비동기 처리】
# - WeatherThread: 날씨 조회 백그라운드 처리
# - WeatherWarningThread: 기상특보 조회 스레드
# - ArticleGenerationThread: AI 기사 생성 스레드
#
# 【사용자 편의성】
# - 빠른 검색: 주요 8개 도시 원클릭 검색
# - 자동 지역명 확장: "광주" → "광주광역시"
# - 진행 상황 표시: 각 작업 단계별 상태 메시지
# - 오류 처리: 친화적 오류 메시지 및 대안 제시
#
# 【데이터 연동】
# - weather_api.py: 실제 날씨 데이터 수집
# - weather_warning.py: 기상특보 데이터 수집  
# - weather_ai_generator.py: AI 기사 생성
#
# 【상태 관리】
# - 버튼 활성화/비활성화: 데이터 준비 상태에 따라
# - 마지막 데이터 캐싱: 중복 조회 방지
# - AI 생성기 상태 초기화: 특보 변경 시
#
# 【출력 형식】
# - 기사 표시: 제목1~3 + 본문 + 해시태그 순서
# - 클립보드 복사: 완성된 기사 전체 복사 가능
#
# 【사용처】
# - article_generator_app.py: 메인 앱의 날씨 탭
# - 독립 실행 가능: 테스트 및 디버깅용
# ===================================================================================

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, 
                             QLineEdit, QPushButton, QLabel, QScrollArea, QApplication, QMessageBox,
                             QTabWidget, QComboBox, QTextEdit)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from datetime import datetime

# 기존 모듈 import
try:
    from weather_api import WeatherAPI
    WEATHER_AVAILABLE = True
    print("날씨 API 활성화")
except ImportError as e:
    WEATHER_AVAILABLE = False
    print(f"⚠️ 날씨 API 비활성화: {e}")

# 기상특보 API import
try:
    from weather_warning import WeatherWarningAPI
    WARNING_AVAILABLE = True
    print("기상특보 API 활성화")
except ImportError as e:
    WARNING_AVAILABLE = False
    print(f"⚠️ 기상특보 API 비활성화: {e}")

# AI 기사 생성기 import
try:
    from weather_ai_generator import WeatherArticleGenerator
    AI_AVAILABLE = True
    print("AI 기사 생성기 활성화")
except ImportError as e:
    AI_AVAILABLE = False
    print(f"⚠️ AI 기사 생성기 비활성화: {e}")

PROV_CANON = {
    "서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시", "인천": "인천광역시",
    "광주": "광주광역시", "대전": "대전광역시", "울산": "울산광역시",
    "세종": "세종특별자치시", "제주": "제주특별자치도",
    "경기": "경기도", "강원": "강원특별자치도",
    "충북": "충청북도", "충남": "충청남도",
    "전북": "전라북도", "전남": "전라남도",
    "경북": "경상북도", "경남": "경상남도",
}

def _expand_to_canonical(q: str) -> str:
    """모호한 입력을 정식명으로 확장"""
    q = (q or "").strip()
    if not q:
        return q
    if q in PROV_CANON:
        return PROV_CANON[q]
    if q == "광주":
        return "광주광역시"
    if q.startswith("광주 ") and ("광역시" not in q and "경기" not in q):
        return "광주광역시 " + q.split(" ", 1)[1]
    return q

class WeatherThread(QThread):
    """날씨 검색 스레드"""
    weather_received = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, city_name, weather_api):
        super().__init__()
        self.city_name = city_name
        self.weather_api = weather_api
    
    def run(self):
        if not self.weather_api:
            self.error_occurred.emit("날씨 API가 설정되지 않았습니다.")
            return
        try:
            weather_data = self.weather_api.get_weather_data(self.city_name)
            self.weather_received.emit(weather_data)
        except Exception as e:
            self.error_occurred.emit(str(e))

class WeatherWarningThread(QThread):
    """기상특보 조회 스레드 - 전국 기준으로 고정"""
    warning_received = pyqtSignal(list)
    error_occurred = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        if WARNING_AVAILABLE:
            self.warning_api = WeatherWarningAPI()
    
    def run(self):
        if not WARNING_AVAILABLE:
            self.error_occurred.emit("기상특보 API가 설정되지 않았습니다.")
            return
        try:
            # 전국 기상특보 조회 (stn_ids=None). 파싱은 WeatherWarningAPI에서 자동으로 처리.
            warnings = self.warning_api.get_weather_warnings(None)
            self.warning_received.emit(warnings)
        except Exception as e:
            self.error_occurred.emit(str(e))

class ArticleGenerationThread(QThread):
    """AI 기사 생성 스레드"""
    article_generated = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, ai_generator, data, data_type, region_name):
        super().__init__()
        self.ai_generator = ai_generator # 외부에서 생성된 인스턴스 사용
        self.data = data
        self.data_type = data_type
        self.region_name = region_name
    
    def run(self):
        if not AI_AVAILABLE:
            self.error_occurred.emit("AI 기사 생성기가 설정되지 않았습니다.")
            return
        try:
            if self.data_type == 'weather':
                article = self.ai_generator.generate_weather_article(self.data, self.region_name)
            else:  # 'warning'
                article = self.ai_generator.generate_warning_article(self.data, self.region_name)
            
            if article:
                self.article_generated.emit(article)
            else:
                self.error_occurred.emit("기사 생성에 실패했습니다.")
        except Exception as e:
            self.error_occurred.emit(str(e))

class SimpleWeatherTabWidget(QWidget):
    """심플한 날씨 탭 위젯 - UI 간소화"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_app = parent
        self._last_weather = None
        self._last_warnings = []
        self._last_city = None

        if WEATHER_AVAILABLE:
            self.weather_api = WeatherAPI()
        else:
            self.weather_api = None

        if AI_AVAILABLE:
            self.ai_generator = WeatherArticleGenerator()
        
        self.setup_ui()
    
    def setup_ui(self):
        """UI 설정 - 간소화"""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # 탭 위젯
        tab_widget = QTabWidget()
        
        # 날씨 정보 탭
        weather_tab = self.create_weather_tab()
        tab_widget.addTab(weather_tab, "날씨 정보")
        
        # 기상특보 탭
        warning_tab = self.create_warning_tab()
        tab_widget.addTab(warning_tab, "기상특보")
        
        main_layout.addWidget(tab_widget)
        
        # 하단 AI 기사 생성 영역
        article_section = self.create_article_section()
        main_layout.addWidget(article_section)
    
    def create_weather_tab(self):
        """날씨 정보 탭"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(15)
        
        # 지역 검색 - GroupBox 제거
        search_layout = QHBoxLayout()
        self.weather_search_input = QLineEdit()
        self.weather_search_input.setPlaceholderText("지역명을 입력하세요 (예: 서울, 부산, 강남구)")
        self.weather_search_input.returnPressed.connect(self.search_weather)
        
        self.weather_search_btn = QPushButton("날씨 검색")
        self.weather_search_btn.clicked.connect(self.search_weather)
        self.weather_search_btn.setStyleSheet("QPushButton { background-color: #007bff; color: white; font-weight: bold; padding: 8px 16px; }")
        
        search_layout.addWidget(self.weather_search_input)
        search_layout.addWidget(self.weather_search_btn)
        layout.addLayout(search_layout)
        
        # 빠른 검색 버튼들
        quick_layout = QHBoxLayout()
        quick_cities = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "제주"]
        for city in quick_cities:
            btn = QPushButton(city)
            btn.clicked.connect(lambda checked, c=city: self.quick_weather_search(c))
            btn.setMaximumWidth(70)
            btn.setStyleSheet("QPushButton { background-color: #f8f9fa; border: 1px solid #dee2e6; padding: 5px; }")
            quick_layout.addWidget(btn)
        layout.addLayout(quick_layout)
        
        # 날씨 정보 표시 - GroupBox 제거
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        
        self.weather_info_label = QLabel("지역을 검색해서 날씨 정보를 확인하세요.")
        self.weather_info_label.setStyleSheet("""
            QLabel {
                font-size: 14px; padding: 20px; background-color: #f8f9fa;
                border: 1px solid #dee2e6; border-radius: 8px; line-height: 1.5;
            }
        """)
        self.weather_info_label.setWordWrap(True)
        scroll_area.setWidget(self.weather_info_label)
        layout.addWidget(scroll_area)
        
        return widget
    
    def create_warning_tab(self):
        """기상특보 탭 - 간소화"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(15)
        
        # 특보 조회 버튼만 - GroupBox와 드롭다운 제거
        button_layout = QHBoxLayout()
        
        self.warning_search_btn = QPushButton("전국 기상특보 조회")
        self.warning_search_btn.clicked.connect(self.search_warnings)
        self.warning_search_btn.setStyleSheet("QPushButton { background-color: #dc3545; color: white; font-weight: bold; padding: 10px 20px; }")
        
        button_layout.addWidget(self.warning_search_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        # 특보 정보 표시 - GroupBox 제거
        warning_scroll = QScrollArea()
        warning_scroll.setWidgetResizable(True)
        
        self.warning_info_label = QLabel("\'전국 기상특보 조회\' 버튼을 클릭하세요.")
        self.warning_info_label.setStyleSheet("""
            QLabel {
                font-size: 14px; padding: 20px; background-color: #fff3cd;
                border: 1px solid #ffeaa7; border-radius: 8px; line-height: 1.5;
            }
        """)
        self.warning_info_label.setWordWrap(True)
        warning_scroll.setWidget(self.warning_info_label)
        layout.addWidget(warning_scroll)
        
        # 상태 표시
        self.warning_status_label = QLabel("대기 중...")
        self.warning_status_label.setStyleSheet("color: #6c757d; font-style: italic; padding: 5px;")
        layout.addWidget(self.warning_status_label)
        
        return widget
    
    def create_article_section(self):
        """AI 기사 생성 섹션 - GroupBox 제거"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)
        
        # 제목
        title_label = QLabel("AI 기사 생성")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #495057; margin-bottom: 10px;")
        layout.addWidget(title_label)
        
        # 버튼들
        button_layout = QHBoxLayout()
        
        self.generate_weather_article_btn = QPushButton("날씨 기사 생성")
        self.generate_weather_article_btn.clicked.connect(self.generate_weather_article)
        self.generate_weather_article_btn.setEnabled(False)
        self.generate_weather_article_btn.setStyleSheet("QPushButton { background-color: #007bff; color: white; padding: 8px 16px; }")
        
        self.generate_warning_article_btn = QPushButton("특보 기사 생성")
        self.generate_warning_article_btn.clicked.connect(self.generate_warning_article)
        self.generate_warning_article_btn.setEnabled(False)
        self.generate_warning_article_btn.setStyleSheet("QPushButton { background-color: #dc3545; color: white; padding: 8px 16px; }")
        
        self.copy_article_btn = QPushButton("기사 복사")
        self.copy_article_btn.clicked.connect(self.copy_article)
        self.copy_article_btn.setEnabled(False)
        self.copy_article_btn.setStyleSheet("QPushButton { background-color: #28a745; color: white; padding: 8px 16px; }")
        
        button_layout.addWidget(self.generate_weather_article_btn)
        button_layout.addWidget(self.generate_warning_article_btn)
        button_layout.addWidget(self.copy_article_btn)
        button_layout.addStretch()
        
        layout.addLayout(button_layout)
        
        # 생성된 기사 표시
        article_label = QLabel("생성된 기사:")
        article_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(article_label)
        
        self.article_display = QTextEdit()
        self.article_display.setMaximumHeight(200)
        self.article_display.setPlaceholderText("위에서 날씨 정보나 기상특보를 조회한 후 'AI 기사 생성' 버튼을 클릭하세요.")
        self.article_display.setStyleSheet("""
            QTextEdit {
                background-color: #f8f9fa; border: 1px solid #dee2e6;
                border-radius: 5px; padding: 10px; font-size: 13px;
            }
        """)
        layout.addWidget(self.article_display)
        
        # 상태 표시
        self.article_status_label = QLabel("AI 기사 생성 대기 중...")
        self.article_status_label.setStyleSheet("color: #6c757d; font-style: italic; padding: 5px;")
        layout.addWidget(self.article_status_label)
        
        return widget
    
    # 날씨 관련 메서드들
    def search_weather(self):
        city = self.weather_search_input.text().strip()
        city = _expand_to_canonical(city)
        if not city:
            QMessageBox.information(self, "안내", "지역명을 입력해주세요.")
            return
        self._start_weather_thread(city)
        
    def quick_weather_search(self, city):
        city = _expand_to_canonical(city)
        self.weather_search_input.setText(city)
        self._start_weather_thread(city)

    def _start_weather_thread(self, city):
        self.weather_info_label.setText(f"'{city}' 날씨 조회 중...")
        self.generate_weather_article_btn.setEnabled(False)
        self._weather_thread = WeatherThread(city, self.weather_api)
        self._weather_thread.weather_received.connect(self._on_weather_ok)
        self._weather_thread.error_occurred.connect(self._on_weather_err)
        self._weather_thread.start()
        self._last_city = city

    def _on_weather_ok(self, data: dict):
        try:
            if self.weather_api:
                formatted = self.weather_api.format_weather_info(data, self._last_city)
                self.weather_info_label.setText(formatted)
            else:
                self.weather_info_label.setText(str(data))
        except Exception:
            self.weather_info_label.setText(str(data))

        self._last_weather = data
        self.generate_weather_article_btn.setEnabled(True)
        self.article_status_label.setText("날씨 정보 준비됨 - 기사 생성 가능")

    def _on_weather_err(self, msg: str):
        QMessageBox.warning(self, "날씨 오류", msg)
        self.weather_info_label.setText(f"오류: {msg}")

    # 기상특보 관련 메서드들 - 전국 기준으로 간소화
    def search_warnings(self):
        if not WARNING_AVAILABLE:
            QMessageBox.warning(self, "오류", "기상특보 API가 비활성화되어 있습니다.")
            return
        
        self.warning_status_label.setText("전국 기상특보 조회 중...")
        self.generate_warning_article_btn.setEnabled(False)
        
        self._warning_thread = WeatherWarningThread()
        self._warning_thread.warning_received.connect(self._on_warning_ok)
        self._warning_thread.error_occurred.connect(self._on_warning_err)
        self._warning_thread.start()
    
    def _on_warning_ok(self, warnings: list):
        self._last_warnings = warnings

        # AI 생성기 상태 초기화
        if hasattr(self, 'ai_generator'):
            self.ai_generator.reset_warning_state()
        
        if WARNING_AVAILABLE:
            warning_api = WeatherWarningAPI()
            formatted_text = warning_api.format_warning_info(warnings)
            self.warning_info_label.setText(formatted_text)
        else:
            self.warning_info_label.setText("API가 비활성화되어 있습니다.")
        
        if warnings:
            self.warning_status_label.setText(f"{len(warnings)}건의 기상특보 발견")
            self.generate_warning_article_btn.setEnabled(True)
            self.article_status_label.setText("기상특보 정보 준비됨 - 기사 생성 가능")
        else:
            self.warning_status_label.setText("현재 발효 중인 기상특보 없음")
            self.generate_warning_article_btn.setEnabled(False)
    
    def _on_warning_err(self, msg: str):
        QMessageBox.warning(self, "기상특보 오류", msg)
        self.warning_info_label.setText(f"오류: {msg}")
        self.warning_status_label.setText("조회 실패")
    
    # AI 기사 생성 관련 메서드들
    def generate_weather_article(self):
        """날씨 기사 생성"""
        if not self._last_weather or not AI_AVAILABLE:
            QMessageBox.information(self, "안내", "날씨 정보를 먼저 조회해주세요.")
            return
        
        self.article_status_label.setText("AI가 날씨 기사를 생성 중...")
        self.generate_weather_article_btn.setEnabled(False)
        
        self._article_thread = ArticleGenerationThread(
            self.ai_generator, self._last_weather, 'weather', self._last_city or "해당 지역"
        )
        self._article_thread.article_generated.connect(self._on_article_generated)
        self._article_thread.error_occurred.connect(self._on_article_error)
        self._article_thread.start()
    
    def generate_warning_article(self):
        """기상특보 기사 생성"""
        if not self._last_warnings or not AI_AVAILABLE or not hasattr(self, 'ai_generator'):
            QMessageBox.information(self, "안내", "기상특보 정보를 먼저 조회하거나 AI 생성기를 초기화해주세요.")
            return
        
        self.article_status_label.setText("AI가 기상특보 기사를 생성 중...")
        self.generate_warning_article_btn.setEnabled(False)
        
        self._article_thread = ArticleGenerationThread(
            self.ai_generator, self._last_warnings, 'warning', None
        )
        self._article_thread.article_generated.connect(self._on_article_generated)
        self._article_thread.error_occurred.connect(self._on_article_error)
        self._article_thread.start()
    
    def _on_article_generated(self, article: dict):
        """기사 생성 완료 — 제목1~3 + 본문 + 해시태그 출력"""
        titles = article.get("titles") or [article.get("title", "제목 없음")]
        lines = []
        for i, t in enumerate(titles[:3], start=1):
            lines.append(f"제목{i}: {t}")

        body = (article.get("content") or "").strip()
        if body:
            lines.append("")
            lines.append(body)

        tags = article.get("hashtags") or []
        if tags:
            lines.append("")
            lines.append(" ".join(tags))

        display_text = "\n".join(lines)
        self.article_display.setText(display_text)
        
        # 버튼 활성화
        self.copy_article_btn.setEnabled(True)
        self.generate_weather_article_btn.setEnabled(bool(self._last_weather))
        self.generate_warning_article_btn.setEnabled(bool(self._last_warnings))
        
        # 상태 업데이트
        type_text = "날씨" if article.get('type') == 'weather' else "기상특보"
        self.article_status_label.setText(f"{type_text} 기사 생성 완료!")
        QMessageBox.information(self, "기사 생성 완료", f"{type_text} 기사가 성공적으로 생성되었습니다!")
    
    def _on_article_error(self, error_msg: str):
        """기사 생성 오류"""
        QMessageBox.warning(self, "기사 생성 오류", f"기사 생성 중 오류가 발생했습니다:\n{error_msg}")
        
        # 버튼 상태 복원
        self.generate_weather_article_btn.setEnabled(bool(self._last_weather))
        self.generate_warning_article_btn.setEnabled(bool(self._last_warnings))
        
        self.article_status_label.setText("기사 생성 실패")
    
    def copy_article(self):
        """기사 복사"""
        text = self.article_display.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            QMessageBox.information(self, "복사 완료", "기사가 클립보드에 복사되었습니다.")
        else:
            QMessageBox.warning(self, "복사 실패", "복사할 기사가 없습니다.")

# 호환성을 위한 별칭
WeatherTabWidget = SimpleWeatherTabWidget

# 테스트 실행
if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication
    
    app = QApplication(sys.argv)
    
    widget = SimpleWeatherTabWidget()
    widget.show()
    
    sys.exit(app.exec_())
