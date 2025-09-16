import sqlite3

db_path = "C:\\Users\\a\\Desktop\\0909_여행&날씨 기사생성기_수정본\\crw_data\\naver_travel_places.db"
try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    query = "SELECT name, category, total_visitor_reviews_count, total_blog_reviews_count FROM places WHERE category LIKE '%절%' OR category LIKE '%사찰%' LIMIT 50"
    cursor.execute(query)

    results = cursor.fetchall()

    if results:
        print(f"Found {len(results)} places (showing up to 50):")
        for row in results:
            print(f"  - Name: {row[0]}, Category: {row[1]}, Visitor Reviews: {row[2]}, Blog Reviews: {row[3]}")
    else:
        print("No places found with '절' or '사찰' in the category.")

    conn.close()
except Exception as e:
    print(f"An error occurred: {e}")