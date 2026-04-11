"""
models.py
SQLAlchemy ORM 모델 정의

DB 연관 구조:
  Composer (작곡가)
    └─ 1:N ─ Work (곡)
                └─ N:M (performance_work) ─ Performance (공연)
                                                ├─ N:1 ─ Genre (장르)
                                                ├─ 1:N ─ PerformanceDate (공연 날짜)
                                                └─ 1:N ─ Performer (연주자)
  Artist (아티스트) — 독립 엔티티 (지휘자·솔리스트 등)

왜 classic-api와 구조가 거의 같은가:
- classic-api의 설계 검토 결과 ORM 구조 자체는 올바름
- 이 파일에서 추가된 것: Performance.poster_url, Composer.era
  (프론트 연동에 필요한 누락 필드 보완)
"""
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Table
from sqlalchemy.orm import relationship
from database import Base


# ─────────────────────────────────────────────────────────────────────────────
# Performance ↔ Work  다대다(N:M) 중간 테이블
# 왜 별도 Core Table로 정의하는가:
#   order_num(프로그램 순서) 컬럼이 필요한데, ORM relationship만으로는
#   중간 테이블에 추가 컬럼을 넣기 어려움. Core Table 방식이 더 명확함.
# ─────────────────────────────────────────────────────────────────────────────
performance_work_table = Table(
    "performance_work",
    Base.metadata,
    Column(
        "performance_id",
        Integer,
        ForeignKey("performance.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "work_id",
        Integer,
        ForeignKey("work.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("order_num", Integer, nullable=True),  # 프로그램 내 연주 순서
)


# ─────────────────────────────────────────────────────────────────────────────
# Genre — 장르 (자기 참조로 계층 구조 표현)
# 왜 계층 구조인가:
#   "교향곡" 같은 대분류 아래 "합창 교향곡" 같은 소분류를 표현하기 위해
#   self-referencing FK 사용. 프론트의 장르 탭 UI를 지원.
# ─────────────────────────────────────────────────────────────────────────────
class Genre(Base):
    __tablename__ = "genre"

    id        = Column(Integer, primary_key=True, index=True)
    name      = Column(String,  nullable=False)
    name_en   = Column(String,  nullable=True)   # 장르 영문 명칭 (예: Symphony)
    parent_id = Column(Integer, ForeignKey("genre.id"), nullable=True)

    children = relationship(
        "Genre",
        back_populates="parent",
        foreign_keys=[parent_id],
    )
    parent = relationship(
        "Genre",
        back_populates="children",
        foreign_keys=[parent_id],
        remote_side=[id],
    )
    performances = relationship("Performance", back_populates="genre")


# ─────────────────────────────────────────────────────────────────────────────
# Composer — 작곡가
# 추가된 필드: era (바로크/고전/낭만/근현대)
# 왜 era를 추가했는가:
#   작곡가.html이 ?era=바로크 처럼 URL 파라미터로 시대 필터를 사용함.
#   era 필드 없이는 /api/composers?era=낭만 필터가 동작 불가.
# ─────────────────────────────────────────────────────────────────────────────
class Composer(Base):
    __tablename__ = "composer"

    id         = Column(Integer, primary_key=True, index=True)
    name       = Column(String,  nullable=False)       # 영문 이름 (예: Beethoven)
    name_ko    = Column(String,  nullable=True)        # 한국어 이름 (예: 베토벤)
    era        = Column(String,  nullable=True)        # 시대: 바로크/고전/낭만/근현대
    featured   = Column(Boolean, default=False)        # UI 빠른 버튼 표시 여부
    birth_year = Column(Integer, nullable=True)        # 출생 연도
    death_year = Column(Integer, nullable=True)        # 사망 연도

    works = relationship("Work", back_populates="composer")


# ─────────────────────────────────────────────────────────────────────────────
# Work — 곡(작품)
# ─────────────────────────────────────────────────────────────────────────────
class Work(Base):
    __tablename__ = "work"

    id          = Column(Integer, primary_key=True, index=True)
    title       = Column(String,  nullable=False)
    composer_id = Column(Integer, ForeignKey("composer.id"), nullable=True)
    genre_id    = Column(Integer, ForeignKey("genre.id"),    nullable=True)

    composer     = relationship("Composer", back_populates="works")
    genre        = relationship("Genre")
    performances = relationship(
        "Performance",
        secondary=performance_work_table,
        back_populates="works",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Performance — 공연
# 추가된 필드: poster_url
# 왜 poster_url을 추가했는가:
#   main.html D-Day 섹션과 공연 카드가 KOPIS 포스터 이미지를 표시함.
#   poster_url 없이는 이미지 없는 회색 박스만 보임.
# ─────────────────────────────────────────────────────────────────────────────
class Performance(Base):
    __tablename__ = "performance"

    id          = Column(Integer, primary_key=True, index=True)
    kopis_id    = Column(String,  nullable=True, index=True)  # KOPIS 원본 공연 ID (PF288193 등)
                                                               # 크롤러 중복 방지에 사용. 수동 입력 데이터는 NULL 허용.
    title       = Column(String,  nullable=False)
    venue       = Column(String,  nullable=True)          # 공연 장소
    poster_url  = Column(String,  nullable=True)          # 포스터 이미지 URL (KOPIS 등)
    source_url  = Column(String,  nullable=True)          # 원본 공연 페이지 URL
    ticket_url  = Column(String,  nullable=True)          # 예매 페이지 URL
    genre_id    = Column(Integer, ForeignKey("genre.id"), nullable=True)
    start_date  = Column(String,  nullable=True)          # YYYY-MM-DD (공연 시작일)
    end_date    = Column(String,  nullable=True)          # YYYY-MM-DD (공연 종료일)
    status      = Column(String,  nullable=True, default="upcoming")  # upcoming / past
    created_at  = Column(String,  nullable=True, server_default="CURRENT_TIMESTAMP")

    genre      = relationship("Genre", back_populates="performances")
    works      = relationship(
        "Work",
        secondary=performance_work_table,
        back_populates="performances",
    )
    dates      = relationship(
        "PerformanceDate",
        back_populates="performance",
        cascade="all, delete-orphan",
        order_by="PerformanceDate.date",
    )
    performers = relationship(
        "Performer",
        back_populates="performance",
        cascade="all, delete-orphan",
    )


# ─────────────────────────────────────────────────────────────────────────────
# PerformanceDate — 공연 날짜 (1 공연 : N 날짜)
# 왜 별도 테이블로 분리했는가:
#   동일 공연이 여러 날짜에 열릴 수 있음 (예: 오페라 3회 공연).
#   Performance 본 테이블에 날짜를 묻으면 정규화 위반.
# ─────────────────────────────────────────────────────────────────────────────
class PerformanceDate(Base):
    __tablename__ = "performance_date"

    id             = Column(Integer, primary_key=True, index=True)
    performance_id = Column(
        Integer,
        ForeignKey("performance.id", ondelete="CASCADE"),
        nullable=False,
    )
    date = Column(String, nullable=False)   # YYYY-MM-DD

    performance = relationship("Performance", back_populates="dates")


# ─────────────────────────────────────────────────────────────────────────────
# Performer — 연주자 (공연에 소속)
# ─────────────────────────────────────────────────────────────────────────────
class Performer(Base):
    __tablename__ = "performer"

    id             = Column(Integer, primary_key=True, index=True)
    name           = Column(String,  nullable=False)
    performance_id = Column(
        Integer,
        ForeignKey("performance.id", ondelete="CASCADE"),
        nullable=False,
    )

    performance = relationship("Performance", back_populates="performers")


# ─────────────────────────────────────────────────────────────────────────────
# Artist — 아티스트 (지휘자·솔리스트·오케스트라 등)
# 왜 Performer와 별도로 존재하는가:
#   Performer는 특정 공연에 귀속된 연주자 (공연마다 새로 기록됨).
#   Artist는 독립 프로필 개념으로 아티스트.html 페이지에서 역할별 검색에 사용.
# ─────────────────────────────────────────────────────────────────────────────
class Artist(Base):
    __tablename__ = "artist"

    id   = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)   # 이름 (예: 김지현)
    role = Column(String, nullable=True)    # 역할 (예: 지휘자)
