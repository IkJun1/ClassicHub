"""
reset_db.py
기존 DB를 초기화하고 시드 데이터를 새로 적재합니다.

실행 방법:
    cd backend_v1/app
    python reset_db.py

왜 별도 스크립트로 분리했는가:
    SQLite는 ALTER TABLE ADD COLUMN을 지원하지만, 인덱스나 UNIQUE 제약 변경은
    테이블 재생성이 필요합니다. 안전하게 DB 파일을 삭제 후 재생성하는 방식을 사용합니다.
    개발 환경에서만 사용할 것 — 운영 DB에는 절대 사용 금지.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_HERE, "..", "db", "concerts.db")

# DB 파일 삭제
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)
    print(f"[삭제] 기존 DB 파일 삭제: {DB_PATH}")
else:
    print(f"[건너뜀] DB 파일 없음: {DB_PATH}")

# 시드 실행
from seed import seed
seed()
