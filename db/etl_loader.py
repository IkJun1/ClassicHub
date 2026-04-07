"""
[KOPIS 원본 데이터 정제 및 DB 적재(ETL) 스크립트]
본 스크립트는 로컬 환경에 생성된 빈 데이터베이스(performance_platform.db)에 
KOPIS 크롤링/API 원본 CSV 데이터를 정제하여 적재하는 역할을 수행합니다.

- 주요 기능 (Extract, Transform, Load):
  1. 결측치(NaN) 처리: DB 제약조건 위반을 방지하기 위해 Pandas의 NaN을 Python None(DB의 NULL)으로 변환
  2. 제1정규화(1NF): 쉼표로 묶인 '출연진' 컬럼 데이터를 원자값(개별 아티스트)으로 분리
  3. 데이터 정제: 아티스트명에 포함된 불필요한 접미사(' 등', '등') 제거
  4. 다대다(N:M) 관계 구축: Performance, Artist, Performance_Artist 테이블 간의 외래 키 매핑
"""

import sqlite3
import pandas as pd
import os

def run_etl_process():
    # 1. 동적 경로 설정
    # 스크립트 실행 위치와 무관하게 항상 정확한 파일 경로를 참조할 수 있도록 절대 경로를 계산합니다.
    base_dir = os.path.dirname(os.path.abspath(__file__))
    db_file = os.path.join(base_dir, 'performance_platform.db')
    csv_file = os.path.join(base_dir, '..', 'kopis_classic_data.csv') # 상위 디렉토리의 CSV 참조

    # 2. 사전 종속성 검증 (Fail-Fast)
    # 필요한 파일이 하나라도 없으면 즉시 프로세스를 중단하여 예기치 않은 에러를 방지합니다.
    if not os.path.exists(csv_file):
        print(f"오류: '{csv_file}' 파일이 없습니다. 원본 데이터 파일을 확인해주세요.")
        return
    if not os.path.exists(db_file):
        print("오류: DB 파일이 없습니다. db/create_db.py를 먼저 1회 실행하여 스키마를 초기화하세요.")
        return

    # 3. 데이터 로드 (Extract) 및 결측치 전처리 (Transform)
    print("CSV 데이터를 읽고 정제하는 중...")
    try:
        df = pd.read_csv(csv_file)
        # Pandas는 빈 칸을 float 형태의 NaN으로 읽어옵니다.
        # 이를 그대로 SQLite에 넣으면 타입 에러나 텍스트 'NaN'으로 들어갈 수 있으므로, 
        # Python의 None으로 치환하여 DB에서 완벽한 NULL 값으로 인식하도록 처리합니다.
        df = df.where(pd.notnull(df), None)
    except Exception as e:
        print(f"CSV 로드 실패: {e}")
        return

    # 4. 데이터베이스 세션 연결
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    # 외래 키(Foreign Key) 참조 무결성 검사 활성화
    cursor.execute("PRAGMA foreign_keys = ON;")

    print("데이터 적재 및 아티스트 정제 작업을 시작합니다...")
    
    try:
        perf_count = 0
        artist_mapping_count = 0
        
        # DataFrame의 각 행을 순회하며 데이터베이스에 적재 (Load)
        for index, row in df.iterrows():
            
            # [A] 공연 정보 매핑 및 적재
            kopis_id = row.get('공연ID')
            title = row.get('공연명')
            start_date = row.get('시작일')
            end_date = row.get('종료일')

            # 스키마 상 NOT NULL로 지정된 필수 핵심 데이터가 누락된 행은 적재하지 않고 건너뜁니다.
            if not all([kopis_id, title, start_date, end_date]):
                continue

            # Performance 테이블 삽입
            # INSERT OR IGNORE: 이미 동일한 kopis_id(UNIQUE 제약조건)가 존재하면 에러 없이 해당 쿼리를 무시합니다. (멱등성 확보)
            cursor.execute("""
                INSERT OR IGNORE INTO Performance 
                (kopis_id, title, start_date, end_date, venue, runtime, age_rating, ticket_price, raw_program_info, poster_url, detail_image_url, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                kopis_id, title, start_date, end_date, row.get('공연장소'), 
                row.get('런타임'), row.get('관람연령'), row.get('티켓가격'), 
                row.get('소개글_프로그램'), row.get('포스터'), row.get('상세이미지_URL'), row.get('상태')
            ))
            
            # 방금 삽입된(또는 무시되어 이미 존재하는) 공연 레코드의 내부 PK(id)를 조회합니다.
            # 이 ID는 이후 매핑 테이블(Performance_Artist)에서 외래 키로 사용됩니다.
            cursor.execute("SELECT id FROM Performance WHERE kopis_id = ?", (kopis_id,))
            perf_id = cursor.fetchone()[0]
            perf_count += 1

            # [B] 아티스트(출연진) 데이터 분리 및 다대다 관계 매핑
            raw_artists = row.get('출연진')
            if raw_artists:
                # 1. 다중 값 분리 (제1정규화): "A, B, C" 형태의 문자열을 리스트 ['A', 'B', 'C']로 분할
                names = [n.strip() for n in str(raw_artists).split(',') if n.strip()]
                
                for name in names:
                    # 2. 접미사 정제 로직 ('길병민 등' -> '길병민')
                    # endswith를 사용하여 이름 중간에 들어가는 '등' 글자(예: 백건우 등)가 손상되는 것을 방지합니다.
                    clean_name = name
                    if clean_name.endswith(' 등'):
                        clean_name = clean_name[:-2].strip()
                    elif clean_name.endswith('등'):
                        clean_name = clean_name[:-1].strip()
                    
                    if not clean_name: continue # 정제 후 값이 비어있으면 스킵

                    # 3. Artist 단일 테이블에 적재
                    # 정제된 이름이 이미 테이블에 존재하면(UNIQUE 제약) 에러 없이 넘어갑니다.
                    cursor.execute("INSERT OR IGNORE INTO Artist (name) VALUES (?)", (clean_name,))
                    
                    # 4. 방금 삽입 또는 조회된 아티스트의 내부 PK(id) 확보
                    cursor.execute("SELECT id FROM Artist WHERE name = ?", (clean_name,))
                    artist_id = cursor.fetchone()[0]
                    
                    # 5. 공연-아티스트 교차(Mapping) 테이블 적재
                    # 특정 공연(perf_id)에 특정 아티스트(artist_id)가 출연한다는 관계를 기록합니다.
                    cursor.execute("""
                        INSERT OR IGNORE INTO Performance_Artist (performance_id, artist_id) 
                        VALUES (?, ?)
                    """, (perf_id, artist_id))
                    artist_mapping_count += 1

        # 모든 반복문이 성공적으로 끝난 후, 메모리 상의 변경 사항을 물리적 DB 파일에 확정(Commit)합니다.
        conn.commit()
        print(f"작업 완료: 공연 {perf_count}건, 아티스트 연결 {artist_mapping_count}건 처리됨.")

    except sqlite3.Error as e:
        # 데이터베이스 작업 중 하나라도 오류가 발생하면, 무결성을 위해 작업 시작 전 상태로 되돌립니다(Rollback).
        conn.rollback()
        print(f"DB 오류 발생: {e}")
    finally:
        # 정상 종료 및 에러 발생 여부와 상관없이 항상 DB 연결을 안전하게 해제합니다.
        conn.close()

if __name__ == "__main__":
    run_etl_process()