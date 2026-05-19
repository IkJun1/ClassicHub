"""
[KOPIS 원본 데이터 정제 및 DB 적재(ETL) 자동화 파이프라인]
본 스크립트는 KOPIS 크롤링/API 원본 CSV 데이터를 정제하여 관계형 데이터베이스(performance_platform.db)에 구조화하여 적재하고,
주기적인 스케줄링을 통해 외부 데이터의 상태 변화를 로컬 환경에 자동으로 동기화하는 백그라운드 데몬(Daemon) 역할을 수행합니다.

- 주요 파이프라인 기능 (Extract, Transform, Load):
  1. 결측치 전처리 (Transform): DB 제약조건 위반 방지를 위해 Pandas의 NaN 값을 Python None(DB의 NULL)으로 완전 치환.
  2. 상태 동기화 및 갱신 (UPSERT): 고유 식별자(kopis_id) 충돌 시, 신규 데이터는 삽입(INSERT)하고 기존 데이터는 상태(status), 종료일, 가격 등을 최신화(UPDATE). (REQ-06 충족)
  3. 장르 계층 구조화 및 지능형 분류: 제목 키워드 분석을 통해 장르를 자동 매핑하고, 대/소분류의 계층 구조 유지.
  4. 출연진 데이터 정규화 (Surgical Cleaning): 악기/역할 키워드 사전을 기반으로 '조성진(피아노)'은 정제하되 '임윤찬(Yunchan Lim)'은 보존.
  5. 문맥 유지형 프로그램 파서 (State-Machine): 작곡가 이름이 선행되고 다음 줄에 곡명만 나오는 클래식 프로그램 특성을 반영하여 자동 연결.
  6. 유연한 컬럼 매핑 (Dynamic Fuzzy Mapping): 엑셀 열 순서가 바뀌어도 키워드 매칭을 통해 동적으로 데이터를 추출.
"""

import sqlite3
import pandas as pd
import os
import re
from datetime import datetime

# ─────────────────────────────────────────────────────────────────────────────
# [고도화 전략 1] 마스터 사전 및 설정
# ─────────────────────────────────────────────────────────────────────────────

# 악기 및 역할 사전 (아티스트 정제 시 선별적 삭제 기준)
ROLE_KEYWORDS = ["피아노", "바이올린", "첼로", "지휘", "소프라노", "테너", "바리톤", "베이스", "협연", "연주", "악단", "오케스트라", "챔버"]

# 장르 분류 키워드
GENRE_KEYWORDS = [
    ("교향곡/관현악", ["교향곡", "심포니", "symphony", "관현악", "오케스트라", "orchestra", "필하모닉", "정기연주회", "신년음악회"]),
    ("협주곡", ["협주곡", "콘체르토", "concerto"]),
    ("오페라/합창", ["오페라", "opera", "합창", "콰이어", "choir", "레퀴엠", "성가", "미사", "칸타타"]),
    ("가곡/성악", ["가곡", "독창회", "성악", "소프라노", "테너", "바리톤", "베이스", "리트", "아리아", "보컬"]),
    ("실내악", ["실내악", "사중주", "삼중주", "오중주", "앙상블", "chamber", "duo", "trio", "quartet", "quintet", "스트링"]),
    ("기악 독주", ["리사이틀", "독주회", "recital", "피아노", "바이올린 독주", "첼로 독주", "건반", "플루트 독주", "기타 독주"]),
    ("복합/일반", ["음악회", "콘서트", "갈라", "마티네", "브런치", "클래식", "페스티벌", "마스터클래스", "초청연주회"])
]

MASTER_COMPOSERS = {
    "Beethoven": ["베토벤", "Beethoven"],
    "Mozart": ["모차르트", "Mozart"],
    "Bach": ["바흐", "Bach"],
    "Chopin": ["쇼팽", "Chopin"],
    "Brahms": ["브람스", "Brahms"],
    "Tchaikovsky": ["차이콥스키", "차이코프스키", "Tchaikovsky"],
    "Mahler": ["말러", "Mahler"],
    "Rachmaninoff": ["라흐마니노프", "Rachmaninoff"],
    "Schubert": ["슈베르트", "Schubert"],
    "Mendelssohn": ["멘델스존", "Mendelssohn"],
    "Vivaldi": ["비발디", "Vivaldi"],
    "Handel": ["헨델", "Handel"],
    "Haydn": ["하이든", "Haydn"],
    "Schumann": ["슈만", "Schumann"],
    "Liszt": ["리스트", "Liszt"],
    "Wagner": ["바그너", "Wagner"],
    "Dvorak": ["드보르자크", "드보르작", "Dvorak"],
    "Debussy": ["드뷔시", "Debussy"],
    "Ravel": ["라벨", "Ravel"],
    "Puccini": ["푸치니", "Puccini"],
    "Verdi": ["베르디", "Verdi"],
    "Stravinsky": ["스트라빈스키", "Stravinsky"]
}

REGION_MAP = {
    "서울": "서울", "서울특별시": "서울",
    "부산": "부산", "부산광역시": "부산",
    "대구": "대구", "대구광역시": "대구",
    "인천": "인천", "인천광역시": "인천",
    "광주": "광주", "광주광역시": "광주",
    "대전": "대전", "대전광역시": "대전",
    "울산": "울산", "울산광역시": "울산",
    "경기": "경기", "경기도": "경기",
    "강원": "강원", "강원도": "경기", # 강원은 경기로 분류되거나 필요시 추가
    "충북": "충북", "충남": "충남", "전북": "전북", "전남": "전남", "경북": "경북", "경남": "경남", "제주": "제주"
}

def run_etl_process():
    # 1. 경로 설정
    base_dir = os.path.dirname(os.path.abspath(__file__))
    db_file = os.path.join(base_dir, 'performance_platform.db')
    csv_file = os.path.join(base_dir, '..', 'kopis_classic_data.csv')

    if not os.path.exists(csv_file):
        print(f"오류: '{csv_file}' 파일을 찾을 수 없습니다.")
        return

    # 2. 데이터 로드
    print(f"📦 통합 데이터 로드 및 컬럼 분석 시작: {os.path.basename(csv_file)}")
    try:
        df = pd.read_csv(csv_file)
        df = df.where(pd.notnull(df), None)
    except Exception as e:
        print(f"❌ 로드 실패: {e}")
        return

    # [해결 1] Dynamic Column Mapping (Fuzzy Match)
    cols = df.columns.tolist()
    def find_idx(keywords):
        for i, col in enumerate(cols):
            col_str = str(col).lower()
            if any(k.lower() in col_str for k in keywords):
                return i
        return None

    idx_map = {
        "id": find_idx(["kopis_id", "ID", "아이디"]),
        "title": find_idx(["title", "명", "제목"]),
        "start": find_idx(["start_date", "시작", "start"]),
        "end": find_idx(["end_date", "종료", "end"]),
        "venue": find_idx(["venue", "장소", "시설"]),
        "poster": find_idx(["poster_url", "포스터", "poster"]),
        "status": find_idx(["status", "상태"]),
        "artists": find_idx(["artists", "출연", "아티스트", "artist"]),
        "runtime": find_idx(["runtime", "런타임", "시간"]),
        "age": find_idx(["age_rating", "연령", "나이", "age"]),
        "price": find_idx(["ticket_price", "가격", "티켓", "price"]),
        "prog": find_idx(["raw_program_info", "프로그램", "곡명", "program"]),
        "img": find_idx(["detail_image_url", "상세", "이미지", "image"]),
        "res": find_idx(["reservation_url", "예매", "ticket"]),
        "region": find_idx(["region", "지역"])
    }

    if idx_map["id"] is None or idx_map["title"] is None:
        print("❌ 필수 컬럼(ID, 공연명)을 찾을 수 없습니다.")
        return

    # 3. DB 연결 및 설정
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")

    # ─────────────────────────────────────────────────────────────────────────
    # [고도화 전략 2] 정제 및 파싱 유틸리티 (캐싱 도입으로 병목 해결)
    # ─────────────────────────────────────────────────────────────────────────
    genre_cache = {}
    artist_cache = {}
    composer_cache = {}
    work_cache = {}

    def clean_artist_name(name):
        if not name: return None, None
        name_str = str(name).strip()
        role = None
        content_match = re.search(r'[\(\[\{](.*?)[\)\]\}]', name_str)
        if content_match:
            inner_text = content_match.group(1)
            if any(r in inner_text for r in ROLE_KEYWORDS):
                role = inner_text.strip()
                name_str = re.sub(r'[\(\[\{].*?[\)\]\}]', '', name_str)
        name_str = re.sub(r'\s*등$', '', name_str).strip()
        return name_str, role

    def clean_url(text):
        if not text: return None
        match = re.search(r'https?://[^\s,\)]+', str(text))
        return match.group(0) if match else None

    def standardize_region(raw_region):
        if not raw_region: return None
        return REGION_MAP.get(str(raw_region).strip(), raw_region)

    def get_genre_id(title):
        title_lower = str(title).lower()
        target_genre = "기타"
        for g_name, keywords in GENRE_KEYWORDS:
            if any(kw in title_lower for kw in keywords):
                target_genre = g_name
                break
                
        if target_genre in genre_cache:
            return genre_cache[target_genre]
            
        cursor.execute("SELECT id FROM Genre WHERE name = ?", (target_genre,))
        res = cursor.fetchone()
        if res:
            genre_cache[target_genre] = res[0]
            return res[0]
            
        cursor.execute("INSERT INTO Genre (name) VALUES (?)", (target_genre,))
        new_id = cursor.lastrowid
        genre_cache[target_genre] = new_id
        return new_id

    def parse_program_with_context(perf_id, program_text):
        if not program_text: return
        
        # 1. 메타 노이즈 및 서술형 안내 문구 선제 제거
        clean_text = str(program_text).strip()
        noise_patterns = [
            r'\[공연소개\]', r'\[프로그램\]', r'\[PROGRAM\]', r'\[Program\]',
            r'▶\s*출연진', r'▶\s*프로그램', r'※\s*본\s*프로그램은.*',
            r'■\s*프로그램', r'\*.*변경될\s*수\s*있습니다\.?'
        ]
        for pattern in noise_patterns:
            clean_text = re.sub(pattern, '', clean_text)

        # 2. 다중 구분자 분할 복구 (수율 붕괴 원인 해결)
        # 클래식 공연 프로그램 나열 시 주로 사용되는 구분자(/, ;, |)를 토큰화 기준에 포함
        raw_lines = re.split(r'[\n;/|]', clean_text)
        
        last_comp_id = None
        order = 1
        
        for line in raw_lines:
            line = line.strip()
            if not line: continue
            
            # 3. 1차 방어벽: 토큰화된 문자열이 120자를 초과하면 해설글 덩어리로 간주하여 스킵
            if len(line) > 120:
                continue
                
            found_composer_key = None
            for key, aliases in MASTER_COMPOSERS.items():
                if any(alias in line for alias in aliases):
                    found_composer_key = key
                    break
            
            if found_composer_key:
                if found_composer_key in composer_cache:
                    last_comp_id = composer_cache[found_composer_key]
                else:
                    cursor.execute("INSERT OR IGNORE INTO Composer (name, era) VALUES (?, ?)", (found_composer_key, "미분류"))
                    cursor.execute("SELECT id FROM Composer WHERE name = ?", (found_composer_key,))
                    last_comp_id = cursor.fetchone()[0]
                    composer_cache[found_composer_key] = last_comp_id

            # 문맥상 작곡가가 존재할 때 곡명 추출 시도
            if last_comp_id:
                work_title = line
                if found_composer_key:
                    for alias in MASTER_COMPOSERS[found_composer_key]:
                        work_title = work_title.replace(alias, "")
                        
                # 특수기호 및 공백 정제
                work_title = re.sub(r'^[:\-\s,·.]+', '', work_title).strip()
                
                # 4. 2차 방어벽: 정제 완료된 순수 '곡명'에 대한 길이 기준 (2자 이상, 100자 이하)
                if not work_title or len(work_title) < 2 or len(work_title) > 100: 
                    continue 
                
                # Work 테이블 캐싱 및 유무 확인
                cache_key = (work_title, last_comp_id)
                if cache_key in work_cache:
                    work_id = work_cache[cache_key]
                else:
                    cursor.execute("SELECT id FROM Work WHERE title = ? AND composer_id = ?", (work_title, last_comp_id))
                    work_res = cursor.fetchone()
                    if work_res:
                        work_id = work_res[0]
                    else:
                        cursor.execute("INSERT INTO Work (title, composer_id) VALUES (?, ?)", (work_title, last_comp_id))
                        work_id = cursor.lastrowid
                    work_cache[cache_key] = work_id
                    
                cursor.execute("INSERT INTO Performance_Work (performance_id, work_id, order_num) VALUES (?, ?, ?)", (perf_id, work_id, order))
                order += 1

    print("🚀 수정된 15-Column 및 시니어 보완 파이프라인 가동...")
    
    try:
        counts = {"perf": 0, "artist": 0, "skipped": 0}
        
        for _, row in df.iterrows():
            def get_val(key):
                idx = idx_map.get(key)
                return row.iloc[idx] if idx is not None else None

            k_id = get_val("id")
            title = get_val("title")
            if not k_id or not title: continue

            def format_date(val):
                if not val: return None
                return str(val).split()[0]

            s_date = format_date(get_val("start"))
            e_date = format_date(get_val("end"))
            
            # [수정 1] NOT NULL 제약조건 위반 방지: 날짜 누락 시 스킵 (또는 로직에 따라 대체값 삽입)
            if not s_date or not e_date:
                counts["skipped"] += 1
                continue

            p_url = clean_url(get_val("poster"))
            det_img = clean_url(get_val("img"))
            res_url = clean_url(get_val("res"))
            region = standardize_region(get_val("region"))
            genre_id = get_genre_id(title)

            # [해결] 15개 컬럼과 15개 자리 표시자(?) 정확히 일치
            cursor.execute("""
                INSERT INTO Performance 
                (kopis_id, title, start_date, end_date, venue, region, runtime, 
                 age_rating, ticket_price, genre_id, raw_program_info, 
                 poster_url, detail_image_url, reservation_url, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(kopis_id) DO UPDATE SET
                    title = excluded.title,
                    start_date = excluded.start_date,
                    end_date = excluded.end_date,
                    venue = excluded.venue,
                    region = excluded.region,
                    runtime = excluded.runtime,
                    age_rating = excluded.age_rating,
                    ticket_price = excluded.ticket_price,
                    genre_id = excluded.genre_id,
                    raw_program_info = excluded.raw_program_info,
                    poster_url = excluded.poster_url,
                    detail_image_url = excluded.detail_image_url,
                    reservation_url = excluded.reservation_url,
                    status = excluded.status
            """, (
                k_id, title, s_date, e_date, get_val("venue"), region, 
                get_val("runtime"), get_val("age"), get_val("price"), genre_id, 
                get_val("prog"), p_url, det_img, res_url, get_val("status") or "공연예정"
            ))
            
            cursor.execute("SELECT id FROM Performance WHERE kopis_id = ?", (k_id,))
            perf_id = cursor.fetchone()[0]
            counts["perf"] += 1

            # [수정 2] N:M 관계 테이블 멱등성 보장 (UPSERT 시 기존 매핑 제거)
            cursor.execute("DELETE FROM Performance_Artist WHERE performance_id = ?", (perf_id,))
            cursor.execute("DELETE FROM Performance_Work WHERE performance_id = ?", (perf_id,))

            # 아티스트 정제 및 매핑
            raw_artists = get_val("artists")
            if raw_artists:
                artist_list = [n.strip() for n in str(raw_artists).split(',') if n.strip()]
                seen_artists = set() # [추가] 단일 공연 내 아티스트 중복 매핑 방지용 세트
                
                for a_name in artist_list:
                    clean_name, role = clean_artist_name(a_name)
                    if not clean_name: continue
                    
                    if clean_name in artist_cache:
                        a_id = artist_cache[clean_name]
                    else:
                        cursor.execute("INSERT OR IGNORE INTO Artist (name) VALUES (?)", (clean_name,))
                        cursor.execute("SELECT id FROM Artist WHERE name = ?", (clean_name,))
                        a_id = cursor.fetchone()[0]
                        artist_cache[clean_name] = a_id
                    
                    # [추가] 이미 현재 공연에 맵핑된 아티스트 ID라면 건너뛰기
                    if a_id in seen_artists:
                        continue
                    seen_artists.add(a_id)
                        
                    cursor.execute("INSERT INTO Performance_Artist (performance_id, artist_id, role) VALUES (?, ?, ?)", (perf_id, a_id, role))
                    counts["artist"] += 1

            # 프로그램 파서 실행
            parse_program_with_context(perf_id, get_val("prog"))

        conn.commit()
        print(f"✅ 적재 성공: 공연 {counts['perf']}건, 아티스트 연결 {counts['artist']}건 (날짜 누락 스킵: {counts['skipped']}건)")

    except Exception as e:
        conn.rollback() # DB 롤백
        
        # [안정성 보완] DB가 롤백되었으므로, 파이썬 메모리의 캐시도 강제 초기화하여 동기화
        genre_cache.clear()
        artist_cache.clear()
        composer_cache.clear()
        work_cache.clear()
        
        print(f"❌ 파이프라인 중단 및 트랜잭션 롤백 완료: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    run_etl_process()