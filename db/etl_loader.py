"""
[KOPIS 원본 데이터 정제 및 DB 적재(ETL) 자동화 파이프라인]
본 스크립트는 KOPIS 크롤링/API 원본 CSV 데이터를 정제하여 관계형 데이터베이스(performance_platform.db)에 구조화하여 적재하고,
주기적인 스케줄링을 통해 외부 데이터의 상태 변화를 로컬 환경에 자동으로 동기화하는 백그라운드 데몬(Daemon) 역할을 수행합니다.

- 주요 파이프라인 기능 (Extract, Transform, Load):
  1. 결측치 전처리 (Transform): DB 제약조건 위반 방지를 위해 Pandas의 NaN 값을 Python None(DB의 NULL)으로 완전 치환.
  2. 상태 동기화 및 갱신 (UPSERT): 고유 식별자(kopis_id) 충돌 시, 신규 데이터는 삽입(INSERT)하고 기존 데이터는 상태(status), 종료일, 가격 등을 최신화(UPDATE). (REQ-06 충족)
  3. 장르 계층 구조화 (1NF): '서양음악 > 교향곡' 형태의 문자열을 파싱하여, 대/소분류의 자기 참조(Self-Referencing) 기반 장르 테이블로 분리 및 외래 키 매핑.
  4. 출연진 데이터 정규화 및 노이즈 제거: 쉼표로 묶인 '출연진' 문자열을 원자값(개별 아티스트)으로 분리하고, 불필요한 접미사(' 등', '등')를 제거.
  5. 복합 다대다(N:M) 관계 구축: 정제된 개체들을 바탕으로 공연-아티스트 간의 교차 매핑(Mapping) 테이블 적재.
  6. 무중단 스케줄러: 운영 환경에서 스크립트 실행 시, 매일 지정된 시간(02:00)에 수집 및 정제 프로세스를 자동 반복 실행.
"""

import sqlite3
import pandas as pd
import os
import time
import schedule

def run_etl_process():
    # 1. 동적 경로 설정
    base_dir = os.path.dirname(os.path.abspath(__file__))
    db_file = os.path.join(base_dir, 'performance_platform.db')
    csv_file = os.path.join(base_dir, '..', 'kopis_classic_data.csv') 

    # 2. 사전 종속성 검증 (Fail-Fast)
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
        df = df.where(pd.notnull(df), None)
    except Exception as e:
        print(f"CSV 로드 실패: {e}")
        return

    # 4. 데이터베이스 세션 연결
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")

    print("데이터 적재 및 아티스트 정제 작업을 시작합니다...")
    
    try:
        perf_count = 0
        artist_mapping_count = 0
        
        for index, row in df.iterrows():

            # [A-0] 장르 계층 구조 매핑 및 ID 추출
            raw_genre = row.get('장르')
            genre_id = None
            
            if raw_genre:
                genre_parts = [g.strip() for g in str(raw_genre).split('>')]
                
                parent_id = None
                for g_name in genre_parts:
                    if not g_name: continue
                    
                    cursor.execute("SELECT id FROM Genre WHERE name = ?", (g_name,))
                    genre_result = cursor.fetchone()
                    
                    if not genre_result:
                        cursor.execute("INSERT INTO Genre (name, parent_id) VALUES (?, ?)", (g_name, parent_id))
                        current_genre_id = cursor.lastrowid
                    else:
                        current_genre_id = genre_result[0]
                    
                    parent_id = current_genre_id
                    genre_id = current_genre_id
            
            # [A] 공연 정보 매핑 및 적재 (UPSERT 방식)
            kopis_id = row.get('공연ID')
            title = row.get('공연명')
            start_date = row.get('시작일')
            end_date = row.get('종료일')

            if not all([kopis_id, title, start_date, end_date]):
                continue

            cursor.execute("""
                INSERT INTO Performance 
                (kopis_id, title, start_date, end_date, venue, runtime, age_rating, ticket_price, genre_id, raw_program_info, poster_url, detail_image_url, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(kopis_id) DO UPDATE SET
                    status = excluded.status,
                    ticket_price = excluded.ticket_price,
                    end_date = excluded.end_date,
                    detail_image_url = excluded.detail_image_url,
                    genre_id = excluded.genre_id
            """, (
                kopis_id, title, start_date, end_date, row.get('공연장소'), 
                row.get('런타임'), row.get('관람연령'), row.get('티켓가격'), 
                genre_id, row.get('소개글_프로그램'), row.get('포스터'), row.get('상세이미지_URL'), row.get('상태')
            ))
            
            cursor.execute("SELECT id FROM Performance WHERE kopis_id = ?", (kopis_id,))
            perf_id = cursor.fetchone()[0]
            perf_count += 1

            # [B] 아티스트(출연진) 데이터 분리 및 다대다 관계 매핑
            raw_artists = row.get('출연진')
            if raw_artists:
                names = [n.strip() for n in str(raw_artists).split(',') if n.strip()]
                
                for name in names:
                    clean_name = name
                    if clean_name.endswith(' 등'):
                        clean_name = clean_name[:-2].strip()
                    elif clean_name.endswith('등'):
                        clean_name = clean_name[:-1].strip()
                    
                    if not clean_name: continue 

                    cursor.execute("INSERT OR IGNORE INTO Artist (name) VALUES (?)", (clean_name,))
                    
                    cursor.execute("SELECT id FROM Artist WHERE name = ?", (clean_name,))
                    artist_id = cursor.fetchone()[0]
                    
                    cursor.execute("""
                        INSERT OR IGNORE INTO Performance_Artist (performance_id, artist_id) 
                        VALUES (?, ?)
                    """, (perf_id, artist_id))
                    artist_mapping_count += 1

        conn.commit()
        print(f"작업 완료: 공연 {perf_count}건, 아티스트 연결 {artist_mapping_count}건 처리됨.")

    except sqlite3.Error as e:
        conn.rollback()
        print(f"DB 오류 발생: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    run_etl_process()

# [향후 스케줄링 기능 추가 예시]
# if __name__ == "__main__":
#     print("시스템 초기화: 1회차 수집 및 갱신을 즉시 실행합니다.")
#     run_etl_process()
#     
#     # REQ-06: 하루 1회 이상 자동 실행을 위한 스케줄러 등록 (매일 새벽 2시 실행)
#     schedule.every().day.at("02:00").do(run_etl_process)
#     
#     print("스케줄러가 활성화되었습니다. 매일 02:00에 데이터 자동 갱신이 수행됩니다. (종료 시 Ctrl+C)")
#     
#     # 무한 루프를 통해 스케줄러 프로세스 유지
#     try:
#         while True:
#             schedule.run_pending()
#             time.sleep(60) # 1분마다 스케줄 도래 여부 확인 (CPU 점유율 최적화)
#     except KeyboardInterrupt:
#         print("\n스케줄러가 수동으로 종료되었습니다.")