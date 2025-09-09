# travel_ui.py - 여행지 검색 탭 UI 컴포넌트 정의
# ===================================================================================
# 파일명     : travel_ui.py
# 작성자     : 하승주, 홍석원
# 최초작성일 : 2025-09-04
# 설명       : 여행지 검색 탭의 순수 UI 레이아웃 및 위젯 생성
#              기능적 로직 없이 시각적 구조만 담당하는 View 컴포넌트
# ===================================================================================
#
# 【주요 기능】
# - 여행지 검색 탭의 순수 UI 레이아웃 및 위젯 생성
# - 기능적 로직 없이 시각적 구조만 담당
# - travel_tab.py 컨트롤러에서 사용할 UI 컴포넌트 제공
#
# 【UI 구조】
# 1. 필터 레이아웃
#    - 지역 검색: 자동완성 입력창 + 검색 버튼
#    - 다단계 필터: 도/시/동 + 카테고리 + 리뷰 카테고리
#    - 정렬 및 범위 선택
#
# 2. 장소 목록 레이아웃
#    - 검색 결과 테이블 (체크박스, 장소 정보, 리뷰)
#    - 테이블 컬럼: 선택, 장소명, 카테고리, 주소, 키워드, 리뷰수, 리뷰요약, 소개
#
# 3. 기사 생성 레이아웃
#    - 제목 입력, 날씨 포함 옵션
#    - 랜덤 선택, 선택 장소 기사 생성 버튼
#    - 선택 개수 표시
#    - 생성된 기사 텍스트 표시 영역
#
# 【위젯 설정】
# - CheckableComboBox: 다중 선택 가능한 콤보박스
# - SelectAllCheckableComboBox: 전체 선택/해제 헤더 있는 콤보박스
# - QTableWidget: 장소 목록 표시용 테이블
# - QCompleter: 지역명 자동완성
# - QTextEdit: 기사 결과 표시
#
# 【스타일링】
# - 최소 폭 설정으로 UI 일관성 유지
# - 테이블 컬럼 크기 및 정렬 옵션 설정
# - 버튼 및 라벨 기본 스타일 적용
#
# 【의존성】
# - ui_components.py: 커스텀 UI 컴포넌트
# - travel_tab.py에서 setupUi() 메서드 호출하여 사용
#
# 【특징】
# - MVC 패턴의 View 역할
# - 로직과 완전 분리된 순수 UI
# - 재사용 가능한 컴포넌트 구조
# ===================================================================================

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QPushButton,
                             QLineEdit, QLabel, QCheckBox, QTextEdit, QCompleter,
                             QTableWidget)
from PyQt5.QtCore import Qt

from ui_components import CheckableComboBox, SelectAllCheckableComboBox, setup_place_table

class Ui_TravelTab:
    """
    여행지 탭의 UI를 설정하는 클래스.
    - 위젯 생성
    - 레이아웃 설정
    - UI 초기값 설정
    """
    def setupUi(self, TravelTabWidget):
        # --- 메인 레이아웃 ---
        main_layout = QVBoxLayout(TravelTabWidget)

        filter_layout = QVBoxLayout()
        list_layout = QVBoxLayout()
        bottom_layout = QVBoxLayout()

        # --- 필터 레이아웃 ---
        TravelTabWidget.province_combo = CheckableComboBox("도/특별시")
        TravelTabWidget.city_combo = CheckableComboBox("시/군/구")
        TravelTabWidget.dong_combo = SelectAllCheckableComboBox("읍/면/동")
        TravelTabWidget.category_combo = SelectAllCheckableComboBox("카테고리")
        TravelTabWidget.category_combo.setMinimumWidth(170)
        TravelTabWidget.review_category_combo = SelectAllCheckableComboBox("리뷰 카테고리")
        TravelTabWidget.review_category_combo.setMinimumWidth(140)
        TravelTabWidget.sort_combo = QComboBox()
        TravelTabWidget.search_button = QPushButton("필터 적용")
        TravelTabWidget.reset_button = QPushButton("초기화")

        TravelTabWidget.region_search_input = QLineEdit()
        TravelTabWidget.region_search_input.setPlaceholderText("지역 검색 ")
        TravelTabWidget.region_search_input.setFixedWidth(200)
        TravelTabWidget.region_completer = QCompleter()
        TravelTabWidget.region_completer.setCaseSensitivity(Qt.CaseInsensitive)
        TravelTabWidget.region_completer.setFilterMode(Qt.MatchContains)
        TravelTabWidget.region_search_input.setCompleter(TravelTabWidget.region_completer)
        TravelTabWidget.region_apply_btn = QPushButton("검색")

        # --- 지역 검색 줄 ---
        region_layout = QHBoxLayout()
        region_layout.addWidget(QLabel("지역 검색:"))
        region_layout.addWidget(TravelTabWidget.region_search_input)
        region_layout.addWidget(TravelTabWidget.region_apply_btn)
        region_layout.addStretch()

        # --- 나머지 필터 줄 ---
        filters_row_layout = QHBoxLayout()
        filters_row_layout.addWidget(QLabel("도/특별시:"))
        filters_row_layout.addWidget(TravelTabWidget.province_combo)
        TravelTabWidget.province_combo.setMinimumContentsLength(5)
        TravelTabWidget.province_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        filters_row_layout.addWidget(QLabel("시/군/구:"))
        filters_row_layout.addWidget(TravelTabWidget.city_combo)
        filters_row_layout.addWidget(QLabel("읍/면/동:"))
        filters_row_layout.addWidget(TravelTabWidget.dong_combo)
        filters_row_layout.addWidget(QLabel("카테고리:"))
        filters_row_layout.addWidget(TravelTabWidget.category_combo)
        filters_row_layout.addWidget(QLabel("리뷰 카테고리:"))
        filters_row_layout.addWidget(TravelTabWidget.review_category_combo)
        filters_row_layout.addWidget(QLabel("정렬:"))
        filters_row_layout.addWidget(TravelTabWidget.sort_combo)

        TravelTabWidget.review_range_combo = QComboBox()
        TravelTabWidget.review_range_combo.addItems(["상위 10%", "상위 30%", "상위 50%", "전체"])
        TravelTabWidget.review_range_combo.setCurrentText("상위 50%")
        TravelTabWidget.review_range_combo.setMinimumWidth(100)
        filters_row_layout.addWidget(QLabel("범위:"))
        filters_row_layout.addWidget(TravelTabWidget.review_range_combo)

        filters_row_layout.addWidget(TravelTabWidget.search_button)
        filters_row_layout.addWidget(TravelTabWidget.reset_button)
        filters_row_layout.addStretch()

        filter_layout.addLayout(region_layout)
        filter_layout.addLayout(filters_row_layout)

        # --- 장소 목록 ---
        TravelTabWidget.place_table_widget = QTableWidget()
        setup_place_table(TravelTabWidget.place_table_widget)
        list_layout.addWidget(TravelTabWidget.place_table_widget)

        # --- 하단 컨트롤 ---
        article_control_layout = QHBoxLayout()
        TravelTabWidget.article_title_input = QLineEdit()
        TravelTabWidget.article_title_input.setPlaceholderText("기사 제목을 입력하세요 (비워두면 자동 생성)")
        TravelTabWidget.include_weather_checkbox = QCheckBox("날씨 정보 포함")
        TravelTabWidget.include_weather_checkbox.setChecked(False)
        TravelTabWidget.random_button = QPushButton("랜덤 선택으로 기사 생성")
        TravelTabWidget.generate_button = QPushButton("선택한 장소로 기사 생성")
        TravelTabWidget.selected_count_label = QLabel("선택: 0")
        TravelTabWidget.selected_count_label.setStyleSheet("color:#555; padding:0 8px;")

        article_control_layout.addWidget(QLabel("기사 제목(키워드):"))
        article_control_layout.addWidget(TravelTabWidget.article_title_input)
        article_control_layout.addWidget(TravelTabWidget.include_weather_checkbox)
        article_control_layout.addWidget(TravelTabWidget.random_button)
        article_control_layout.addWidget(TravelTabWidget.generate_button)
        article_control_layout.addStretch()
        article_control_layout.addWidget(TravelTabWidget.selected_count_label)

        TravelTabWidget.result_text_edit = QTextEdit()
        TravelTabWidget.result_text_edit.setReadOnly(True)

        bottom_layout.addLayout(article_control_layout)
        bottom_layout.addWidget(QLabel("--- 생성된 기사 ---"))
        bottom_layout.addWidget(TravelTabWidget.result_text_edit)

        main_layout.addLayout(filter_layout)
        main_layout.addLayout(list_layout)
        main_layout.addLayout(bottom_layout)
