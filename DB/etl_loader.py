"""
[KOPIS 원본 데이터 정제 및 DB 적재(ETL) 자동화 파이프라인]
본 스크립트는 KOPIS 크롤링/API 원본 CSV 데이터를 정제하여 관계형 데이터베이스(Supabase PostgreSQL)에 구조화하여 적재하고,
주기적인 스케줄링을 통해 외부 데이터의 상태 변화를 환경에 자동으로 동기화하는 백그라운드 데몬(Daemon) 역할을 수행합니다.

- 주요 파이프라인 기능 (Extract, Transform, Load):
  1. 결측치 전처리 (Transform): DB 제약조건 위반 방지를 위해 Pandas의 NaN 값을 Python None(DB의 NULL)으로 완전 치환.
  2. 상태 동기화 및 갱신 (UPSERT): 고유 식별자(kopis_id) 충돌 시, 신규 데이터는 삽입(INSERT)하고 기존 데이터는 최신화(UPDATE).
  3. 장르 계층 구조화 및 지능형 분류: 제목 키워드 분석을 통해 장르를 자동 매핑.
  4. 출연진 데이터 정규화 (Surgical Cleaning): 악기/역할 키워드 사전 기반 정제.
  5. 문맥 유지형 프로그램 파서 (State-Machine): 작곡가 이름 기반 프로그램 추출.
  6. SQLAlchemy Core 연동: PostgreSQL 특화 UPSERT 적용 및 ORM/Core 매핑.
"""

import sys
import os
import re
import pandas as pd
from datetime import datetime

# backend__v3 모듈 임포트를 위한 경로 추가
base_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.join(base_dir, '..', 'backend__v3')
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from database import engine, SessionLocal
from models import Genre, Composer, Work, Artist, Performance, PerformanceArtist, PerformanceWork
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import select, delete

# ─────────────────────────────────────────────────────────────────────────────
# [고도화 전략 1] 마스터 사전 및 설정
# ─────────────────────────────────────────────────────────────────────────────

ROLE_KEYWORDS = ["피아노", "바이올린", "첼로", "지휘", "소프라노", "테너", "바리톤", "베이스", "협연", "연주", "악단", "오케스트라", "챔버"]

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
    "강원": "강원", "강원도": "경기", 
    "충북": "충북", "충남": "충남", "전북": "전북", "전남": "전남", "경북": "경북", "경남": "경남", "제주": "제주"
}

def run_etl_process():
    csv_file = os.path.join(base_dir, '..', 'kopis_classic_data.csv')

    if not os.path.exists(csv_file):
        print(f"오류: '{csv_file}' 파일을 찾을 수 없습니다.")
        return

    print(f"📦 통합 데이터 로드 및 컬럼 분석 시작: {os.path.basename(csv_file)}")
    try:
        df = pd.read_csv(csv_file)
        df = df.where(pd.notnull(df), None)
    except Exception as e:
        print(f"❌ 로드 실패: {e}")
        return

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

    # SQLAlchemy Session 
    session = SessionLocal()

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
            
        genre_obj = session.scalar(select(Genre).where(Genre.name == target_genre))
        if genre_obj:
            genre_cache[target_genre] = genre_obj.id
            return genre_obj.id
            
        new_genre = Genre(name=target_genre)
        session.add(new_genre)
        session.flush()
        genre_cache[target_genre] = new_genre.id
        return new_genre.id

    def parse_program_with_context(perf_id, program_text):
        if not program_text: return
        
        clean_text = str(program_text).strip()
        noise_patterns = [
            r'\[공연소개\]', r'\[프로그램\]', r'\[PROGRAM\]', r'\[Program\]',
            r'▶\s*출연진', r'▶\s*프로그램', r'※\s*본\s*프로그램은.*',
            r'■\s*프로그램', r'\*.*변경될\s*수\s*있습니다\.?'
        ]
        for pattern in noise_patterns:
            clean_text = re.sub(pattern, '', clean_text)

        raw_lines = re.split(r'[\n;/|]', clean_text)
        
        last_comp_id = None
        order = 1
        
        for line in raw_lines:
            line = line.strip()
            if not line: continue
            
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
                    stmt = insert(Composer).values(name=found_composer_key, era="미분류").on_conflict_do_nothing(index_elements=['name'])
                    session.execute(stmt)
                    session.flush()
                    last_comp_id = session.scalar(select(Composer.id).where(Composer.name == found_composer_key))
                    composer_cache[found_composer_key] = last_comp_id

            if last_comp_id:
                work_title = line
                if found_composer_key:
                    for alias in MASTER_COMPOSERS[found_composer_key]:
                        work_title = work_title.replace(alias, "")
                        
                work_title = re.sub(r'^[:\-\s,·.]+', '', work_title).strip()
                
                if not work_title or len(work_title) < 2 or len(work_title) > 100: 
                    continue 
                
                cache_key = (work_title, last_comp_id)
                if cache_key in work_cache:
                    work_id = work_cache[cache_key]
                else:
                    work_id = session.scalar(select(Work.id).where(Work.title == work_title, Work.composer_id == last_comp_id))
                    if not work_id:
                        new_work = Work(title=work_title, composer_id=last_comp_id)
                        session.add(new_work)
                        session.flush()
                        work_id = new_work.id
                    work_cache[cache_key] = work_id
                    
                new_pw = PerformanceWork(performance_id=perf_id, work_id=work_id, order_num=order)
                session.add(new_pw)
                order += 1

    print("🚀 수정된 파이프라인 가동 (SQLAlchemy + PostgreSQL UPSERT)")
    
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
            
            if not s_date or not e_date:
                counts["skipped"] += 1
                continue

            p_url = clean_url(get_val("poster"))
            det_img = clean_url(get_val("img"))
            res_url = clean_url(get_val("res"))
            region = standardize_region(get_val("region"))
            genre_id = get_genre_id(title)

            # PostgreSQL 특화 UPSERT (ON CONFLICT DO UPDATE)
            insert_stmt = insert(Performance).values(
                kopis_id=k_id,
                title=title,
                start_date=s_date,
                end_date=e_date,
                venue=get_val("venue"),
                region=region,
                runtime=get_val("runtime"),
                age_rating=get_val("age"),
                ticket_price=get_val("price"),
                genre_id=genre_id,
                raw_program_info=get_val("prog"),
                poster_url=p_url,
                detail_image_url=det_img,
                reservation_url=res_url,
                status=get_val("status") or "공연예정"
            )
            
            update_dict = insert_stmt.excluded
            upsert_stmt = insert_stmt.on_conflict_do_update(
                index_elements=['kopis_id'],
                set_={
                    'title': update_dict.title,
                    'start_date': update_dict.start_date,
                    'end_date': update_dict.end_date,
                    'venue': update_dict.venue,
                    'region': update_dict.region,
                    'runtime': update_dict.runtime,
                    'age_rating': update_dict.age_rating,
                    'ticket_price': update_dict.ticket_price,
                    'genre_id': update_dict.genre_id,
                    'raw_program_info': update_dict.raw_program_info,
                    'poster_url': update_dict.poster_url,
                    'detail_image_url': update_dict.detail_image_url,
                    'reservation_url': update_dict.reservation_url,
                    'status': update_dict.status
                }
            ).returning(Performance.id)
            
            perf_id = session.execute(upsert_stmt).scalar()
            if not perf_id:
                # 안전장치: returning으로 못 가져왔을 경우 대비
                perf_id = session.scalar(select(Performance.id).where(Performance.kopis_id == k_id))
            
            counts["perf"] += 1

            # N:M 관계 데이터 초기화
            session.execute(delete(PerformanceArtist).where(PerformanceArtist.performance_id == perf_id))
            session.execute(delete(PerformanceWork).where(PerformanceWork.performance_id == perf_id))
            session.flush()

            # 아티스트 정제 및 매핑
            raw_artists = get_val("artists")
            if raw_artists:
                artist_list = [n.strip() for n in str(raw_artists).split(',') if n.strip()]
                seen_artists = set()
                
                for a_name in artist_list:
                    clean_name, role = clean_artist_name(a_name)
                    if not clean_name: continue
                    
                    if clean_name in artist_cache:
                        a_id = artist_cache[clean_name]
                    else:
                        stmt = insert(Artist).values(name=clean_name).on_conflict_do_nothing(index_elements=['name'])
                        session.execute(stmt)
                        session.flush()
                        a_id = session.scalar(select(Artist.id).where(Artist.name == clean_name))
                        artist_cache[clean_name] = a_id
                    
                    if a_id in seen_artists:
                        continue
                    seen_artists.add(a_id)
                        
                    new_pa = PerformanceArtist(performance_id=perf_id, artist_id=a_id, role=role)
                    session.add(new_pa)
                    counts["artist"] += 1

            # 프로그램 파서 실행
            parse_program_with_context(perf_id, get_val("prog"))
            session.flush()

        session.commit()
        print(f"✅ 적재 성공: 공연 {counts['perf']}건, 아티스트 연결 {counts['artist']}건 (날짜 누락 스킵: {counts['skipped']}건)")

    except Exception as e:
        session.rollback()
        genre_cache.clear()
        artist_cache.clear()
        composer_cache.clear()
        work_cache.clear()
        print(f"❌ 파이프라인 중단 및 트랜잭션 롤백 완료: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    run_etl_process()