"""
database.py
SQLAlchemy 엔진·세션·베이스 클래스 설정

왜 SQLite를 선택했는가:
- 팀 과제 기준으로 별도 DB 서버 없이 파일 하나로 동작
- 추후 PostgreSQL 전환 시 DATABASE_URL 한 줄만 교체하면 됨

PostgreSQL로 전환 시:
    SQLALCHEMY_DATABASE_URL = "postgresql://user:password@host:port/dbname"
    create_engine() 에서 connect_args 제거
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

import os
from dotenv import load_dotenv

# 프로젝트 루트의 .env 경로를 동적으로 계산하여 로드
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(BASE_DIR, '.env')
load_dotenv(dotenv_path=ENV_PATH)

# ── DB 설정 ─────────────────────────────────────────────────────────────
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")

# 방어 로직: postgres:// 로 시작하면 postgresql:// 로 치환
if SQLALCHEMY_DATABASE_URL and SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgres://", "postgresql://", 1)

# ── 엔진 생성 ────────────────────────────────────────────────────────────────
# PostgreSQL 연결 (SQLite 전용인 check_same_thread=False 제거)
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
)


# ── 세션 팩토리 ──────────────────────────────────────────────────────────────
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ── 베이스 클래스 ─────────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    """모든 SQLAlchemy ORM 모델이 상속받는 베이스 클래스"""
    pass


# ── FastAPI 의존성 주입용 DB 세션 제공자 ─────────────────────────────────────
def get_db():
    """
    요청마다 새 세션을 생성하고 응답 후 자동으로 닫는다.
    FastAPI의 Depends()와 함께 사용.

    왜 yield를 쓰는가:
    - try/finally 패턴으로 예외가 발생해도 세션이 반드시 닫힘
    - 연결 누수(connection leak)를 방지
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
