"""
[KOPIS 원본 데이터 정제 및 DB 적재(ETL) 자동화 파이프라인]
본 스크립트는 KOPIS 크롤링/API 원본 CSV 데이터를 정제하여 관계형 데이터베이스(performance_platform.db)에 구조화하여 적재하고,
주기적인 스케줄링을 통해 외부 데이터의 상태 변화를 로컬 환경에 자동으로 동기화하는 백그라운드 데몬(Daemon) 역할을 수행합니다.

- 주요 파이프라인 기능 (Extract, Transform, Load):
  1. 결측치 전처리 (Transform): DB 제약조건 위반 방지를 위해 Pandas의 NaN 값을 Python None(DB의 NULL)으로 완전 치환.
  2. 상태 동기화 및 갱신 (UPSERT): 고유 식별자(kopis_id) 충돌 시, 신규 데이터는 삽입(INSERT)하고 기존 데이터는 상태(status), 종료일, 가격 등을 최신화(UPDATE). (REQ-06 충족)
  3. 장르 계층 구조화 (1NF): '서양음악 > 교향곡' 형태의 문자열을 파싱하여, 대/소분류의 자기 참조(Self-Referencing) 기반 장르 테이블로 분리 및 외래 키 매핑.
  4. 비정형 데이터 정제 (LLM API 연동): 정제되지 않은 소개글/프로그램 텍스트를 LLM을 통해 구조화된 JSON 데이터(작곡가, 곡목)로 추출.
  5. 출연진 데이터 정규화 및 노이즈 제거: 쉼표로 묶인 '출연진' 문자열을 원자값(개별 아티스트)으로 분리하고, 불필요한 접미사(' 등', '등')를 제거.
  6. 복합 다대다(N:M) 관계 구축: 정제된 개체들을 바탕으로 공연-아티스트, 공연-작품(곡목) 간의 교차 매핑(Mapping) 테이블 적재.
  7. 무중단 스케줄러: 운영 환경에서 스크립트 실행 시, 매일 지정된 시간(02:00)에 수집 및 정제 프로세스를 자동 반복 실행.
"""

import sqlite3
import pandas as pd
import os
import json
# import requests  # (향후 외부 LLM API 호출 시 주석 해제)
import time
import schedule

def extract_program_info_via_llm(raw_text):
    """
    [LLM API 연동 모듈]
    비정형 텍스트(소개글_프로그램)를 입력받아 작곡가와 곡목을 구조화된 데이터로 반환합니다.
    (실제 운영 환경에서는 이 함수 내부에 OpenAI API 또는 로컬 모델 호출 코드를 구현해야 합니다.)
    """
    if not raw_text or len(str(raw_text)) < 10:
        return []

    # -------------------------------------------------------------------
    # [API 연동 시 구현해야 할 프롬프트 엔지니어링 예시]
    # prompt = f"""
    # 다음 텍스트에서 클래식 작곡가와 연주되는 곡목을 추출하여 아래 JSON 형식으로만 반환해.
    # [ {{"composer": "베토벤", "era": "고전", "works": ["교향곡 5번", "피아노 소나타 14번"]}} ]
    # 텍스트: {raw_text}
    # """
    # response = llm_client.chat.completions.create(..., messages=[{"role": "user", "content": prompt}])
    # return json.loads(response.choices[0].message.content)
    # -------------------------------------------------------------------

    # 테스트 및 개발을 위한 예시 반환값 (실제 연동 전까지 데이터베이스 적재 흐름을 검증하기 위함)
    # 텍스트 내에 특정 키워드가 있을 경우에만 더미 데이터를 반환하도록 임시 구성
    if "베토벤" in str(raw_text):
        return [
            {"composer": "베토벤", "era": "고전", "works": ["교향곡 5번 운명", "피아노 협주곡 5번 황제"]}
        ]
    elif "모차르트" in str(raw_text):
        return [
            {"composer": "모차르트", "era": "고전", "works": ["레퀴엠", "마술피리 서곡"]}
        ]
    
    return [] # 매칭되지 않거나 파싱 실패 시 빈 리스트 반환

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

            # [A-0] 장르 계층 구조 매핑 및 ID 추출
            # 원본 데이터의 '장르' 컬럼 값을 파싱하여 자기 참조(Self-Referencing) 계층으로 적재합니다.
            raw_genre = row.get('장르')
            genre_id = None
            
            if raw_genre:
                # 데이터가 '서양음악 > 교향곡'과 같이 구분되어 들어올 경우를 대비한 파싱 로직
                # (단일 문자열인 '서양음악(클래식)'으로 들어올 경우 최상위 대분류 1개만 생성됨)
                genre_parts = [g.strip() for g in str(raw_genre).split('>')]
                
                parent_id = None
                for g_name in genre_parts:
                    if not g_name: continue
                    
                    # 1. 현재 계층의 장르가 이미 테이블에 존재하는지 확인
                    cursor.execute("SELECT id FROM Genre WHERE name = ?", (g_name,))
                    genre_result = cursor.fetchone()
                    
                    if not genre_result:
                        # 2. 존재하지 않으면 직전 계층(parent_id)을 부모로 하여 신규 삽입
                        cursor.execute("INSERT INTO Genre (name, parent_id) VALUES (?, ?)", (g_name, parent_id))
                        current_genre_id = cursor.lastrowid
                    else:
                        current_genre_id = genre_result[0]
                    
                    # 3. 다음 하위 계층을 위해 parent_id를 갱신하고, 최종 식별자를 genre_id에 저장
                    parent_id = current_genre_id
                    genre_id = current_genre_id
            
            # [A] 공연 정보 매핑 및 적재 (UPSERT 방식 + genre_id 추가)
            kopis_id = row.get('공연ID')
            title = row.get('공연명')
            start_date = row.get('시작일')
            end_date = row.get('종료일')

            if not all([kopis_id, title, start_date, end_date]):
                continue

            # Performance 테이블 적재 및 상태 갱신 (UPSERT)
            # 앞서 A-0 단계에서 추출한 genre_id를 외래 키(FK)로 저장합니다.
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
            
            # 방금 삽입되거나 업데이트된 공연 레코드의 내부 PK(id)를 조회합니다.
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
            
            # -------------------------------------------------------------------
            # [C] LLM을 활용한 프로그램(작곡가/작품) 비정형 데이터 정제 및 다대다 매핑
            # -------------------------------------------------------------------
            raw_program = row.get('소개글_프로그램')
            structured_program = extract_program_info_via_llm(raw_program)
            
            for item in structured_program:
                composer_name = item.get("composer")
                era = item.get("era")
                works = item.get("works", [])
                
                if not composer_name:
                    continue
                    
                # 1. 작곡가(Composer) 테이블 적재
                cursor.execute("INSERT OR IGNORE INTO Composer (name, era) VALUES (?, ?)", (composer_name, era))
                cursor.execute("SELECT id FROM Composer WHERE name = ?", (composer_name,))
                composer_result = cursor.fetchone()
                if not composer_result: continue
                composer_id = composer_result[0]
                
                # 2. 작품(Work) 테이블 적재 및 매핑
                for work_idx, work_title in enumerate(works, start=1):
                    if not work_title: continue
                    
                    # Work 테이블에 해당 작곡가의 곡이 존재하는지 확인 후 삽입
                    cursor.execute("SELECT id FROM Work WHERE title = ? AND composer_id = ?", (work_title, composer_id))
                    work_result = cursor.fetchone()
                    
                    if not work_result:
                        cursor.execute("INSERT INTO Work (title, composer_id) VALUES (?, ?)", (work_title, composer_id))
                        work_id = cursor.lastrowid # 방금 삽입된 곡의 ID
                    else:
                        work_id = work_result[0]
                    
                    # 3. 공연-작품 교차(Mapping) 테이블 적재 (다대다 관계 해소 + 순서 번호 추가)
                    cursor.execute("""
                        INSERT OR IGNORE INTO Performance_Work (performance_id, work_id, order_num)
                        VALUES (?, ?, ?)
                    """, (perf_id, work_id, work_idx))

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

# [향후 스케줄링 기능 추가 예시]
# if __name__ == "__main__":
#     print("시스템 초기화: 1회차 수집 및 갱신을 즉시 실행합니다.")
#     run_etl_process()
    
#     # REQ-06: 하루 1회 이상 자동 실행을 위한 스케줄러 등록 (매일 새벽 2시 실행)
#     schedule.every().day.at("02:00").do(run_etl_process)
    
#     print("스케줄러가 활성화되었습니다. 매일 02:00에 데이터 자동 갱신이 수행됩니다. (종료 시 Ctrl+C)")
    
#     # 무한 루프를 통해 스케줄러 프로세스 유지
#     try:
#         while True:
#             schedule.run_pending()
#             time.sleep(60) # 1분마다 스케줄 도래 여부 확인 (CPU 점유율 최적화)
#     except KeyboardInterrupt:
#         print("\n스케줄러가 수동으로 종료되었습니다.")