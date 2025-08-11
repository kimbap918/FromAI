# 데이터베이스 연결 및 상태를 진단하는 유틸리티 스크립트입니다.
import os
import sqlite3
import sys

def diagnose_database_issue():
    print("=== 데이터베이스 진단 시작 ===")
    
    # 1. 현재 작업 디렉토리 확인
    current_dir = os.getcwd()
    print(f"현재 작업 디렉토리: {current_dir}")
    
    # 2. 데이터베이스 디렉토리 확인
    db_dir = os.path.join(current_dir, 'database')
    print(f"데이터베이스 디렉토리: {db_dir}")
    print(f"데이터베이스 디렉토리 존재 여부: {os.path.exists(db_dir)}")
    
    if os.path.exists(db_dir):
        print(f"데이터베이스 디렉토리 권한: {oct(os.stat(db_dir).st_mode)[-3:]}")
    
    # 3. 데이터베이스 파일 경로들 확인
    possible_db_paths = [
        os.path.join(current_dir, 'database', 'articles.db'),
        os.path.join(current_dir, 'articles.db'),
        os.path.join(current_dir, 'database', 'news.db'),
        os.path.join(current_dir, 'news.db')
    ]
    
    print("\n=== 가능한 데이터베이스 파일 경로들 ===")
    for db_path in possible_db_paths:
        exists = os.path.exists(db_path)
        print(f"{db_path} - 존재: {exists}")
        if exists:
            try:
                size = os.path.getsize(db_path)
                print(f"  파일 크기: {size} bytes")
                print(f"  파일 권한: {oct(os.stat(db_path).st_mode)[-3:]}")
            except Exception as e:
                print(f"  파일 정보 읽기 실패: {e}")
    
    # 4. SQLite3 연결 테스트
    print("\n=== SQLite3 연결 테스트 ===")
    
    # 메모리 데이터베이스 테스트
    try:
        conn = sqlite3.connect(':memory:')
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE test (id INTEGER)")
        cursor.execute("INSERT INTO test VALUES (1)")
        result = cursor.fetchone()
        conn.close()
        print("메모리 데이터베이스 연결: 성공")
    except Exception as e:
        print(f"메모리 데이터베이스 연결 실패: {e}")
    
    # 파일 데이터베이스 생성 테스트
    test_db_path = os.path.join(current_dir, 'database', 'test.db')
    try:
        # 디렉토리가 없으면 생성
        os.makedirs(os.path.dirname(test_db_path), exist_ok=True)
        
        conn = sqlite3.connect(test_db_path)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS test (id INTEGER)")
        cursor.execute("INSERT INTO test VALUES (1)")
        conn.commit()
        conn.close()
        print(f"파일 데이터베이스 생성/연결: 성공 - {test_db_path}")
        
        # 테스트 파일 삭제
        if os.path.exists(test_db_path):
            os.remove(test_db_path)
            print("테스트 데이터베이스 파일 삭제 완료")
            
    except Exception as e:
        print(f"파일 데이터베이스 생성/연결 실패: {e}")
    
    # 5. 프로젝트 파일들 확인
    print("\n=== 프로젝트 파일들 ===")
    for file in os.listdir(current_dir):
        if file.endswith('.py'):
            print(f"Python 파일: {file}")
    
    # 6. article_generator_app.py에서 데이터베이스 경로 확인
    app_file = os.path.join(current_dir, 'article_generator_app.py')
    if os.path.exists(app_file):
        print(f"\n=== {app_file} 에서 데이터베이스 경로 검색 ===")
        try:
            with open(app_file, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.split('\n')
                for i, line in enumerate(lines, 1):
                    if '.db' in line.lower() or 'sqlite' in line.lower() or 'database' in line.lower():
                        print(f"줄 {i}: {line.strip()}")
        except Exception as e:
            print(f"파일 읽기 실패: {e}")
    
    print("\n=== 진단 완료 ===")

if __name__ == "__main__":
    diagnose_database_issue()