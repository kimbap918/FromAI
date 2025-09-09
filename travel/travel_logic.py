# travel_logic.py - 여행지 검색 탭의 비즈니스 로직 처리
# ===================================================================================
# 파일명     : travel_logic.py
# 작성자     : 하승주, 홍석원
# 최초작성일 : 2025-09-04
# 설명       : UI와 독립적인 여행지 검색, 필터링, 기사 생성 로직 및
#              백그라운드 스레드를 통한 비동기 작업 처리
# ===================================================================================
#
# 【주요 기능】
# - UI와 독립적인 여행지 검색, 필터링, 기사 생성 로직
# - 백그라운드 스레드를 통한 비동기 작업 처리
# - 복잡한 필터 조건의 파이썬 기반 후처리
#
# 【핵심 클래스】
# - TravelLogic: 메인 비즈니스 로직 클래스
# - CrawlerWorker: 실시간 크롤링 워커 스레드
# - ArticleWorker: AI 기사 생성 워커 스레드
#
# 【주요 기능】
# 1. 초기 데이터 로딩
#    - get_initial_filter_data(): 도/시/동, 카테고리 목록
#    - build_region_index(): 자동완성용 지역 인덱스
#
# 2. 장소 검색 및 필터링
#    - search_places(): 다단계 지역 + 카테고리 + 리뷰 필터
#    - _place_matches_filters(): 정규화 기반 정확한 매칭
#    - _apply_review_count_filter(): 리뷰 수 상위 N% 필터
#
# 3. 비동기 작업 처리
#    - start_article_generation(): 크롤링 → 기사 생성 파이프라인
#    - 진행 상황 시그널을 통한 UI 업데이트
#
# 【필터링 로직】
# - 카테고리: category_utils.py의 정규화 함수 활용
# - 리뷰: visitor_reviews_utils.py의 태그 변환 활용
# - 지역: DB 쿼리 + 파이썬 추가 필터링
# - 리뷰 수: 상위 10/30/50% 선택 가능
#
# 【워커 스레드】
# - CrawlerWorker: 선택된 장소들의 실시간 정보 업데이트
# - ArticleWorker: 날씨 정보 포함하여 AI 기사 생성
#
# 【사용처】
# - travel_tab.py: 컨트롤러에서 호출
# - 모든 무거운 작업을 백그라운드에서 처리
# ===================================================================================

import random
import re
import pandas as pd
from PyQt5.QtCore import QObject, pyqtSignal, QThread

import db_manager
import realtime_crawler
from category_utils import normalize_category_for_ui
from visitor_reviews_utils import normalize_review_for_ui


# ----------------------------
# 내부 유틸리티: 정규화 기반 필터 공용 함수
# ----------------------------

def _to_set(value):
    """정규화 함수 반환형이 str/list/set 등일 수 있어 항상 set로 변환."""
    if value is None:
        return set()
    if isinstance(value, (list, tuple, set)):
        return {str(v).strip() for v in value if str(v).strip()}
    s = str(value).strip()
    return {s} if s else set()


def _extract_place_categories(place: dict) -> set:
    """
    장소의 UI 카테고리 집합을 계산합니다.
    - name, category/categories, keywords 등을 합쳐 normalize_category_for_ui에 전달
    - normalize_category_for_ui 반환값을 set로 일관 변환
    """
    name = str(place.get("name", "")).strip()
    raw_cat = place.get("category") or place.get("categories") or ""
    keywords = place.get("keywords") or ""

    if isinstance(raw_cat, (list, tuple, set)):
        raw_cat_text = " / ".join(map(str, raw_cat))
    else:
        raw_cat_text = str(raw_cat)

    normalized = normalize_category_for_ui(f"{name} {raw_cat_text} {keywords}".strip())
    return _to_set(normalized)


def _extract_review_tags(place: dict) -> set:
    """
    장소의 리뷰 태그 집합을 계산합니다.
    - 가능한 여러 리뷰 필드 중 하나라도 존재하면 사용
    - 콤마로 구분된 문자열을 각 용어로 분리
    - 각 용어를 normalize_review_for_ui를 통해 태그로 변환
    - '정보 없음'은 필터 판단에서 제외
    """
    raw_text = (
        place.get("visitor_reviews")
        or place.get("review_summary")
        or place.get("reviews_summary")
        or place.get("reviews_raw")
        or place.get("reviews")
        or place.get("review")
        or ""
    )
    raw_text = str(raw_text or "").strip()

    if not raw_text:
        return set()

    # 콤마로 구분된 리뷰들을 개별 용어로 분리
    terms = [p.strip() for p in raw_text.split(",") if p.strip()]
    
    # 각 용어를 표준 UI 태그로 변환
    tags = {normalize_review_for_ui(term) for term in terms}
    
    # 유효하지 않은 태그(None, 빈 문자열, 정보 없음) 제거
    return {t for t in tags if t and t != "정보 없음"}


def _place_matches_filters(place: dict, selected_ui_cats: set, selected_review_tags: set) -> bool:
    """선택된 카테고리/리뷰 태그와의 교집합으로 통과 여부 결정."""
    # 카테고리 필터
    if selected_ui_cats:
        cats = _extract_place_categories(place)
        if not (cats & selected_ui_cats):
            return False

    # 리뷰 필터
    if selected_review_tags:
        rtags = _extract_review_tags(place)
        # 과거 버그: '정보 없음' 또는 빈 리뷰를 무조건 통과 -> 이제는 제외
        if not rtags:
            return False
        if not (rtags & selected_review_tags):
            return False

    return True


class CrawlerWorker(QObject):
    """
    백그라운드에서 크롤링 및 DB 업데이트를 수행하는 워커
    """
    finished = pyqtSignal(list)  # 작업 완료 시 업데이트된 장소 목록을 전달
    progress = pyqtSignal(str)   # 진행 상황 텍스트를 전달
    error = pyqtSignal(str)      # 오류 발생 시 메시지를 전달

    def __init__(self, db_path: str, places: list):
        super().__init__()
        self.db_path = db_path
        self.places = places
        self.is_running = True

    def run(self):
        """크롤링 및 DB 업데이트 실행"""
        db_conn = None
        try:
            db_conn = db_manager.create_connection(self.db_path)
            if not db_conn:
                self.error.emit("DB 연결에 실패했습니다.")
                return

            for i, place in enumerate(self.places):
                if not self.is_running:
                    break
                
                self.progress.emit(f"({i+1}/{len(self.places)}) {place['name']} 확인 중...")
                
                if place.get('naver_place_id'):
                    new_intro = realtime_crawler.crawl_introduction(place['naver_place_id'])
                    if new_intro:
                        print(f"  [UPDATE] '{place['name']}'의 소개 정보가 업데이트되었습니다.")
                        place['intro'] = new_intro
                        db_manager.update_introduction(db_conn, place['naver_place_id'], new_intro)
                        print(f"  [DB] '{place['name']}'의 업데이트된 정보가 DB에 저장될 예정입니다.")
                    else:
                        print(f"  [SKIP] '{place['name']}'의 실시간 정보 확인에 실패하여 기존 정보를 사용합니다.")
            
            if self.is_running:
                db_conn.commit()
                print("[DB] 모든 변경사항이 DB에 최종적으로 저장되었습니다.")
                self.finished.emit(self.places)

        except Exception as e:
            if db_conn:
                db_conn.rollback()
            self.error.emit(f"크롤링 중 오류 발생: {e}")
        finally:
            if db_conn:
                db_conn.close()

    def stop(self):
        self.is_running = False


class ArticleWorker(QObject):
    """AI 기사 생성을 백그라운드에서 수행하는 워커"""
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, chatbot, query, places_json, weather_text):
        super().__init__()
        self.chatbot = chatbot
        self.query = query
        self.places_json = places_json
        self.weather_text = weather_text

    def run(self):
        try:
            article = self.chatbot.recommend_travel_article(
                self.query, [], self.places_json, self.weather_text
            )
            article = re.sub(r'[ \t]{2,}', ' ', article)
            self.finished.emit(article)
        except Exception as e:
            self.error.emit(f"기사 생성 중 오류 발생: {e}")


class TravelLogic(QObject):
    """여행 탭의 모든 비즈니스 로직을 처리하는 클래스"""
    # 작업 결과를 컨트롤러(TravelTabWidget)로 전달하기 위한 시그널
    crawling_progress = pyqtSignal(str)
    crawling_error = pyqtSignal(str)
    article_generated = pyqtSignal(str)
    article_error = pyqtSignal(str)

    def __init__(self, db_path, category_mapping, chatbot, weather_api):
        super().__init__()
        self.db_path = db_path
        self.category_mapping = category_mapping
        self.chatbot = chatbot
        self.weather_api = weather_api
        self.crawler_thread = None
        self.crawler_worker = None
        self.article_thread = None
        self.article_worker = None

    def get_initial_filter_data(self):
        """UI 필터 초기화에 필요한 데이터를 DB에서 조회"""
        provinces = db_manager.get_province_list(self.db_path)
        categories = sorted(self.category_mapping.keys())
        review_categories = [
            "가격/가성비", "맛/음식", "분위기/경관", "시설/청결", "서비스/친절",
            "활동/경험", "접근성/편의성", "상품/제품", "대상", "아이 관련", "반려동물 관련", "기타"
        ]
        sort_options = ["인기 순", "주소 순", "이름 순"]
        return {
            "provinces": provinces,
            "categories": categories,
            "review_categories": review_categories,
            "sort_options": sort_options
        }

    def get_cities_for_provinces(self, provinces):
        """선택된 도/특별시에 속한 시/군/구 목록을 반환"""
        cities_set = set()
        target_provinces = provinces if provinces else db_manager.get_province_list(self.db_path)
        for p in target_provinces:
            try:
                for c in db_manager.get_city_list(p, self.db_path):
                    cities_set.add(c)
            except Exception:
                pass
        return sorted(cities_set)

    def get_dongs_for_cities(self, provinces, cities):
        """선택된 도/특별시와 시/군/구에 속한 읍/면/동 목록을 반환"""
        dongs_set = set()
        target_provinces = provinces if provinces else db_manager.get_province_list(self.db_path)

        if not cities:
            for p in target_provinces:
                try:
                    for c in db_manager.get_city_list(p, self.db_path):
                        for d in db_manager.get_dong_list(p, c, self.db_path):
                            dongs_set.add(d)
                except Exception:
                    pass
        else:
            for p in target_provinces:
                try:
                    p_cities = set(db_manager.get_city_list(p, self.db_path))
                    for c in cities:
                        if c in p_cities:
                            for d in db_manager.get_dong_list(p, c, self.db_path):
                                dongs_set.add(d)
                except Exception:
                    pass
        return sorted(dongs_set)

    def build_region_index(self):
        """자동완성을 위한 전체 지역 인덱스를 생성하여 반환"""
        region_index = []
        region_map = {}
        provinces = db_manager.get_province_list(self.db_path)
        for p in provinces:
            try:
                cities = db_manager.get_city_list(p, self.db_path)
            except Exception:
                cities = []
            
            for c in cities:
                label = f"{p} > {c}"
                region_index.append((label, p, c, None))
                region_map[label] = (p, c, None)
                
                try:
                    dongs = db_manager.get_dong_list(p, c, self.db_path)
                    for d in dongs:
                        dong_label = f"{p} > {c} > {d}"
                        region_index.append((dong_label, p, c, d))
                        region_map[dong_label] = (p, c, d)
                except Exception:
                    pass
        return region_index, region_map

    def search_places(self, filters):
        """필터 조건에 따라 장소를 검색하고 결과를 반환"""
        sel_prov_list = filters.get("provinces", [])
        sel_city = filters.get("cities", [])
        sel_dong_raw = set(filters.get("dongs", []))
        sel_cats = filters.get("categories", [])
        sel_review_cats_raw = set(filters.get("review_categories", []))
        sel_review_cats = set(filters.get("review_categories", []))
        review_range = filters.get("review_range", "상위 50%")

        filter_by_road_name = "도로명" in sel_dong_raw
        normal_dongs = sel_dong_raw - {"도로명"}

        try:
            search_city = sel_city[0] if len(sel_city) == 1 else None
            search_dong = list(normal_dongs)[0] if len(normal_dongs) == 1 and not filter_by_road_name else None

            target_provs = sel_prov_list if sel_prov_list else db_manager.get_province_list(self.db_path)
            merged = {}

            for pv in target_provs:
                res = db_manager.search_places_advanced_with_dong(
                    self.db_path, pv, search_city, search_dong, []
                )
                for place in res:
                    key = (place.get('name',''), place.get('address',''))
                    merged[key] = place

            places = list(merged.values())

            # 도시 다중 선택 보정
            if sel_city and len(sel_city) > 1:
                places = [p for p in places if any(city in (p.get('address', '') or '') for city in sel_city)]

            # 동 필터링 (도로명 포함)
            if sel_dong_raw:
                def _get_dong_from_addr(addr):
                    parts = (addr or "").split()
                    if len(parts) > 2:
                        d = parts[2]
                        # 숫자나 숫자-숫자 형태가 아닌 경우만 동으로 간주
                        if not (d.isdigit() or ('-' in d and all(c.isdigit() for c in d.split('-')))):
                            return d
                    return None

                def _is_road_name(dong_part):
                    road_suffixes = ("길", "로", "대로", "가로", "거리")
                    return any(dong_part.endswith(s) for s in road_suffixes)

                final_places = []
                for place in places:
                    address = place.get('address', '') or ''
                    matched = False

                    # 일반 동 이름 매칭
                    if normal_dongs:
                        if any(d in address for d in normal_dongs):
                            final_places.append(place)
                            matched = True
                    
                    # 도로명 매칭
                    if not matched and filter_by_road_name:
                        dong_part = _get_dong_from_addr(address)
                        if dong_part and _is_road_name(dong_part):
                            final_places.append(place)
                
                places = final_places

        except Exception as e:
            print(f"검색 오류: {e}")
            places = []

        # ----------------------
        # 파이썬 측 정규화 필터링
        # ----------------------
        sel_ui_cat_set = set(sel_cats)
        if sel_ui_cat_set or sel_review_cats:
            filtered = []
            for place in places:
                if _place_matches_filters(place, sel_ui_cat_set, sel_review_cats):
                    filtered.append(place)
            places = filtered

        # 리뷰 수(방문+블로그) 비중 필터
        places = self._apply_review_count_filter(places, review_range)
        return places

    def _apply_review_count_filter(self, places, review_range="상위 50%"):
        """리뷰 수 기준으로 필터를 적용"""
        if not places or review_range == "전체":
            return places
        
        def get_total_reviews(place):
            visitor_reviews = place.get('total_visitor_reviews', 0) or 0
            blog_reviews = place.get('total_blog_reviews', 0) or 0
            try:
                return int(visitor_reviews) + int(blog_reviews)
            except (ValueError, TypeError):
                # 숫자가 문자열로 들어올 수 있으니 재시도
                try:
                    return int(str(visitor_reviews).replace(',', '')) + int(str(blog_reviews).replace(',', ''))
                except Exception:
                    return 0
        
        sorted_places = sorted(places, key=get_total_reviews, reverse=True)

        if review_range == "상위 10%":
            cut_off = max(1, int(len(sorted_places) * 0.1))
        elif review_range == "상위 30%":
            cut_off = max(1, int(len(sorted_places) * 0.3))
        elif review_range == "상위 50%":
            cut_off = max(1, int(len(sorted_places) * 0.5))
        else:
            return sorted_places
        
        return sorted_places[:cut_off]

    def start_article_generation(self, selected_places, article_title, include_weather, weather_query_location):
        """실시간 크롤링 및 기사 생성 프로세스를 시작"""
        self.crawler_thread = QThread()
        self.crawler_worker = CrawlerWorker(self.db_path, selected_places)
        self.crawler_worker.moveToThread(self.crawler_thread)

        self.crawler_thread.started.connect(self.crawler_worker.run)
        self.crawler_worker.finished.connect(lambda places: self._on_crawling_finished(places, article_title, include_weather, weather_query_location))
        self.crawler_worker.error.connect(self.crawling_error.emit)
        self.crawler_worker.progress.connect(self.crawling_progress.emit)
        
        self.crawler_worker.finished.connect(self.crawler_thread.quit)
        self.crawler_worker.finished.connect(self.crawler_worker.deleteLater)
        self.crawler_thread.finished.connect(self.crawler_thread.deleteLater)

        self.crawler_thread.start()

    def _on_crawling_finished(self, updated_places, article_title, include_weather, weather_query_location):
        """크롤링 완료 후 AI 기사 생성 스레드를 시작"""
        weather_info_text = ""
        if include_weather:
            try:
                if not weather_query_location:
                    raise ValueError("날씨 정보를 포함하려면 지역을 명확히 선택해야 합니다.")
                weather_data = self.weather_api.get_weather_data(weather_query_location)
                weather_info_text = self.weather_api.format_weather_info(weather_data, weather_query_location)
            except Exception as e:
                weather_info_text = f"날씨 정보를 가져오는 데 실패했습니다: {e}"

        df = pd.DataFrame(updated_places)
        columns_to_send = ['name', 'category', 'address', 'keywords', 'visitor_reviews', 'intro']
        # 존재하지 않는 컬럼이 있어도 안전하게 처리
        for col in list(columns_to_send):
            if col not in df.columns:
                df[col] = ""
        places_json = df[columns_to_send].to_json(orient='records', force_ascii=False)

        self.article_thread = QThread()
        self.article_worker = ArticleWorker(self.chatbot, article_title, places_json, weather_info_text)
        self.article_worker.moveToThread(self.article_thread)

        self.article_thread.started.connect(self.article_worker.run)
        self.article_worker.finished.connect(self.article_generated.emit)
        self.article_worker.error.connect(self.article_error.emit)

        self.article_worker.finished.connect(self.article_thread.quit)
        self.article_worker.finished.connect(self.article_worker.deleteLater)
        self.article_thread.finished.connect(self.article_thread.deleteLater)

        self.article_thread.start()

# Force recompile
