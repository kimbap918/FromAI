# travel_tab.py - 여행지 검색 탭 UI 컨트롤러
# ===================================================================================
# 파일명     : travel_tab.py
# 작성자     : 하승주, 홍석원
# 최초작성일 : 2025-09-04
# 설명       : 여행지 검색 탭의 사용자 인터페이스 제어 및
#              travel_ui.py와 travel_logic.py를 연결하는 MVC 컨트롤러 역할
# ===================================================================================
#
# 【주요 기능】
# - 여행지 검색 탭의 사용자 인터페이스 제어
# - travel_ui.py와 travel_logic.py를 연결하는 MVC 컨트롤러 역할
# - 사용자 이벤트 처리 및 화면 상태 관리
#
# 【UI 구성】
# 1. 필터 영역: 도/시/동, 카테고리, 리뷰 선택
# 2. 지역 검색: 자동완성 지원 통합 검색
# 3. 장소 테이블: 체크박스, 정렬, 상세 정보 표시
# 4. 기사 생성: 제목 입력, 날씨 포함 옵션
#
# 【핵심 기능】
# - 계층적 필터: 도 선택 → 시 목록 업데이트 → 동 목록 업데이트
# - 지역 검색: "강원 > 강릉시 > 교동" 형태 자동완성
# - 테이블 관리: 체크박스 선택, 정렬, 선택 항목 상단 이동
# - 랜덤 선택: 지정된 개수만큼 무작위 장소 선택
#
# 【이벤트 처리】
# - 필터 변경 → 하위 옵션 자동 업데이트
# - 검색 실행 → travel_logic 호출 → 결과 테이블 표시
# - 기사 생성 → 진행 상황 표시 → 결과 출력
#
# 【상태 관리】
# - 체크박스 선택 상태 추적
# - 진행 상황 다이얼로그 관리
# - 버튼 활성화/비활성화 제어
#
# 【테이블 기능】
# - 정렬: 인기순(리뷰수), 이름순, 주소순
# - 필터: 상위 10/30/50% 리뷰 범위
# - 체크박스: 다중 선택 및 선택 항목 상단 이동
#
# 【기사 생성】
# - 실시간 크롤링으로 최신 정보 확보
# - 날씨 정보 선택적 포함
# - AI 기사 생성 후 결과 표시
#
# 【사용처】
# - article_generator_app.py: 메인 앱에서 탭으로 사용
# ===================================================================================

from PyQt5.QtWidgets import (QWidget, QMessageBox, QTableWidgetItem, QCheckBox,
                             QHBoxLayout, QTextEdit, QApplication)
from PyQt5.QtGui import QStandardItem
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QStandardItemModel

# 분리된 UI와 로직 모듈 import
from travel_ui import Ui_TravelTab
from travel_logic import TravelLogic

# 유틸리티 및 기존 의존성 import
from ui_components import IntItem

PROV_CANON = {
    "서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시", "인천": "인천광역시",
    "광주": "광주광역시", "대전": "대전광역시", "울산": "울산광역시",
    "세종": "세종특별자치시", "제주": "제주특별자치도",
    "경기": "경기도", "강원": "강원특별자치도",
    "충북": "충청북도", "충남": "충청남도",
    "전북": "전라북도", "전남": "전라남도",
    "경북": "경상북도", "경남": "경상남도",
}

def _expand_province_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        return name
    if any(s in name for s in ("광역시", "특별시", "특별자치시", "특별자치도", "도")):
        return name
    return PROV_CANON.get(name, name)

class TravelTabWidget(QWidget):
    """여행지 검색 탭 컨트롤러"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_app = parent
        
        # 로직 및 UI 클래스 인스턴스화
        self.logic = TravelLogic(
            db_path=parent.db_path,
            category_mapping=parent.category_mapping,
            chatbot=parent.chatbot,
            weather_api=parent.weather_api
        )
        self.ui = Ui_TravelTab()
        self.ui.setupUi(self)

        self._init_properties()
        self._load_initial_data()
        self._connect_signals()

    def _init_properties(self):
        """클래스 속성 초기화"""
        self.progress_dialog = None
        self._region_index = []
        self._region_model = QStandardItemModel(self)
        self._region_map = {}

    def _load_initial_data(self):
        """초기 데이터 로드 및 UI 설정"""
        # 필터 데이터 로드
        filter_data = self.logic.get_initial_filter_data()
        self.province_combo.add_checkable_items(filter_data["provinces"], checked=False)
        self.category_combo.add_checkable_items(filter_data["categories"], checked=False)
        default_categories = ["공연/엔터테인먼트", "쇼핑", "음식점", "자연/공원", "전시/문화", "종교/전통", "체험/액티비티", "카페/디저트"]
        self.category_combo.set_checked(default_categories)
        self.review_category_combo.add_checkable_items(filter_data["review_categories"], checked=True)
        self.sort_combo.addItems(filter_data["sort_options"])

        # 지역 자동완성 인덱스 빌드
        self._region_index, self._region_map = self.logic.build_region_index()
        self.region_completer.setModel(self._region_model)
        self.on_region_search_text_changed("") # 초기 목록 채우기

    def _connect_signals(self):
        """UI 위젯의 시그널과 슬롯(메서드)을 연결"""
        # 필터 변경
        self.province_combo.model().itemChanged.connect(self._rebuild_cities_from_provinces)
        self.city_combo.model().itemChanged.connect(self._rebuild_dongs)

        # 지역 검색
        self.region_search_input.textChanged.connect(self.on_region_search_text_changed)
        self.region_search_input.returnPressed.connect(self.on_region_apply_clicked)
        self.region_apply_btn.clicked.connect(self.on_region_apply_clicked)
        try:
            self.region_completer.activated[str].connect(self.on_region_completer_activated)
        except TypeError:
            self.region_completer.activated.connect(self.on_region_completer_activated)

        # 버튼 클릭
        self.search_button.clicked.connect(self.search_places)
        self.reset_button.clicked.connect(self.reset_filters)
        self.generate_button.clicked.connect(self.generate_article)
        self.random_button.clicked.connect(self.random_select_and_generate)

        # 로직 시그널
        self.logic.crawling_progress.connect(self._update_progress_text)
        self.logic.crawling_error.connect(self._on_crawling_error)
        self.logic.article_generated.connect(self._on_article_finished)
        self.logic.article_error.connect(self._on_article_error)

    # --- UI 업데이트 및 이벤트 핸들러 ---

    def _rebuild_cities_from_provinces(self):
        sel_provs = self.province_combo.checked_items()
        cities = self.logic.get_cities_for_provinces(sel_provs)
        self.city_combo.clear_items()
        self.city_combo.add_checkable_items(cities, checked=False)
        self.dong_combo.clear_items()

    def _rebuild_dongs(self):
        sel_provs = self.province_combo.checked_items()
        sel_cities = self.city_combo.checked_items()
        dongs = self.logic.get_dongs_for_cities(sel_provs, sel_cities)
        self.dong_combo.clear_items()
        self.dong_combo.add_checkable_items(dongs, checked=False)

    def on_region_search_text_changed(self, text: str):
        if getattr(self, "_region_settling", False): return
        text = (text or "").strip()
        self._region_model.clear()
        if not text:
            for label, _, _, _ in self._region_index[:300]:
                self._region_model.appendRow(QStandardItem(label))
            return
        nt = "".join(text.split()).lower()
        count = 0
        for label, _, _, _ in self._region_index:
            if nt in "".join(label.split()).lower():
                self._region_model.appendRow(QStandardItem(label))
                count += 1
                if count >= 300: break

    def _apply_region_text_and_update(self, text: str) -> bool:
        # ... (이하 기존 on_region_apply_clicked 로직과 유사하게 UI 직접 제어) ...
        # 이 부분은 UI 상태를 직접 제어해야 하므로 컨트롤러에 남아있는 것이 자연스러움
        info = self._region_map.get(text)
        if not info:
            # ... (기존의 info 찾는 로직) ...
            pass # 간단히 생략
        
        if not info: return False

        prov, city, dong = info
        self.province_combo.set_checked([prov])
        self._rebuild_cities_from_provinces()
        self.city_combo.set_checked([city])
        self._rebuild_dongs()
        if dong: self.dong_combo.set_checked([dong])

        try:
            self._region_settling = True
            display_text = f"{prov} > {city}"
            if dong: display_text += f" > {dong}"
            self.region_search_input.setText(display_text)
        finally:
            self._region_settling = False
        return True

    def on_region_apply_clicked(self):
        text = self.region_search_input.text()
        if not self._apply_region_text_and_update(text):
            QMessageBox.information(self, "알림", "지역을 인식하지 못했어요. 예: '강원 > 강릉시'")
            return
        self.search_places()

    def on_region_completer_activated(self, picked: str):
        if self._apply_region_text_and_update(picked):
            pass

    def search_places(self):
        self.search_button.setText("검색 중...")
        self.search_button.setEnabled(False)
        QApplication.processEvents()

        filters = {
            "provinces": self.province_combo.checked_items(),
            "cities": self.city_combo.checked_items(),
            "dongs": self.dong_combo.checked_items(),
            "categories": self.category_combo.checked_items(),
            "review_categories": self.review_category_combo.checked_items(),
            "review_range": self.review_range_combo.currentText()
        }
        places = self.logic.search_places(filters)

        if not places:
            QMessageBox.information(self, "검색 결과", "조건에 맞는 장소를 찾을 수 없습니다.")
            self.place_table_widget.setRowCount(0)
        else:
            if len(places) > 1000:
                QMessageBox.information(self, "결과 제한", f"검색 결과가 {len(places):,}개로 많아 상위 1,000개만 표시합니다.")
                places = places[:1000]
            self._populate_table(places)

        self.search_button.setText("필터 적용")
        self.search_button.setEnabled(True)

    def _populate_table(self, places):
        # If called from _move_checked_to_top, the list is already sorted.
        # We can detect this by checking for the temporary key.
        is_resorting = places and places[0].get('_is_checked') is not None

        if not is_resorting:
            sort_by = self.sort_combo.currentText()
            if sort_by == '인기 순':
                places.sort(key=lambda x: (x.get('total_visitor_reviews', 0) or 0) + (x.get('total_blog_reviews', 0) or 0), reverse=True)
            elif sort_by == '이름 순':
                places.sort(key=lambda x: x.get('name', ''))
            elif sort_by == '주소 순':
                def get_parts(addr):
                    parts = (addr or '').split()
                    return (parts[0] if len(parts)>0 else '',
                            parts[1] if len(parts)>1 else '',
                            ' '.join(parts[2:]) if len(parts)>2 else '')
                places.sort(key=lambda x: get_parts(x.get('address','')))

        self.place_table_widget.setSortingEnabled(False)
        self.place_table_widget.setRowCount(len(places))
        for i, place in enumerate(places):
            checkbox_widget = QWidget()
            layout = QHBoxLayout(checkbox_widget)
            cb = QCheckBox()
            if place.get('_is_checked', False):
                cb.setChecked(True)
            cb.stateChanged.connect(self._update_selected_count)
            layout.addWidget(cb)
            layout.setAlignment(Qt.AlignCenter)
            layout.setContentsMargins(0,0,0,0)
            self.place_table_widget.setCellWidget(i, 0, checkbox_widget)

            self.place_table_widget.setItem(i, 1, QTableWidgetItem(place.get('name','')))
            self.place_table_widget.setItem(i, 2, QTableWidgetItem(place.get('category','')))
            self.place_table_widget.setItem(i, 3, QTableWidgetItem(place.get('address','')))
            self.place_table_widget.setItem(i, 4, QTableWidgetItem(place.get('keywords','N/A')))

            v = place.get('total_visitor_reviews', 0) or 0
            b = place.get('total_blog_reviews', 0) or 0
            try:
                total_reviews = int(v) + int(b)
            except Exception:
                total_reviews = 0

            item_total = IntItem(total_reviews)
            item_total.setText(f"{total_reviews:,}")
            item_total.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            item_total.setToolTip(f"이용자: {v:,} / 블로그: {b:,}")
            self.place_table_widget.setItem(i, 5, item_total)

            self.place_table_widget.setItem(i, 6, QTableWidgetItem(place.get('visitor_reviews', '')))
            intro = QTextEdit(); intro.setReadOnly(True); intro.setText(place.get('intro', ''))
            self.place_table_widget.setCellWidget(i, 7, intro)

            self.place_table_widget.setItem(i, 8, QTableWidgetItem("0"))
            
            self.place_table_widget.setItem(i, 9, QTableWidgetItem(str(place.get('naver_place_id', ''))))

        if is_resorting:
            self.place_table_widget.setSortingEnabled(False)
        else:
            self.place_table_widget.setSortingEnabled(True)
            current_sort = self.sort_combo.currentText()
            if current_sort == '인기 순':
                self.place_table_widget.sortByColumn(5, Qt.DescendingOrder)
            elif current_sort == '이름 순':
                self.place_table_widget.sortByColumn(1, Qt.AscendingOrder)
            elif current_sort == '주소 순':
                self.place_table_widget.sortByColumn(3, Qt.AscendingOrder)

        self._update_selected_count()

    def reset_filters(self):
        # ... (UI 초기화 로직) ...
        self.province_combo.uncheck_all()
        self.city_combo.uncheck_all()
        self.dong_combo.uncheck_all()
        self.category_combo.check_all()
        self.review_category_combo.check_all()
        self.review_range_combo.setCurrentText("상위 50%")
        self.sort_combo.setCurrentIndex(0)
        self.place_table_widget.setRowCount(0)

    def generate_article(self):
        self._move_checked_to_top()
        selected_places = self._get_selected_places_from_table()
        if not selected_places:
            QMessageBox.warning(self, "선택 오류", "기사를 생성할 장소를 하나 이상 선택해주세요.")
            return

        self.progress_dialog = QMessageBox(self)
        self.progress_dialog.setWindowTitle("정보 업데이트 중")
        self.progress_dialog.setText("최신 정보 확인 중...")
        self.progress_dialog.setStandardButtons(QMessageBox.Close)
        self.progress_dialog.show()

        title = self.article_title_input.text().strip()
        weather_loc = self._pick_weather_query_location()
        if not title:
            title = weather_loc or "추천 여행지"
        self.logic.start_article_generation(selected_places, title, self.include_weather_checkbox.isChecked(), weather_loc)

    def random_select_and_generate(self):
        import random

        total_rows = self.place_table_widget.rowCount()
        if total_rows == 0:
            QMessageBox.information(self, "알림", "먼저 장소를 검색해주세요.")
            return

        # 모든 체크박스 해제
        for i in range(total_rows):
            cb = self.place_table_widget.cellWidget(i, 0).findChild(QCheckBox)
            if cb:
                cb.setChecked(False)

        # 현재 테이블의 모든 장소 데이터 수집
        all_places = []
        for i in range(total_rows):
            review_item = self.place_table_widget.item(i, 5)
            if isinstance(review_item, IntItem):
                total_reviews = review_item.data(Qt.UserRole) or 0
            else:
                total_reviews = 0
            
            place_data = {
                'index': i,
                'total_reviews': total_reviews
            }
            all_places.append(place_data)

        # 리뷰 수 기준으로 정렬 (내림차순)
        all_places.sort(key=lambda x: x['total_reviews'], reverse=True)
        
        # 상위 10% 계산
        top_10_percent_count = max(1, int(len(all_places) * 0.1))
        top_10_percent_places = all_places[:top_10_percent_count]
        
        # 상위 10%에서 선택할 장소가 너무 적으면 (3개 미만) 상위 30%로 확장
        if len(top_10_percent_places) < 3:
            top_30_percent_count = max(3, int(len(all_places) * 0.3))
            candidate_places = all_places[:top_30_percent_count]
            selection_range = "상위 30%"
        else:
            candidate_places = top_10_percent_places
            selection_range = "상위 10%"
        
        # 3-5개 중 랜덤 선택
        num_to_select = random.choice([3, 4, 5])
        num_to_select = min(num_to_select, len(candidate_places))
        
        # 후보 장소들 중에서 랜덤 선택
        selected_places = random.sample(candidate_places, num_to_select)
        
        # 선택된 장소들의 체크박스 체크
        for place in selected_places:
            cb = self.place_table_widget.cellWidget(place['index'], 0).findChild(QCheckBox)
            if cb:
                cb.setChecked(True)
        
        print(f"랜덤 선택: 리뷰 수 {selection_range}에서 {num_to_select}개 장소 선택")
        
        # 기사 생성 프로세스 시작
        self.generate_article()

    def _get_selected_places_from_table(self):
        selected_places = []
        for i in range(self.place_table_widget.rowCount()):
            cb = self.place_table_widget.cellWidget(i, 0).findChild(QCheckBox)
            if cb and cb.isChecked():
                name_item = self.place_table_widget.item(i, 1)
                cat_item = self.place_table_widget.item(i, 2)
                addr_item = self.place_table_widget.item(i, 3)
                keyw_item = self.place_table_widget.item(i, 4)
                vr_item = self.place_table_widget.item(i, 6)
                intro_w = self.place_table_widget.cellWidget(i, 7)
                id_item = self.place_table_widget.item(i, 9)

                place_data = {
                    'name': name_item.text() if name_item else '',
                    'category': cat_item.text() if cat_item else '',
                    'address': addr_item.text() if addr_item else '',
                    'keywords': keyw_item.text() if keyw_item else 'N/A',
                    'visitor_reviews': vr_item.text() if vr_item else '',
                    'intro': intro_w.toPlainText() if intro_w else '',
                    'naver_place_id': id_item.text() if id_item else None
                }
                selected_places.append(place_data)
        return selected_places

    def _update_selected_count(self):
        count = 0
        for i in range(self.place_table_widget.rowCount()):
            cb = self.place_table_widget.cellWidget(i, 0).findChild(QCheckBox)
            if cb and cb.isChecked():
                count += 1
        self.selected_count_label.setText(f"선택: {count}")

    def _update_progress_text(self, text):
        if self.progress_dialog:
            self.progress_dialog.setInformativeText(text)

    def _on_crawling_error(self, error_message):
        if self.progress_dialog: self.progress_dialog.close()
        QMessageBox.critical(self, "크롤링 오류", error_message)

    def _on_article_finished(self, article):
        if self.progress_dialog: self.progress_dialog.close()
        self.result_text_edit.setText("AI가 기사를 생성하고 있습니다...")
        self.result_text_edit.setText(article)

    def _on_article_error(self, error_message):
        if self.progress_dialog: self.progress_dialog.close()
        self.result_text_edit.setText(f"기사 생성 오류: {error_message}")

    def _pick_weather_query_location(self) -> str:
        dongs  = self.dong_combo.checked_items()
        cities = self.city_combo.checked_items()
        sel_provs = self.province_combo.checked_items() # Assuming this is the correct way to get selected provinces

        def _find_prov_for_city(city):
            for p in sel_provs:
                try:
                    if city in self.logic.get_cities_for_provinces([p]): # Pass as list for logic method
                        return p
                except Exception:
                    pass
            for p in self.logic.get_initial_filter_data()["provinces"]:
                try:
                    if city in self.logic.get_cities_for_provinces([p]):
                        return p
                except Exception:
                    pass
            return None

        parts = []
        if len(dongs) == 1:
            if len(cities) == 1:
                prov = _find_prov_for_city(cities[0]) or (sel_provs[0] if sel_provs else "")
                if prov: parts.append(_expand_province_name(prov))
                parts.append(cities[0])
            else:
                if sel_provs:
                    parts.append(_expand_province_name(sel_provs[0]))
            parts.append(dongs[0])
        elif len(cities) == 1:
            prov = _find_prov_for_city(cities[0]) or (sel_provs[0] if sel_provs else "")
            if prov: parts.append(_expand_province_name(prov))
            parts.append(cities[0])
        elif sel_provs:
            parts.append(_expand_province_name(sel_provs[0]))

        q = " ".join(p for p in parts if p).strip()

        if q == "광주":
            q = "광주광역시"

        return q

    def _move_checked_to_top(self):
        checked_rows_data = []
        unchecked_rows_data = []

        for i in range(self.place_table_widget.rowCount()):
            cb = self.place_table_widget.cellWidget(i, 0).findChild(QCheckBox)
            is_checked = cb and cb.isChecked()
            
            row_data = {
                '_is_checked': is_checked, # 임시 정렬 키
                'name': self.place_table_widget.item(i, 1).text() if self.place_table_widget.item(i, 1) else '',
                'category': self.place_table_widget.item(i, 2).text() if self.place_table_widget.item(i, 2) else '',
                'address': self.place_table_widget.item(i, 3).text() if self.place_table_widget.item(i, 3) else '',
                'keywords': self.place_table_widget.item(i, 4).text() if self.place_table_widget.item(i, 4) else 'N/A',
                'total_visitor_reviews': self.place_table_widget.item(i, 5).data(Qt.UserRole) if self.place_table_widget.item(i, 5) else 0,
                'visitor_reviews': self.place_table_widget.item(i, 6).text() if self.place_table_widget.item(i, 6) else '',
                'intro': self.place_table_widget.cellWidget(i, 7).toPlainText() if self.place_table_widget.cellWidget(i, 7) else '',
                'naver_place_id': self.place_table_widget.item(i, 9).text() if self.place_table_widget.item(i, 9) else ''
            }
            # IntItem에서 리뷰 수를 가져오기 위한 추가 처리
            review_item = self.place_table_widget.item(i, 5)
            if isinstance(review_item, IntItem):
                row_data['total_visitor_reviews'] = review_item.data(Qt.UserRole)
                # 툴팁에서 블로그 리뷰 수 파싱 (선택적)
                tooltip = review_item.toolTip()
                try:
                    v_str, b_str = tooltip.split('/')
                    row_data['total_blog_reviews'] = int(''.join(filter(str.isdigit, b_str)))
                except:
                    row_data['total_blog_reviews'] = 0
            else: # Fallback
                row_data['total_visitor_reviews'] = 0
                row_data['total_blog_reviews'] = 0


            if is_checked:
                checked_rows_data.append(row_data)
            else:
                unchecked_rows_data.append(row_data)

        # 정렬된 순서대로 다시 채우기
        sorted_places = checked_rows_data + unchecked_rows_data
        self._populate_table(sorted_places)

# 기존의 QWidget을 상속받는 클래스 이름은 그대로 유지하여
# article_generator_app.py에서 수정 없이 바로 사용 가능하도록 함.

# Force recompile