#################################################################################################
#################################################################################################
####8월 8일 읍면동 반영 시도####
import sqlite3
import os
from category_utils import normalize_category_for_ui

def create_connection(db_name):
    """데이터베이스 연결을 생성하고 반환합니다."""
    try:
        conn = sqlite3.connect(db_name, timeout=10)
        return conn
    except sqlite3.Error as e:
        print(f"[DB ERROR] DB 연결 실패: {e}")
        return None

def get_category_mapping(db_path):
    conn = create_connection(db_path)
    if not conn:
        return {}
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT category FROM places WHERE category IS NOT NULL AND category != ''")
        all_categories = [row[0] for row in cursor.fetchall()]
        
        mapping = {}
        for original_cat in all_categories:
            normalized_cat = normalize_category_for_ui(original_cat)
            if normalized_cat not in mapping:
                mapping[normalized_cat] = []
            mapping[normalized_cat].append(original_cat)
        return mapping
    except sqlite3.Error as e:
        print(f"[DB ERROR] 카테고리 매핑 조회 실패: {e}")
        return {}
    finally:
        if conn:
            conn.close()

def get_province_list(db_path):
    conn = create_connection(db_path)
    if not conn:
        return []
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT SUBSTR(address, 1, INSTR(address, ' ') - 1) FROM places WHERE address LIKE '%_ %'")
        provinces = [row[0] for row in cursor.fetchall() if row[0]]
        return sorted(list(set(provinces)))
    except sqlite3.Error as e:
        print(f"[DB ERROR] 도/특별시 목록 조회 실패: {e}")
        return []
    finally:
        if conn:
            conn.close()

def get_city_list(province, db_path):
    conn = create_connection(db_path)
    if not conn:
        return []
    try:
        cursor = conn.cursor()
        query = f"SELECT DISTINCT SUBSTR(address, INSTR(address, ' ') + 1, INSTR(SUBSTR(address, INSTR(address, ' ') + 1), ' ') - 1) FROM places WHERE address LIKE ?"
        cursor.execute(query, (province + ' %',))
        cities = [row[0] for row in cursor.fetchall() if row[0]]
        return sorted(list(set(cities)))
    except sqlite3.Error as e:
        print(f"[DB ERROR] 시/군/구 목록 조회 실패: {e}")
        return []
    finally:
        if conn:
            conn.close()

def normalize_dong_for_ui(dong_name):
    """
    읍/면/동명을 UI용으로 정규화합니다.
    도로명(~길, ~로 등)은 "도로명"으로 통합합니다.
    """
    if not dong_name:
        return "기타"
    
    # 도로명 키워드들
    road_keywords = ["길", "로", "대로", "가로", "거리", "avenue", "street", "road"]
    
    # 도로명으로 끝나는 경우 "도로명"으로 통합
    if any(dong_name.endswith(keyword) for keyword in road_keywords):
        return "도로명"
    
    # 그 외는 그대로 반환
    return dong_name

def get_dong_mapping(province, city, db_path):
    """읍/면/동의 UI 매핑을 가져오는 함수 (카테고리 매핑과 동일한 방식)"""
    conn = create_connection(db_path)
    if not conn:
        return {}
    
    try:
        cursor = conn.cursor()
        
        # 주소에서 도로명/지역명 추출
        cursor.execute("""
            SELECT DISTINCT address FROM places 
            WHERE address LIKE ? AND address LIKE ?
        """, (f'{province}%', f'%{city}%'))
        
        addresses = cursor.fetchall()
        all_dongs = []
        
        for address_tuple in addresses:
            address = address_tuple[0]
            parts = address.split()
            
            # 주소 형태: "광주 동구 제봉로 100-1 길" -> 3번째 부분인 "제봉로"를 추출
            if len(parts) >= 3:
                dong_part = parts[2]  # 3번째 부분 (0-indexed로 2번째)
                
                # 숫자로만 이루어진 경우는 제외 (예: "100-1" 같은 번지수)
                if not dong_part.replace('-', '').isdigit():
                    all_dongs.append(dong_part)
        
        # 매핑 생성 (카테고리와 동일한 방식)
        mapping = {}
        for original_dong in all_dongs:
            normalized_dong = normalize_dong_for_ui(original_dong)
            if normalized_dong not in mapping:
                mapping[normalized_dong] = []
            if original_dong not in mapping[normalized_dong]:
                mapping[normalized_dong].append(original_dong)
                
        return mapping
        
    except sqlite3.Error as e:
        print(f"[DB ERROR] 읍/면/동 매핑 조회 실패: {e}")
        return {}
    finally:
        if conn:
            conn.close()

def get_dong_list(province, city, db_path):
    """특정 도/시와 시/군/구의 읍/면/동(UI용 정규화된) 목록을 가져오는 함수"""
    dong_mapping = get_dong_mapping(province, city, db_path)
    return sorted(list(dong_mapping.keys()))

def search_provinces_by_partial_name(partial_name, db_path):
    provinces = get_province_list(db_path)
    return [p for p in provinces if partial_name.lower() in p.lower()]

def search_cities_by_partial_name(province, partial_name, db_path):
    cities = get_city_list(province, db_path)
    return [c for c in cities if partial_name.lower() in c.lower()]

def search_dongs_by_partial_name(province, city, partial_dong, db_path):
    """부분 읍/면/동명으로 검색하는 함수"""
    dong_mapping = get_dong_mapping(province, city, db_path)
    all_dongs = list(dong_mapping.keys())
    suggestions = [dong for dong in all_dongs if partial_dong.lower() in dong.lower()]
    return suggestions

def search_places_advanced(db_path, province, city, categories):
    conn = create_connection(db_path)
    if not conn:
        return []
    try:
        cursor = conn.cursor()
        query = "SELECT name, category, address, keywords, visitor_reviews, introduction, total_visitor_reviews_count, total_blog_reviews_count FROM places WHERE 1=1"
        params = []

        if province and province != '전체':
            query += " AND address LIKE ?"
            params.append(province + '%')
        
        if city and city != '전체':
            query += " AND address LIKE ?"
            params.append(f"%{city}%")

        if categories:
            placeholders = ', '.join('?' for _ in categories)
            query += f" AND category IN ({placeholders})"
            params.extend(categories)

        cursor.execute(query, params)
        places = cursor.fetchall()
        
        # 결과를 딕셔너리 리스트로 변환
        result = []
        for row in places:
            result.append({
                'name': row[0],
                'category': row[1],
                'address': row[2],
                'keywords': row[3],
                'visitor_reviews': row[4],
                'intro': row[5],
                'total_visitor_reviews': row[6],
                'total_blog_reviews': row[7]
            })
        return result

    except sqlite3.Error as e:
        print(f"[DB ERROR] 장소 검색 실패: {e}")
        return []
    finally:
        if conn:
            conn.close()

def search_places_advanced_with_dong(db_path, province, city, dong, categories):
    """읍/면/동까지 포함한 고급 장소 검색 함수"""
    conn = create_connection(db_path)
    if not conn:
        return []
    
    try:
        cursor = conn.cursor()
        
        # 기본 쿼리
        query = """
            SELECT name, category, address, keywords, visitor_reviews, introduction,
                   total_visitor_reviews_count, total_blog_reviews_count
            FROM places 
            WHERE 1=1
        """
        params = []
        
        # 도/특별시 필터
        if province and province != "전체":
            query += " AND address LIKE ?"
            params.append(f'{province}%')
        
        # 시/군/구 필터  
        if city and city != "전체":
            query += " AND address LIKE ?"
            params.append(f'%{city}%')
        
        # 읍/면/동 필터 (매핑 고려)
        if dong and dong != "전체":
            # 선택된 dong이 매핑된 그룹인지 확인
            dong_mapping = get_dong_mapping(province, city, db_path)
            if dong in dong_mapping:
                # 매핑된 그룹이면 해당하는 모든 원본 dong들로 검색
                original_dongs = dong_mapping[dong]
                dong_conditions = []
                for original_dong in original_dongs:
                    dong_conditions.append("address LIKE ?")
                    params.append(f'%{original_dong}%')
                
                if dong_conditions:
                    query += f" AND ({' OR '.join(dong_conditions)})"
            else:
                # 일반적인 dong 검색
                query += " AND address LIKE ?"
                params.append(f'%{dong}%')
        
        # 카테고리 필터
        if categories:
            category_conditions = []
            for category in categories:
                category_conditions.append("category LIKE ?")
                params.append(f'%{category}%')
            
            if category_conditions:
                query += f" AND ({' OR '.join(category_conditions)})"
        
        cursor.execute(query, params)
        results = cursor.fetchall()
        
        places = []
        for row in results:
            place = {
                'name': row[0] if row[0] else '',
                'category': row[1] if row[1] else '',
                'address': row[2] if row[2] else '',
                'keywords': row[3] if row[3] else '',
                'visitor_reviews': row[4] if row[4] else '',
                'intro': row[5] if row[5] else '',
                'total_visitor_reviews': row[6] if row[6] else 0,
                'total_blog_reviews': row[7] if row[7] else 0
            }
            places.append(place)
        
        return places
    
    except sqlite3.Error as e:
        print(f"[DB ERROR] 장소 검색 오류: {e}")
        return []
    finally:
        if conn:
            conn.close()