#기사생성, 메인 
import sys
import os
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QComboBox, QPushButton, QTableWidget, QTableWidgetItem, 
                             QCheckBox, QTextEdit, QLabel, QMessageBox, QLineEdit, QFrame, QHeaderView, QAbstractItemView, QTabWidget, 
                             QGroupBox, QScrollArea, QDialog, QProgressDialog)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont
from datetime import datetime

from category_utils import normalize_category_for_ui
from visitor_reviews_utils import normalize_review_for_ui
from weather_api import WeatherAPI # WeatherAPI 임포트

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

# 날씨 API 관련 import
try:
    from weather_api import WeatherAPI
    WEATHER_AVAILABLE = True
    print("✅ 날씨 기능 활성화")
except ImportError as e:
    WEATHER_AVAILABLE = False
    print(f"⚠️ 날씨 기능 비활성화: {e}")

class WeatherThread(QThread):
    """날씨 검색을 위한 백그라운드 스레드"""
    weather_received = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, city_name):
        super().__init__()
        self.city_name = city_name
        if WEATHER_AVAILABLE:
            self.weather_api = WeatherAPI()
    
    def run(self):
        if not WEATHER_AVAILABLE:
            self.error_occurred.emit("날씨 API가 설정되지 않았습니다.")
            return
            
        try:
            weather_data = self.weather_api.get_weather_data(self.city_name)
            self.weather_received.emit(weather_data)
        except Exception as e:
            self.error_occurred.emit(str(e))

class ArticleGeneratorApp(QWidget):
    def __init__(self):
        super().__init__()
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
        self.dong_mapping = {}  # 읍/면/동 매핑을 저장할 변수
        self.weather_api = WeatherAPI() # WeatherAPI 인스턴스 생성
        self.initUI()

    def initUI(self):
        self.setWindowTitle('여행&날씨 기사 생성기 개발자 : 하승주, 홍석원')
        self.setGeometry(100, 100, 1400, 800)

        # 메인 레이아웃
        main_layout = QVBoxLayout()

        # 탭 위젯 생성
        tabs = QTabWidget()

        # 기존 여행지 검색 탭
        travel_tab = self.setup_travel_tab()
        tabs.addTab(travel_tab, "🏛️ 여행지 검색")

        # 날씨 조회 탭 (날씨 API가 사용 가능할 때만)
        if WEATHER_AVAILABLE:
            weather_tab = self.setup_weather_tab()
            tabs.addTab(weather_tab, "🌤️ 상세 날씨 조회")

        main_layout.addWidget(tabs)
        self.setLayout(main_layout)

    def setup_travel_tab(self):
        """여행지 검색 탭 설정 (기존 기능)"""
        travel_widget = QWidget()
        main_layout = QVBoxLayout(travel_widget)

        filter_layout = QHBoxLayout()
        list_layout = QVBoxLayout()
        bottom_layout = QVBoxLayout()

        # --- 필터 레이아웃 ---
        self.province_combo = QComboBox()
        self.province_combo.setEditable(True)
        self.city_combo = QComboBox()
        self.city_combo.setEditable(True)
        self.dong_combo = QComboBox()  # 읍/면/동 콤보박스 추가
        self.dong_combo.setEditable(True)
        self.category_combo = QComboBox()
        self.review_category_combo = QComboBox() # 리뷰 카테고리 콤보박스 추가 (from current)
        self.sort_combo = QComboBox()
        self.search_button = QPushButton("필터 적용")

        filter_layout.addWidget(QLabel("도/특별시:"))
        filter_layout.addWidget(self.province_combo)
        filter_layout.addWidget(QLabel("시/군/구:"))
        filter_layout.addWidget(self.city_combo)
        filter_layout.addWidget(QLabel("읍/면/동:"))  # 읍/면/동 라벨 추가
        filter_layout.addWidget(self.dong_combo)
        filter_layout.addWidget(QLabel("카테고리:"))
        filter_layout.addWidget(self.category_combo)
        filter_layout.addWidget(QLabel("리뷰 카테고리:")) # 리뷰 카테고리 라벨 추가 (from current)
        filter_layout.addWidget(self.review_category_combo) # 리뷰 카테고리 콤보박스 추가 (from current)
        filter_layout.addWidget(QLabel("정렬:"))
        filter_layout.addWidget(self.sort_combo)
        filter_layout.addWidget(self.search_button)
        filter_layout.addStretch()

        self.load_filters()
        self.province_combo.lineEdit().textEdited.connect(self.update_province_suggestions)
        self.province_combo.currentTextChanged.connect(self.load_cities)
        self.city_combo.lineEdit().textEdited.connect(self.update_city_suggestions)
        self.city_combo.currentTextChanged.connect(self.load_dongs)  # 시/군/구 변경 시 읍/면/동 로드
        self.dong_combo.lineEdit().textEdited.connect(self.update_dong_suggestions)  # 읍/면/동 자동완성
        self.search_button.clicked.connect(self.search_places)

        # --- 장소 목록 레이아웃 ---
        self.place_table_widget = QTableWidget()
        self.place_table_widget.setColumnCount(7)  # 체크박스, 소개 포함
        self.place_table_widget.setHorizontalHeaderLabels(["", "장소명", "카테고리", "주소", "키워드", "리뷰 요약", "소개"])

        header = self.place_table_widget.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Interactive)
        header.setSectionResizeMode(3, QHeaderView.Interactive)
        header.setSectionResizeMode(4, QHeaderView.Interactive)
        header.setSectionResizeMode(5, QHeaderView.Interactive)
        header.setSectionResizeMode(6, QHeaderView.Stretch) # 소개 컬럼은 Stretch

        self.place_table_widget.setColumnWidth(1, 150)
        self.place_table_widget.setColumnWidth(2, 100)
        self.place_table_widget.setColumnWidth(3, 250)
        self.place_table_widget.setColumnWidth(4, 150)
        self.place_table_widget.setColumnWidth(5, 250)

        self.place_table_widget.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.place_table_widget.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.place_table_widget.setWordWrap(True)

        list_layout.addWidget(self.place_table_widget)

        # --- 하단 레이아웃 ---
        article_control_layout = QHBoxLayout()
        self.article_title_input = QLineEdit()
        self.article_title_input.setPlaceholderText("기사 제목을 입력하세요 (비워두면 자동 생성)")
        self.include_weather_checkbox = QCheckBox("날씨 정보 포함") # 날씨 정보 포함 체크박스 추가
        self.include_weather_checkbox.setChecked(False) # 기본값: 체크 해제
        self.generate_button = QPushButton("선택한 장소로 기사 생성")
        self.generate_button.clicked.connect(self.generate_article)

        article_control_layout.addWidget(QLabel("기사 제목:"))
        article_control_layout.addWidget(self.article_title_input)
        article_control_layout.addWidget(self.include_weather_checkbox) # 체크박스 레이아웃에 추가
        article_control_layout.addWidget(self.generate_button)
        article_control_layout.addStretch()

        self.result_text_edit = QTextEdit()
        self.result_text_edit.setReadOnly(True)

        bottom_layout.addLayout(article_control_layout)
        bottom_layout.addWidget(QLabel("--- 생성된 기사 ---"))
        bottom_layout.addWidget(self.result_text_edit)

        main_layout.addLayout(filter_layout)
        main_layout.addLayout(list_layout)
        main_layout.addLayout(bottom_layout)

        return travel_widget

    def setup_weather_tab(self):
        """향상된 날씨 조회 탭 설정"""
        weather_widget = QWidget()
        weather_layout = QVBoxLayout(weather_widget)

        # 상단 검색 영역
        search_group = QGroupBox("🔍 지역 검색")
        search_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                margin-top: 20px;  /* 제목과 테두리 간격 */
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                padding: 0 5px;
            }
        """)
        search_layout = QVBoxLayout(search_group)

        # 검색 입력
        search_input_layout = QHBoxLayout()
        self.weather_search_input = QLineEdit()
        self.weather_search_input.setPlaceholderText("지역명을 입력하세요 (예: 서울, 부산, 강남구, 제주도)")
        self.weather_search_input.returnPressed.connect(self.search_weather)

        self.weather_search_btn = QPushButton("상세 날씨 검색")
        self.weather_search_btn.clicked.connect(self.search_weather)
        self.weather_search_btn.setStyleSheet("QPushButton { background-color: #007bff; color: white; font-weight: bold; }")

        search_input_layout.addWidget(self.weather_search_input)
        search_input_layout.addWidget(self.weather_search_btn)
        search_layout.addLayout(search_input_layout)

        # 빠른 검색 버튼들
        quick_search_layout = QHBoxLayout()
        quick_cities = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "제주"]

        for city in quick_cities:
            btn = QPushButton(city)
            btn.clicked.connect(lambda checked, c=city: self.quick_weather_search(c))
            btn.setMaximumWidth(80)
            btn.setStyleSheet("QPushButton { background-color: #f8f9fa; border: 1px solid #dee2e6; }")
            quick_search_layout.addWidget(btn)

        search_layout.addLayout(quick_search_layout)
        weather_layout.addWidget(search_group)

        # 📊 향상된 날씨 정보 표시 영역
        info_group = QGroupBox("🌡️ 종합 날씨 정보")
        info_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                margin-top: 20px;  /* 제목과 테두리 간격 */
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                padding: 0 5px;
            }
        """)
        info_layout = QVBoxLayout(info_group)

        # 메인 날씨 정보 (스크롤 가능하게 개선)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMaximumHeight(300)

        self.weather_info_label = QLabel("""
🌤️ 상세 날씨 정보를 검색해보세요!

💡 이제 다음 정보들을 모두 제공합니다:
• 현재 기온 및 체감온도
• 오늘/내일 최저/최고 기온
• 강수 확률 및 강수량
• 바람 정보 (속도, 방향)
• 하늘 상태 및 날씨 설명
• 습도 및 기타 상세 정보

📍 위의 지역명을 입력하거나 빠른 검색 버튼을 클릭하세요.
        """)
        self.weather_info_label.setStyleSheet("""
            QLabel {
                font-size: 14px;
                padding: 20px;
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 8px;
                margin: 10px;
                line-height: 1.5;
            }
        """)
        self.weather_info_label.setWordWrap(True)
        scroll_area.setWidget(self.weather_info_label)
        info_layout.addWidget(scroll_area)

        # 상세 정보 영역 (3개 그룹으로 나누어 더 많은 정보 표시)
        details_layout = QHBoxLayout()

        # 온도 정보 그룹
        temp_group = QGroupBox("🌡️ 온도 정보")
        temp_layout = QVBoxLayout(temp_group)
        self.temp_label = QLabel("--°C")
        self.temp_label.setStyleSheet("font-size: 28px; font-weight: bold; color: #007bff; text-align: center;")
        self.temp_label.setAlignment(Qt.AlignCenter)
        self.feels_like_label = QLabel("체감: --°C")
        self.feels_like_label.setAlignment(Qt.AlignCenter)
        temp_layout.addWidget(self.temp_label)
        temp_layout.addWidget(self.feels_like_label)
        details_layout.addWidget(temp_group)

        # 강수 정보 그룹
        precip_group = QGroupBox("💧 강수 정보")
        precip_layout = QVBoxLayout(precip_group)
        self.humidity_label = QLabel("습도: --%")
        self.rain_prob_label = QLabel("강수확률: --%")
        self.precip_amount_label = QLabel("강수량: --mm")
        precip_layout.addWidget(self.humidity_label)
        precip_layout.addWidget(self.rain_prob_label)
        precip_layout.addWidget(self.precip_amount_label)
        details_layout.addWidget(precip_group)

        # 기타 정보 그룹
        other_group = QGroupBox("🌬️ 기타 정보")
        other_layout = QVBoxLayout(other_group)
        self.weather_desc_label = QLabel("날씨: --")
        self.wind_info_label = QLabel("바람: --")
        self.data_source_label = QLabel("데이터: --")
        other_layout.addWidget(self.weather_desc_label)
        other_layout.addWidget(self.wind_info_label)
        other_layout.addWidget(self.data_source_label)
        details_layout.addWidget(other_group)

        info_layout.addLayout(details_layout)
        weather_layout.addWidget(info_group)
        group_style = """
        QGroupBox { font-weight: bold; margin-top: 20px; }
        QGroupBox::title { subcontrol-origin: margin; padding: 0 5px; }
        """
        for g in (temp_group, precip_group, other_group):
            g.setStyleSheet(group_style)

        # 하단 버튼들
        button_layout = QHBoxLayout()

        self.refresh_weather_btn = QPushButton("🔄 새로고침")
        self.refresh_weather_btn.clicked.connect(self.refresh_weather)
        self.refresh_weather_btn.setEnabled(False)

        self.copy_weather_btn = QPushButton("📋 상세 정보 복사")
        self.copy_weather_btn.clicked.connect(self.copy_weather_info)
        self.copy_weather_btn.setEnabled(False)

        self.show_regions_btn = QPushButton("🗺️ 지원 지역 보기")
        self.show_regions_btn.clicked.connect(self.show_supported_regions)

        button_layout.addWidget(self.refresh_weather_btn)
        button_layout.addWidget(self.copy_weather_btn)
        button_layout.addWidget(self.show_regions_btn)
        button_layout.addStretch()

        weather_layout.addLayout(button_layout)

        # 여백 추가
        weather_layout.addStretch()

        return weather_widget

    def load_filters(self):
        provinces = db_manager.get_province_list(self.db_path)
        self.province_combo.addItems(["전체"] + provinces)

        categories = sorted(self.category_mapping.keys())
        self.category_combo.addItems(["전체"] + categories)

        review_categories = [
            "전체", "가격/가성비", "맛/음식", "분위기/경관", "시설/청결", "서비스/친절",
            "활동/경험", "접근성/편의성", "상품/제품", "대상", "아이 관련", "반려동물 관련", "기타"
        ]
        self.review_category_combo.addItems(review_categories)

        self.sort_combo.addItems(["주소 순", "인기 순", "이름 순"])
        self.sort_combo.setCurrentText("인기 순")

    def update_province_suggestions(self, text):
        self.province_combo.blockSignals(True)
        self.province_combo.clear()
        if text:
            suggestions = db_manager.search_provinces_by_partial_name(text, self.db_path)
            self.province_combo.addItems(suggestions)
        else:
            provinces = db_manager.get_province_list(self.db_path)
            self.province_combo.addItems(["전체"] + provinces)
        self.province_combo.setEditText(text)
        self.province_combo.showPopup()
        self.province_combo.blockSignals(False)

    def load_cities(self, province_text):
        self.city_combo.blockSignals(True)
        self.city_combo.clear()
        self.dong_combo.clear()  # 시/군/구 변경 시 읍/면/동도 초기화
        self.dong_combo.addItem("전체")
        
        if province_text and province_text != "전체":
            cities = db_manager.get_city_list(province_text, self.db_path)
            self.city_combo.addItems(["전체"] + cities)
        else:
            self.city_combo.addItem("전체")
        self.city_combo.blockSignals(False)

    def update_city_suggestions(self, text):
        current_province = self.province_combo.currentText()
        self.city_combo.blockSignals(True)
        self.city_combo.clear()
        if text and current_province and current_province != "전체":
            suggestions = db_manager.search_cities_by_partial_name(current_province, text, self.db_path)
            self.city_combo.addItems(suggestions)
        elif not text and current_province and current_province != "전체":
            cities = db_manager.get_city_list(current_province, self.db_path)
            self.city_combo.addItems(["전체"] + cities)
        else:
            self.city_combo.addItem("전체")
        self.city_combo.setEditText(text)
        self.city_combo.showPopup()
        self.city_combo.blockSignals(False)

    def load_dongs(self, city_text):
        """시/군/구 선택 시 해당 읍/면/동 목록을 로드"""
        self.dong_combo.blockSignals(True)
        self.dong_combo.clear()
        
        current_province = self.province_combo.currentText()
        
        if city_text and city_text != "전체" and current_province and current_province != "전체":
            # 읍/면/동 매핑 업데이트
            self.dong_mapping = db_manager.get_dong_mapping(current_province, city_text, self.db_path)
            dongs = db_manager.get_dong_list(current_province, city_text, self.db_path)
            self.dong_combo.addItems(["전체"] + dongs)
        else:
            self.dong_mapping = {}
            self.dong_combo.addItem("전체")
        self.dong_combo.blockSignals(False)

    def update_dong_suggestions(self, text):
        """읍/면/동 자동완성 기능"""
        current_province = self.province_combo.currentText()
        current_city = self.city_combo.currentText()
        
        self.dong_combo.blockSignals(True)
        self.dong_combo.clear()
        
        if text and current_province and current_province != "전체" and current_city and current_city != "전체":
            suggestions = db_manager.search_dongs_by_partial_name(current_province, current_city, text, self.db_path)
            self.dong_combo.addItems(suggestions)
        elif not text and current_province and current_province != "전체" and current_city and current_city != "전체":
            dongs = db_manager.get_dong_list(current_province, current_city, self.db_path)
            self.dong_combo.addItems(["전체"] + dongs)
        else:
            self.dong_combo.addItem("전체")
            
        self.dong_combo.setEditText(text)
        self.dong_combo.showPopup()
        self.dong_combo.blockSignals(False)

    def search_places(self):
        province = self.province_combo.currentText()
        city = self.city_combo.currentText()
        dong = self.dong_combo.currentText()  # 읍/면/동 추가
        selected_category = self.category_combo.currentText()
        selected_review_category = self.review_category_combo.currentText() # 선택된 리뷰 카테고리 가져오기
        sort_by = self.sort_combo.currentText()

        # 실제 카테고리 필터값 매핑 처리
        if selected_category != "전체":
            original_categories = self.category_mapping.get(selected_category, [])
        else:
            original_categories = []

        self.place_table_widget.setRowCount(0)

        # 필터링된 장소 검색 (읍/면/동 포함)
        places = db_manager.search_places_advanced_with_dong(
            self.db_path, province, city, dong, original_categories
        )

        # 리뷰 카테고리 필터링
        if selected_review_category != "전체":
            filtered_by_review_category = []
            for place in places:
                raw_reviews = place.get('visitor_reviews', '')
                if raw_reviews:
                    review_terms = [term.strip() for term in raw_reviews.split(',')]
                    categorized_reviews = [normalize_review_for_ui(term) for term in review_terms]
                    if selected_review_category in categorized_reviews:
                        filtered_by_review_category.append(place)
            places = filtered_by_review_category

        if not places:
            QMessageBox.information(self, "검색 결과", "조건에 맞는 장소를 찾을 수 없습니다.")
            return

        # 정렬 로직
        if sort_by == '리뷰 많은 순':
            places.sort(key=lambda x: x.get('total_visitor_reviews', 0) + x.get('total_blog_reviews', 0), reverse=True)
        elif sort_by == '이름 순':
            places.sort(key=lambda x: x.get('name', ''))
        elif sort_by == '주소 순':
            def get_address_parts(address):
                parts = address.split()
                province_part = parts[0] if len(parts) > 0 else ''
                city_part = parts[1] if len(parts) > 1 else ''
                detail_part = ' '.join(parts[2:]) if len(parts) > 2 else ''
                return (province_part, city_part, detail_part)
            places.sort(key=lambda x: get_address_parts(x.get('address', '')))

        self.place_table_widget.setRowCount(len(places))
        for i, place in enumerate(places):
            # 체크박스 셀
            checkbox_widget = QWidget()
            checkbox_layout = QHBoxLayout(checkbox_widget)
            checkbox = QCheckBox()
            checkbox_layout.addWidget(checkbox)
            checkbox_layout.setAlignment(Qt.AlignCenter)
            checkbox_layout.setContentsMargins(0,0,0,0)
            self.place_table_widget.setCellWidget(i, 0, checkbox_widget)

            # 데이터 셀
            self.place_table_widget.setItem(i, 1, QTableWidgetItem(place['name']))
            self.place_table_widget.setItem(i, 2, QTableWidgetItem(place['category']))
            self.place_table_widget.setItem(i, 3, QTableWidgetItem(place['address']))
            self.place_table_widget.setItem(i, 4, QTableWidgetItem(place.get('keywords', 'N/A')))
            self.place_table_widget.setItem(i, 5, QTableWidgetItem(place.get('visitor_reviews', '')))
            
            # 소개 셀 (스크롤 가능)
            intro_text = QTextEdit()
            intro_text.setReadOnly(True)
            intro_text.setText(place.get('intro', ''))
            self.place_table_widget.setCellWidget(i, 6, intro_text)

    def generate_article(self):
        selected_places = []
        for i in range(self.place_table_widget.rowCount()):
            if self.place_table_widget.cellWidget(i, 0).findChild(QCheckBox).isChecked():
                place_data = {
                    'name': self.place_table_widget.item(i, 1).text(),
                    'category': self.place_table_widget.item(i, 2).text(),
                    'address': self.place_table_widget.item(i, 3).text(),
                    'keywords': self.place_table_widget.item(i, 4).text(),
                    'visitor_reviews': self.place_table_widget.item(i, 5).text(),
                    'intro': self.place_table_widget.cellWidget(i, 6).toPlainText()
                }
                selected_places.append(place_data)

        if not selected_places:
            QMessageBox.warning(self, "선택 오류", "기사를 생성할 장소를 하나 이상 선택해주세요.")
            return

        title = self.article_title_input.text()
        
        if not title:
            selected_region_query = self.province_combo.currentText()
            if self.city_combo.currentText() != "전체":
                selected_region_query += " " + self.city_combo.currentText()
            if self.dong_combo.currentText() != "전체":
                selected_region_query += " " + self.dong_combo.currentText()
            
            search_query_for_ai = selected_region_query + " 가볼만한곳"
            title_for_display = search_query_for_ai # For the user input field
        else:
            search_query_for_ai = title # If user provides title, use it as search_query for AI
            title_for_display = title

        self.result_text_edit.setText("기사를 생성 중입니다. 잠시만 기다려주세요...")
        QApplication.processEvents()

        # --- 날씨 정보 가져오기 ---
        weather_info_text = "" # Initialize as empty string

        if self.include_weather_checkbox.isChecked(): # Only fetch if checkbox is checked
            weather_query_city = self.city_combo.currentText()
            if weather_query_city == "전체":
                weather_query_city = self.province_combo.currentText()
            elif self.dong_combo.currentText() != "전체":
                weather_query_city = self.dong_combo.currentText() # 읍/면/동이 선택되어 있으면 읍/면/동으로 날씨 검색

            try:
                weather_data = self.weather_api.get_weather_data(weather_query_city)
                weather_info_text = self.weather_api.format_weather_info(weather_data, weather_query_city)
            except Exception as e:
                weather_info_text = f"날씨 정보를 가져오는 데 실패했습니다: {e}"
                print(f"날씨 정보 오류: {e}") # For debugging

        try:
            import pandas as pd
            
            df = pd.DataFrame(selected_places)
            columns_to_send = ['name', 'category', 'address', 'keywords', 'visitor_reviews', 'intro']
            places_json = df[columns_to_send].to_json(orient='records', force_ascii=False)

            article = self.chatbot.recommend_travel_article(search_query_for_ai, [], places_json, weather_info_text)
            self.result_text_edit.setText(article)

        except Exception as e:
            self.result_text_edit.setText(f"기사 생성 중 오류가 발생했습니다: {e}")

    # === 향상된 날씨 관련 메서드들 ===

    def search_weather(self):
        city = self.weather_search_input.text().strip()
        if not city:
            QMessageBox.information(self, "안내", "지역명을 입력해줘.")
            return
        self._start_weather_thread(city)

    def quick_weather_search(self, city):
        self.weather_search_input.setText(city)
        self._start_weather_thread(city)

    def _start_weather_thread(self, city):
        self.weather_info_label.setText(f" '{city}' 날씨 조회 중…")
        self.refresh_weather_btn.setEnabled(False)
        self.copy_weather_btn.setEnabled(False)
        self._weather_thread = WeatherThread(city)
        self._weather_thread.weather_received.connect(self._on_weather_ok)
        self._weather_thread.error_occurred.connect(self._on_weather_err)
        self._weather_thread.start()
        self._last_city = city

    def _on_weather_ok(self, data: dict):
        # 키 이름은 weather_api 구현에 따라 다를 수 있으니 .get 사용
        temp = data.get("temp") or data.get("temperature")
        feels = data.get("feels_like") or data.get("apparent_temperature")
        hum  = data.get("humidity")
        pop  = data.get("precip_probability") or data.get("rain_prob")
        prcp = data.get("precip_amount") or data.get("precip")
        desc = data.get("description") or data.get("weather")
        wind = data.get("wind") or f"{data.get('wind_speed','-')} m/s"
        source = data.get("source") or "WeatherAPI"

        if temp is not None: self.temp_label.setText(f"{temp}°C")
        if feels is not None: self.feels_like_label.setText(f"체감: {feels}°C")
        if hum is not None: self.humidity_label.setText(f"습도: {hum}%")
        if pop is not None: self.rain_prob_label.setText(f"강수확률: {pop}%")
        if prcp is not None: self.precip_amount_label.setText(f"강수량: {prcp} mm")
        if desc is not None: self.weather_desc_label.setText(f"날씨: {desc}")
        if wind is not None: self.wind_info_label.setText(f"바람: {wind}")
        self.data_source_label.setText(f"데이터: {source}")

        # 상세 텍스트 (weather_api에 포매터가 있으면 그걸 사용)
        try:
            formatted = self.weather_api.format_weather_info(data, self._last_city)
            self.weather_info_label.setText(formatted)
        except Exception:
            self.weather_info_label.setText(str(data))

        self._last_weather = data
        self.refresh_weather_btn.setEnabled(True)
        self.copy_weather_btn.setEnabled(True)

    def _on_weather_err(self, msg: str):
        QMessageBox.warning(self, "날씨 오류", msg)
        self.weather_info_label.setText(f"⚠️ 오류: {msg}")

    def refresh_weather(self):
        if getattr(self, "_last_city", None):
            self._start_weather_thread(self._last_city)

    def copy_weather_info(self):
        text = self.weather_info_label.text()
        QApplication.clipboard().setText(text)
        QMessageBox.information(self, "복사됨", "상세 날씨 정보를 클립보드에 복사했어.")

    def show_supported_regions(self):
        # 필요하면 weather_api에서 제공하는 리스트를 가져오도록 확장
        QMessageBox.information(self, "지원 지역", "예: 서울, 부산, 대구, 인천, 광주, 대전, 울산, 제주 …")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = ArticleGeneratorApp()
    ex.show()
    sys.exit(app.exec_())