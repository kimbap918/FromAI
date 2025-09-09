# db_manager.py - SQLite 데이터베이스 관리 및 장소 검색
# ===================================================================================
# 파일명     : db_manager.py
# 작성자     : 하승주, 홍석원
# 최초작성일 : 2025-09-04
# 설명       : 네이버 크롤링 데이터가 저장된 SQLite DB 연결/조회 및
#              지역별(도/시/동) 계층적 장소 검색과 카테고리 기반 필터링 지원
# ===================================================================================
#
# 【주요 기능】
# - 네이버 크롤링 데이터가 저장된 SQLite DB 연결/조회
# - 지역별(도/시/동) 계층적 장소 검색
# - 카테고리 및 리뷰 기반 필터링
# - UI용 카테고리 매핑 데이터 생성
# - 크롤링 단계: 크롤링한 장소 데이터를 DB에 저장/갱신 (initialize_db, save_places_to_db 등 활용)
# - 앱 실행 단계: DB에서 지역/카테고리별 장소를 검색하여 기사 생성에 활용
#
# 【DB 스키마】
# - places 테이블: 장소 정보 저장
#   * naver_place_id, name, category, address
#   * total_visitor_reviews_count, total_blog_reviews_count  
#   * introduction, keywords, visitor_reviews
#
# 【핵심 검색 기능】
# - get_province_list(): 도/특별시 목록 (장소 수 순 정렬)
# - get_city_list(): 특정 도의 시/군/구 목록
# - get_dong_list(): 특정 시의 읍/면/동 목록
# - search_places_advanced_with_dong(): 다단계 지역 필터 검색
#
# 【지역 정규화】
# - 강원특별자치도 ↔ 강원도 통합 처리
# - 전라북도 ↔ 전북특별자치도 통합 처리
# - 별칭 매핑으로 검색 범위 확장
#
# 【데이터 관리】
# - save_places_to_db(): 크롤링 데이터 저장
# - update_introduction(): 실시간 크롤링으로 소개 정보 업데이트
# - check_place_exists(): 중복 체크
#
# 【사용처】
# - travel_logic.py: 장소 검색 및 필터링
# - travel_tab.py: UI 드롭다운 데이터 제공
# - chatbot_app.py: 기사 작성 전 DB 연결/테이블 확인
# ===================================================================================

import os
import sqlite3
from collections import defaultdict
from typing import List, Dict, Tuple, Iterable, Optional
from category_utils import normalize_category_for_ui

# ---------------------------
# [크롤링 단계] DB 연결/초기화
# ---------------------------
def create_connection(db_path: str) -> Optional[sqlite3.Connection]:
    try:
        return sqlite3.connect(db_path, timeout=10)
    except sqlite3.Error as e:
        print(f"[DB ERROR] 연결 실패: {e}")
        return None

def initialize_db(db_path: str) -> None:
    conn = create_connection(db_path)
    if not conn: return
    try:
        c = conn.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS places (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            naver_place_id TEXT UNIQUE NOT NULL,
            name TEXT,
            category TEXT,
            address TEXT,
            total_visitor_reviews_count INTEGER DEFAULT 0,
            total_blog_reviews_count INTEGER DEFAULT 0,
            introduction TEXT,
            keywords TEXT,
            visitor_reviews TEXT,
            search_keyword TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        conn.commit()
        print(f"[DB] '{os.path.basename(db_path)}' 초기화 완료")
    except sqlite3.Error as e:
        print(f"[DB ERROR] 테이블 생성 실패: {e}")
    finally:
        conn.close()

# ---------------------------
# [크롤링 단계] 레거시 호환 (앱 실행 때도 연결 확인용으로 사용)
# ---------------------------
def connect_db(db_path: str):
    conn = create_connection(db_path)
    cur = conn.cursor() if conn else None
    return conn, cur

def create_places_table(cursor) -> bool:
    try:
        cursor.execute("SELECT 1 FROM places LIMIT 1")
        return True
    except Exception:
        return False

# ---------------------------
# 공용 유틸 (크롤링 + 앱 실행 둘 다 사용)
# ---------------------------
# 강원/전북 단일 표기: 강원특별자치도→강원, 전라북도/전북특별자치도→전북
_PROV_CANON_MAP = {
    "강원특별자치도": "강원", "강원": "강원",
    "전북특별자치도": "전북", "전라북도": "전북", "전북": "전북",
}

def _canon_province(raw: str) -> str:
    raw = (raw or "").strip()
    return _PROV_CANON_MAP.get(raw, raw)

def _aliases_for_province(canon: str) -> List[str]:
    # 검색 시 사용할 주소 1토큰 후보들
    if canon == "강원":
        return ["강원", "강원특별자치도"]
    if canon == "전북":
        return ["전북", "전라북도", "전북특별자치도"]
    return [canon]

def _first_token(addr: str) -> str:
    parts = (addr or "").split()
    return parts[0] if parts else ""

def _nth_token(addr: str, n: int) -> str:
    parts = (addr or "").split()
    return parts[n] if len(parts) > n else ""

def _iter_addresses(conn: sqlite3.Connection) -> Iterable[str]:
    for (addr,) in conn.execute("SELECT address FROM places WHERE address IS NOT NULL AND address != ''"):
        yield addr

def _normalize_dong_for_ui(dong: str) -> str:
    if not dong: return "기타"
    road_suffix = ("길", "로", "대로", "가로", "거리", "avenue", "street", "road")
    return "도로명" if dong.endswith(road_suffix) else dong

def _is_numeric_token(tok: str) -> bool:
    t = (tok or "").replace("-", "")
    return t.isdigit()

# ---------------------------
# [크롤링 단계] 중복 검사 / 저장 / 업데이트
# ---------------------------
def check_place_exists(conn_or_path, naver_place_id: str) -> bool:
    try:
        if isinstance(conn_or_path, sqlite3.Connection):
            cur = conn_or_path.cursor()
            close = False
        else:
            conn = create_connection(conn_or_path)
            if not conn: return False
            cur, close = conn.cursor(), True
        cur.execute("SELECT 1 FROM places WHERE naver_place_id = ?", (naver_place_id,))
        ok = cur.fetchone() is not None
        if close: conn.close()
        return ok
    except sqlite3.Error as e:
        print(f"[DB ERROR] 존재 확인 실패: {e}")
        return False

def save_places_to_db(conn: sqlite3.Connection, places_data: List[Dict]) -> int:
    if not places_data: return 0
    try:
        before = conn.execute("SELECT COUNT(*) FROM places").fetchone()[0]
        conn.executemany("""
            INSERT OR IGNORE INTO places (
              naver_place_id, name, category, address,
              total_visitor_reviews_count, total_blog_reviews_count,
              introduction, keywords, visitor_reviews, search_keyword
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [(
            p.get("naver_place_id"),
            p.get("장소명"),
            p.get("카테고리"),
            p.get("주소"),
            int(p.get("총 방문자 리뷰 수", 0) or 0),
            int(p.get("총 블로그 리뷰 수", 0) or 0),
            p.get("소개"),
            p.get("키워드"),
            p.get("방문자 리뷰"),
            p.get("검색어"),
        ) for p in places_data])
        conn.commit()
        after = conn.execute("SELECT COUNT(*) FROM places").fetchone()[0]
        saved = after - before
        if saved:
            print(f"[DB] 새 장소 {saved}건 저장")
        return saved
    except sqlite3.Error as e:
        print(f"[DB ERROR] 저장 실패: {e}")
        return 0

def update_introduction(conn_or_path, naver_place_id: str, new_introduction: str) -> None:
    conn = None
    internal = False
    try:
        if isinstance(conn_or_path, sqlite3.Connection):
            conn = conn_or_path
        else:
            conn = create_connection(conn_or_path)
            internal = True
            if not conn: 
                print("[DB ERROR] 연결 실패로 소개 업데이트 중단")
                return
        conn.execute("UPDATE places SET introduction = ? WHERE naver_place_id = ?",
                     (new_introduction, naver_place_id))
        if internal:
            conn.commit()
    except sqlite3.Error as e:
        print(f"[DB ERROR] 소개 업데이트 실패(ID={naver_place_id}): {e}")
    finally:
        if conn and internal:
            conn.close()

# ---------------------------
# [앱 실행 단계] 지역 리스트 (장소 많은 순 정렬)
# ---------------------------
def get_province_list(db_path: str) -> List[str]:
    conn = create_connection(db_path)
    if not conn: return []
    try:
        cnt = defaultdict(int)
        for addr in _iter_addresses(conn):
            p = _canon_province(_first_token(addr))
            if p: cnt[p] += 1
        # 장소 수 내림차순, 이름 오름차순
        return [p for p, _ in sorted(cnt.items(), key=lambda x: (-x[1], x[0]))]
    finally:
        conn.close()

def get_city_list(province: str, db_path: str) -> List[str]:
    conn = create_connection(db_path)
    if not conn: return []
    try:
        aliases = _aliases_for_province(_canon_province(province))
        cnt = defaultdict(int)
        for addr in _iter_addresses(conn):
            p = _first_token(addr)
            if p not in aliases: 
                # 별칭이 짧은 '전북'이 주소에 직접 들어갈 수도 있어 보조 체크
                if _canon_province(p) != _canon_province(province):
                    continue
            c = _nth_token(addr, 1)
            if c: cnt[c] += 1
        return [c for c, _ in sorted(cnt.items(), key=lambda x: (-x[1], x[0]))]
    finally:
        conn.close()

def get_dong_list(province: str, city: str, db_path: str) -> List[str]:
    conn = create_connection(db_path)
    if not conn: return []
    try:
        aliases = _aliases_for_province(_canon_province(province))
        cnt = defaultdict(int)
        for addr in _iter_addresses(conn):
            p = _first_token(addr)
            if (p not in aliases) and (_canon_province(p) != _canon_province(province)):
                continue
            if _nth_token(addr, 1) != city:
                continue
            d = _nth_token(addr, 2)
            if not d or _is_numeric_token(d):
                continue
            d = _normalize_dong_for_ui(d)
            cnt[d] += 1
        return [d for d, _ in sorted(cnt.items(), key=lambda x: (-x[1], x[0]))]
    finally:
        conn.close()

# ---------------------------
# [앱 실행 단계] 장소 검색 (도/시/동) — 주소 기반
#   * province='강원' → 강원/강원특별자치도 모두 매칭
#   * city/dong 미지정(None) 허용
# ---------------------------
def search_places_advanced_with_dong(
    db_path: str, province: Optional[str], city: Optional[str], dong: Optional[str], categories: List[str]
) -> List[Dict]:
    conn = create_connection(db_path)
    if not conn: return []
    try:
        sql = "SELECT name, category, address, keywords, total_visitor_reviews_count, total_blog_reviews_count, visitor_reviews, introduction, naver_place_id FROM places"
        where = []
        params: List[str] = []

        # 주소 LIKE 조건(별칭 포함)
        if province:
            aliases = _aliases_for_province(_canon_province(province))
        else:
            aliases = []

        # 경우의 수(도/시/동 조합)
        like_blocks = []
        if aliases:
            for a in aliases:
                prefix = a
                if city:  prefix += f" {city}"
                if dong:  prefix += f" {dong}"
                like_blocks.append("address LIKE ?")
                params.append(prefix + "%")
        elif city or dong:
            # 도 없이 시/동만 온 특수 케이스(드뭄)
            prefix = ""
            if city: prefix += f"% {city}"
            if dong: prefix += f" {dong}"
            if prefix:
                like_blocks.append("address LIKE ?")
                params.append(prefix + "%")

        if like_blocks:
            where.append("(" + " OR ".join(like_blocks) + ")")

        if where:
            sql += " WHERE " + " AND ".join(where)

        rows = conn.execute(sql, params).fetchall()
        cols = ["name","category","address","keywords","total_visitor_reviews","total_blog_reviews","visitor_reviews","intro","naver_place_id"]
        return [dict(zip(cols, r)) for r in rows]
    finally:
        conn.close()

# ---------------------------
# [앱 실행 단계] 기사/통계용 매핑
# ---------------------------
def get_category_mapping(db_path: str) -> Dict[str, List[Tuple[str, str]]]:
    """
    UI 카테고리 → [(장소명, 동)] 목록.
    * 간결화: category를 normalize_category_for_ui로만 정규화
    """
    out: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
    conn = create_connection(db_path)
    if not conn: return out
    try:
        for name, cat, addr in conn.execute("SELECT name, category, address FROM places WHERE name IS NOT NULL"):
            ui = normalize_category_for_ui(cat or "")
            dong = _nth_token(addr or "", 2)
            out[ui].append((name, dong))
    finally:
        conn.close()
    return out

def get_dong_mapping(db_path: str) -> Dict[str, List[str]]:
    """
    '도 시 동' 키 → [장소명...] 목록.
    (UI 검색 자동완성/기사용 간단 통계)
    """
    out: Dict[str, List[str]] = defaultdict(list)
    conn = create_connection(db_path)
    if not conn: return out
    try:
        for name, addr in conn.execute("SELECT name, address FROM places WHERE address IS NOT NULL AND address != ''"):
            parts = addr.split()
            if len(parts) >= 3:
                key = f"{_canon_province(parts[0])} {parts[1]} {parts[2]}"
                out[key].append(name)
    finally:
        conn.close()
    return out
