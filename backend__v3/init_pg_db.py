"""
init_pg_db.py
Supabase (PostgreSQL) 최초 연동 시 테이블(스키마)을 생성해주는 일회용 스크립트.
main.py에서 테이블 자동 생성이 비활성화되어 있으므로 이 스크립트를 수동으로 한 번 실행합니다.
"""

from database import engine, Base
# 모델들이 등록되어 있어야 테이블이 생성되므로 models.py를 임포트합니다.
import models

def init_db():
    print("PostgreSQL(Supabase) 테이블 생성을 시작합니다...")
    # Base에 연결된 모든 모델의 테이블을 DB에 생성합니다.
    # 이미 존재하는 테이블은 무시됩니다.
    Base.metadata.create_all(bind=engine)
    print("테이블 생성이 완료되었습니다.")

if __name__ == "__main__":
    init_db()
