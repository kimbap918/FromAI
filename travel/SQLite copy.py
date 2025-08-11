# 데이터베이스에 테스트 데이터를 삽입하는 유틸리티 스크립트입니다.
import sqlite3

conn = sqlite3.connect(r'C:\Users\TDI\Desktop\0804 작업\FromAI-crw\crw_data\naver_travel_places.db')
cursor = conn.cursor()

cursor.execute("""
INSERT INTO places (
    naver_place_id, name, category, address,
    total_visitor_reviews_count, total_blog_reviews_count,
    introduction, keywords, visitor_reviews, search_keyword
)
VALUES (
    'test001', '테스트 장소', '테스트 카테고리', '테스트 주소',
    100, 200, '테스트 소개', '테스트 키워드', '테스트 방문자 리뷰', '테스트 검색어'
);
""")

conn.commit()
conn.close()
print("테스트 삽입 완료")
