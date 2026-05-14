"""
[로컬 개발 환경 구축용 DB 초기화 스크립트]
본 스크립트는 프로젝트(ClassicHub)의 팀원들이 로컬 환경에서 동일한 데이터베이스 스키마를 구성할 수 있도록 지원하는 DDL(Data Definition Language) 실행 파일입니다.
- 용도: 물리적 SQLite DB 파일 생성 및 전체 테이블 스키마 초기화
- 실행 순서: 백엔드 개발 또는 KOPIS 데이터 적재(etl_loader.py) 이전에 반드시 가장 먼저 1회 실행되어야 합니다.
- 주의: 스크립트 실행 시 기존 DB 파일은 완전히 삭제되고 빈 스키마로 덮어씌워지므로, 로컬에서 추가한 테스트 데이터는 유실됩니다.
"""

import sqlite3
import os

def create_database():
    # 1. 파일 경로 설정
    # __file__ 속성을 사용하여 팀원마다 다를 수 있는 작업 디렉토리(OS 환경 등)와 무관하게,
    # 항상 현재 스크립트(create_db.py)가 위치한 'db' 폴더 내부에 물리적 DB 파일이 생성되도록 경로를 고정합니다.
    base_dir = os.path.dirname(os.path.abspath(__file__))
    db_file = os.path.join(base_dir, 'performance_platform.db')
    
    # 2. 기존 데이터베이스 초기화 (멱등성 보장)
    # 스크립트를 여러 번 실행하더라도 항상 오류 없이 동일한 빈 상태의 스키마를 얻을 수 있도록 기존 파일을 삭제합니다.
    if os.path.exists(db_file):
        os.remove(db_file)
        print(f"기존 '{db_file}' 파일 삭제 완료. 새로운 스키마로 초기화합니다.")

    # 3. 데이터베이스 연결 및 설정
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    
    # SQLite는 기본적으로 외래 키(Foreign Key) 제약 조건이 비활성화되어 있습니다.
    # 참조 무결성(데이터 정합성) 유지를 위해 세션 연결 시마다 외래 키 검사를 명시적으로 활성화해야 합니다.
    cursor.execute("PRAGMA foreign_keys = ON;")

    # 4. DDL(Data Definition Language) 스크립트 정의
    # 참조 무결성을 위해 참조의 대상이 되는 부모 테이블을 먼저 생성하고, 외래 키를 가지는 자식 테이블을 나중에 생성합니다.
    sql_script = """
    -- [기본 마스터 데이터 테이블] -----------------------------------------

    -- 1. 작곡가 테이블 (클래식 작품의 원작자 정보)
    CREATE TABLE Composer (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        era TEXT -- 시대 구분 (예: 바로크, 고전, 낭만 등)
    );

    -- 2. 장르 테이블 (자기 참조 계층 구조)
    -- parent_id를 통해 대분류/소분류(예: 서양음악 > 교향곡) 관계를 구현합니다.
    CREATE TABLE Genre (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        parent_id INTEGER,
        FOREIGN KEY (parent_id) REFERENCES Genre(id)
    );

    -- 3. 작품 테이블 (작곡가의 개별 곡 정보)
    CREATE TABLE Work (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        composer_id INTEGER,
        FOREIGN KEY (composer_id) REFERENCES Composer(id)
    );

    -- 4. 아티스트 테이블 (연주자, 지휘자, 단체 등)
    -- 데이터 정제(ETL) 과정을 통해 ' 등' 문자가 제거된 깨끗한 이름만 단일 레코드로 적재됩니다.
    CREATE TABLE Artist (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        role TEXT
    );

    -- [공연 핵심 데이터 테이블] --------------------------------------------

    -- 5. 공연 정보 테이블 (KOPIS 연동 데이터의 중심 테이블)
    CREATE TABLE Performance (
        id INTEGER PRIMARY KEY AUTOINCREMENT, -- 내부 시스템 고유 식별자
        kopis_id TEXT UNIQUE NOT NULL,        -- 외부 KOPIS API 고유 식별자 (예: PF288648)
        title TEXT NOT NULL,                  -- 공연명
        start_date DATE NOT NULL,             -- 시작일 (YYYY-MM-DD)
        end_date DATE NOT NULL,               -- 종료일 (YYYY-MM-DD)
        venue TEXT,                           -- 공연 장소
        region TEXT,                          -- 지역 정보
        runtime TEXT,                         -- 런타임
        age_rating TEXT,                      -- 관람 연령 (예: 만 7세 이상)
        ticket_price TEXT,                    -- 티켓 가격 정보
        genre_id INTEGER,                     -- Genre 테이블 참조(FK)
        raw_program_info TEXT,                -- 소개글 및 프로그램 원본 텍스트
        poster_url TEXT,                      -- 포스터 이미지 URL
        detail_image_url TEXT,                -- 상세 이미지 URL
        reservation_url TEXT,                 -- 예매 페이지 연동 URL
        status TEXT,                          -- 공연 상태 (공연예정, 공연완료 등)
        FOREIGN KEY (genre_id) REFERENCES Genre(id)
    );

    -- [다대다(N:M) 관계 매핑 테이블] ---------------------------------------

    -- 6. 공연-작품 매핑 테이블
    -- 하나의 공연에서 여러 곡을 연주하거나, 하나의 곡이 여러 공연에서 연주되는 관계를 해소합니다.
    CREATE TABLE Performance_Work (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        performance_id INTEGER,
        work_id INTEGER,
        order_num INTEGER, -- 프로그램 내 연주 순서 (백엔드 API 호환성 보완)
        FOREIGN KEY (performance_id) REFERENCES Performance(id),
        FOREIGN KEY (work_id) REFERENCES Work(id)
    );

    -- 7. 공연-아티스트 매핑 테이블
    -- 하나의 공연에 여러 출연진이 참여하거나, 한 명의 아티스트가 여러 공연에 출연하는 관계를 해소합니다.
    CREATE TABLE Performance_Artist (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        performance_id INTEGER,
        artist_id INTEGER,
        role TEXT, -- 아티스트의 해당 공연 내 역할 (예: 피아노, 지휘 등)
        FOREIGN KEY (performance_id) REFERENCES Performance(id),
        FOREIGN KEY (artist_id) REFERENCES Artist(id)
    );

    -- [사용자 및 서비스 테이블] --------------------------------------------

    -- 8. 사용자 정보 테이블 (Firebase Auth 시스템과 연동)
    CREATE TABLE User (
        firebase_uid TEXT PRIMARY KEY, -- Firebase에서 발급하는 고유 식별자를 PK로 활용하여 동기화
        email TEXT UNIQUE NOT NULL,
        nickname TEXT NOT NULL,
        is_active INTEGER DEFAULT 1,   -- 1: 활성, 0: 탈퇴/비활성
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    -- 9. 사용자 관심 공연(북마크) 테이블
    CREATE TABLE User_Bookmark (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        firebase_uid TEXT,
        performance_id INTEGER,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (firebase_uid) REFERENCES User(firebase_uid),
        FOREIGN KEY (performance_id) REFERENCES Performance(id),
        UNIQUE(firebase_uid, performance_id) -- 복합 제약조건: 동일 사용자가 동일 공연을 중복하여 찜하는 것 방지
    );
    """

    # 5. 스크립트 일괄 실행 및 트랜잭션 제어
    try:
        # executescript는 여러 개의 SQL 문(세미콜론으로 구분된 문자열)을 한 번의 호출로 일괄 처리합니다.
        cursor.executescript(sql_script)
        conn.commit() # DDL 변경 사항을 물리적 디스크에 최종 반영
        print("데이터베이스 및 테이블 스키마가 성공적으로 생성되었습니다.")
    except sqlite3.Error as e:
        conn.rollback() # 오류 발생 시, 실행 전 상태로 트랜잭션을 롤백하여 DB 손상 방지
        print(f"데이터베이스 스키마 생성 중 구조적 오류 발생: {e}")
    finally:
        # 작업 성공 여부와 관계없이 시스템 자원 반환을 위해 데이터베이스 연결을 안전하게 종료합니다.
        conn.close()

if __name__ == "__main__":
    create_database()