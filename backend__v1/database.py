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
import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# ── DB 파일 경로 ─────────────────────────────────────────────────────────────
# 이 파일(app/) 기준 ../db/concerts.db 에 저장
# app/ 디렉터리에서 실행해도, backend_v1/ 루트에서 실행해도 동일 경로 참조
DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "db")
os.makedirs(DB_DIR, exist_ok=True)  # db/ 디렉터리 없으면 자동 생성

SQLALCHEMY_DATABASE_URL = f"sqlite:///{os.path.join(DB_DIR, 'concerts.db')}"


# ── 엔진 생성 ────────────────────────────────────────────────────────────────
# SQLite는 기본적으로 단일 스레드용이므로 check_same_thread=False 설정
# FastAPI는 멀티스레드 환경이므로 이 옵션이 반드시 필요
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)


# ── SQLite 외래키 제약 활성화 ─────────────────────────────────────────────────
# SQLite는 기본적으로 FK 제약이 비활성화되어 있음
# 이를 켜야 CASCADE DELETE 등이 정상 동작함
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


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
