import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# 프로젝트 루트의 .env 경로를 동적으로 계산하여 로드합니다.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env_path = os.path.join(BASE_DIR, '.env')
load_dotenv(dotenv_path=env_path)

# .env 파일에서 DB 주소를 가져옵니다.
db_url = os.getenv("DATABASE_URL") or os.getenv("DB_URL") or os.getenv("SQLALCHEMY_DATABASE_URI")

if not db_url:
    print("[ERROR] 지정된 .env 파일에서 DB 주소를 찾을 수 없습니다.")
    print("해결책: .env 파일을 열어서 postgresql:// 로 시작하는 변수명을 확인해 주세요.")
    exit(1)

engine = create_engine(db_url)
tables = [
    "Performance", "Work", "Genre", "Composer", "Artist",
    "Performance_Artist", "Performance_Work", "Performance_Composer"
]

print("[INFO] 데이터베이스 시퀀스(번호표) 자동 동기화를 시작합니다...\n")

with engine.connect() as conn:
    for table in tables:
        try:
            # public 스키마를 명확히 지정하여 진짜 시퀀스를 찾아 강제 동기화
            query = text(f"""
            SELECT setval(pg_get_serial_sequence('public."{table}"', 'id'), 
                          COALESCE((SELECT MAX(id) FROM public."{table}"), 1));
            """)
            val = conn.execute(query).scalar()
            print(f"[SUCCESS] '{table}' 테이블 번호표 세팅 완료 -> 현재 최댓값: {val}")
        except Exception as e:
            print(f"[WARN] '{table}' 테이블 처리 중 알림: {e}")
    
    conn.commit()

print("\n[INFO] 동기화가 완료되었습니다. 스케줄러를 다시 실행해 주십시오.")