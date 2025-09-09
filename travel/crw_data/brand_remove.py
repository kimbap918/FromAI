#스타벅스, 맥도날드등의 지점 삭제
import sqlite3, pandas as pd, shutil, os

DB_PATH   = r"C:\Users\TDI\Desktop\0909_여행&날씨 기사생성기\crw_data\naver_travel_places.db"            # ← 네 경로로 바꿔줘
CSV_PATH  = r"C:\Users\TDI\Desktop\0909_여행&날씨 기사생성기\crw_data\chain_over15_brand_list.csv"       # ← 네 경로로 바꿔줘
BACKUP    = DB_PATH.replace(".db", "_backup_before_delete.db")

# 1) 백업
if not os.path.exists(BACKUP):
    shutil.copy2(DB_PATH, BACKUP)

# 2) 브랜드 로드
brands = pd.read_csv(CSV_PATH, dtype=str)
col = "brand_key" if "brand_key" in brands.columns else brands.columns[0]
words = (brands[col].dropna().astype(str).str.strip().unique().tolist())

# 3) LIKE 안전 이스케이프
def esc_like(s: str) -> str:
    return s.replace("!", "!!").replace("%","!%").replace("_","!_")

params = [f"%{esc_like(w)}%" for w in words]

with sqlite3.connect(DB_PATH) as con:
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=OFF;")
    con.execute("PRAGMA temp_store=MEMORY;")

    total_before = con.execute("SELECT COUNT(*) FROM places").fetchone()[0]
    print("총 행(삭제 전):", total_before)

    # 4) 한 방에 새 테이블 생성 (모든 브랜드 NOT LIKE)
    where_not = " AND ".join(["name NOT LIKE ? ESCAPE '!'"] * len(params))
    sql = f"CREATE TABLE places_filtered AS SELECT * FROM places WHERE {where_not}"
    con.execute(sql, params)

    # 5) 원본 교체
    con.execute("DROP TABLE places")
    con.execute("ALTER TABLE places_filtered RENAME TO places")
    con.execute("VACUUM")

    total_after = con.execute("SELECT COUNT(*) FROM places").fetchone()[0]
    print("총 행(삭제 후):", total_after)
    print("삭제 수:", total_before - total_after)
