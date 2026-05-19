"""
models.py
SQLAlchemy ORM 모델 정의

이 파일은 DB를 생성하는 용도가 아니라,
이미 존재하는 performance_platform.db 테이블을 ORM으로 매핑하는 용도로만 사용한다.
DB 스키마 기준: ERD_v2 (PascalCase 테이블명)

연관 구조:
  Composer (작곡가)
    └─ 1:N ─ Work (곡)
                └─ N:M (Performance_Work) ─ Performance (공연)
                                                ├─ N:1 ─ Genre (장르, 자기참조 계층)
                                                └─ N:M (Performance_Artist) ─ Artist (아티스트)
  User (사용자)
    └─ 1:N ─ User_Bookmark (찜한 공연)
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Table
from sqlalchemy.orm import relationship
from database import Base


# ─────────────────────────────────────────────────────────────────────────────
# Performance_Artist  다대다(N:M) 중간 테이블 (Core Table)
# id 컬럼이 있는 일반 테이블이므로 Core Table로 정의.
# 추가 컬럼이 없으므로 ORM 모델 대신 secondary 테이블로 사용.
# ─────────────────────────────────────────────────────────────────────────────
class PerformanceArtist(Base):
    __tablename__ = "Performance_Artist"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    performance_id = Column(Integer, ForeignKey("Performance.id"), nullable=False)
    artist_id      = Column(Integer, ForeignKey("Artist.id"), nullable=False)
    role           = Column(String,  nullable=True)

    performance = relationship("Performance", back_populates="performance_artists")
    artist      = relationship("Artist", back_populates="performance_artists")


# ─────────────────────────────────────────────────────────────────────────────
# Genre — 장르 (자기 참조로 계층 구조 표현)
# ─────────────────────────────────────────────────────────────────────────────
class Genre(Base):
    __tablename__ = "Genre"

    id        = Column(Integer, primary_key=True, index=True)
    name      = Column(String,  nullable=False, unique=True)
    parent_id = Column(Integer, ForeignKey("Genre.id"), nullable=True)

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
# ERD_v2 기준: id, name, era 만 사용
# ─────────────────────────────────────────────────────────────────────────────
class Composer(Base):
    __tablename__ = "Composer"

    id   = Column(Integer, primary_key=True, index=True)
    name = Column(String,  nullable=False, unique=True)
    era  = Column(String,  nullable=True)

    works = relationship("Work", back_populates="composer")


# ─────────────────────────────────────────────────────────────────────────────
# Work — 곡(작품)
# ─────────────────────────────────────────────────────────────────────────────
class Work(Base):
    __tablename__ = "Work"

    id          = Column(Integer, primary_key=True, index=True)
    title       = Column(String,  nullable=False)
    composer_id = Column(Integer, ForeignKey("Composer.id"), nullable=True)

    composer          = relationship("Composer", back_populates="works")
    performance_works = relationship("PerformanceWork", back_populates="work")


# ─────────────────────────────────────────────────────────────────────────────
# Artist — 아티스트 (지휘자·솔리스트·오케스트라 등)
# ─────────────────────────────────────────────────────────────────────────────
class Artist(Base):
    __tablename__ = "Artist"

    id   = Column(Integer, primary_key=True, index=True)
    name = Column(String,  nullable=True, unique=True)
    role = Column(String,  nullable=True)

    performance_artists = relationship(
        "PerformanceArtist",
        back_populates="artist",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Performance — 공연
# ERD_v2 기준 컬럼: id, kopis_id, title, start_date, end_date, venue, region,
#   runtime, age_rating, ticket_price, genre_id, raw_program_info,
#   poster_url, detail_image_url, reservation_url, status
# ─────────────────────────────────────────────────────────────────────────────
class Performance(Base):
    __tablename__ = "Performance"

    id               = Column(Integer, primary_key=True, index=True)
    kopis_id         = Column(String,  nullable=True,  unique=True, index=True)
    title            = Column(String,  nullable=False)
    start_date       = Column(String,  nullable=True)
    end_date         = Column(String,  nullable=True)
    venue            = Column(String,  nullable=True)
    region           = Column(String,  nullable=True)
    runtime          = Column(String,  nullable=True)
    age_rating       = Column(String,  nullable=True)
    ticket_price     = Column(String,  nullable=True)
    genre_id         = Column(Integer, ForeignKey("Genre.id"), nullable=True)
    raw_program_info = Column(String,  nullable=True)
    poster_url       = Column(String,  nullable=True)
    detail_image_url = Column(String,  nullable=True)
    reservation_url  = Column(String,  nullable=True)
    # ETL이 KOPIS 원문 한국어 값을 저장하므로 기본값도 한국어 기준으로 맞춤
    status           = Column(String,  nullable=True, default="공연예정")

    genre             = relationship("Genre", back_populates="performances")
    performance_artists = relationship(
        "PerformanceArtist",
        back_populates="performance",
    )
    performance_works = relationship(
        "PerformanceWork",
        back_populates="performance",
    )


# ─────────────────────────────────────────────────────────────────────────────
# PerformanceWork — 공연-연주곡 매핑 (N:M 중간 테이블 ORM 모델)
# order_num 컬럼 접근이 필요하므로 Core Table 대신 ORM 모델로 정의.
# ─────────────────────────────────────────────────────────────────────────────
class PerformanceWork(Base):
    __tablename__ = "Performance_Work"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    performance_id = Column(Integer, ForeignKey("Performance.id"), nullable=False)
    work_id        = Column(Integer, ForeignKey("Work.id"), nullable=False)
    order_num      = Column(Integer, nullable=True)

    performance = relationship("Performance", back_populates="performance_works")
    work        = relationship("Work", back_populates="performance_works")


# ─────────────────────────────────────────────────────────────────────────────
# User — 사용자 정보 (Firebase Auth 연동)
# ─────────────────────────────────────────────────────────────────────────────
class User(Base):
    __tablename__ = "User"

    firebase_uid = Column(String,   primary_key=True)
    email        = Column(String,   nullable=False, unique=True)
    nickname     = Column(String,   nullable=False)
    is_active    = Column(Integer,  default=1)
    created_at   = Column(DateTime, nullable=True)
    updated_at   = Column(DateTime, nullable=True)

    bookmarks = relationship("UserBookmark", back_populates="user")


# ─────────────────────────────────────────────────────────────────────────────
# UserBookmark — 사용자 관심 공연 (찜하기)
# ─────────────────────────────────────────────────────────────────────────────
class UserBookmark(Base):
    __tablename__ = "User_Bookmark"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    firebase_uid   = Column(String,  ForeignKey("User.firebase_uid"), nullable=False)
    performance_id = Column(Integer, ForeignKey("Performance.id"),    nullable=False)
    created_at     = Column(DateTime, nullable=True)

    user        = relationship("User",        back_populates="bookmarks")
    performance = relationship("Performance")
