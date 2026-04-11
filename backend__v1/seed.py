"""
seed.py
초기 데이터를 DB에 적재합니다.

실행 방법:
    cd backend_v1/app
    python seed.py

주의:
    이미 데이터가 있으면 중복 적재됩니다.
    깨끗하게 시작하려면 ../db/concerts.db 파일을 삭제 후 실행하세요.

데이터 출처:
    - 공연 데이터: 프로젝트 제공 KOPIS CSV (20260101~20261231, 서양음악 클래식, 2297건)
    - 작곡가/아티스트: 프론트 mock 데이터 기반 수작업 정의
    - 장르: 프론트 탭 UI 기준으로 정의 (교향곡/협주곡/오페라/가곡/피아노 독주/실내악/기타)

장르 자동 분류 방식:
    KOPIS 데이터의 장르는 모두 "서양음악(클래식)"이므로 공연명 키워드로 장르를 추론.
    예: "교향곡"이 공연명에 포함 → 교향곡 장르로 분류.
"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal, engine
from models import (
    Base,
    Genre,
    Composer,
    Work,
    Performance,
    PerformanceDate,
    Artist,
)

# ─────────────────────────────────────────────────────────────────────────────
# KOPIS CSV 경로
# seed.py는 app/ 에서 실행되므로 ../../ 경로로 DB 문서 접근
# ─────────────────────────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
KOPIS_CSV = os.path.join(
    _HERE, "..", "데이터베이스 스키마 및 연동 명세서",
    "DB 문서", "kopis_classic_data.csv"
)


# ─────────────────────────────────────────────────────────────────────────────
# 장르 정의 (프론트 탭 UI 기준)
# ─────────────────────────────────────────────────────────────────────────────
GENRES = [
    {"name": "교향곡",    "name_en": "Symphony",    "children": []},
    {"name": "협주곡",    "name_en": "Concerto",    "children": []},
    {"name": "오페라",    "name_en": "Opera",       "children": []},
    {"name": "가곡",      "name_en": "Lied",        "children": []},
    {"name": "피아노 독주", "name_en": "Piano Solo", "children": []},
    {"name": "실내악",    "name_en": "Chamber",     "children": []},
    {"name": "기타",      "name_en": "Others",      "children": []},
]

# 장르 키워드 매핑 (공연명에 해당 키워드가 포함되면 해당 장르로 분류)
# 왜 순서가 중요한가:
#   "피아노 협주곡"은 협주곡이 피아노보다 먼저 체크되어야 협주곡으로 분류됨.
#   피아노 독주 키워드보다 협주곡 키워드를 우선 검사.
GENRE_KEYWORDS = [
    ("교향곡",    ["교향곡", "심포니", "symphony", "필하모닉 오케스트라", "오케스트라 정기"]),
    ("협주곡",    ["협주곡", "concerto", "콘체르토"]),
    ("오페라",    ["오페라", "opera", "오페레타"]),
    ("가곡",      ["가곡", "독창회", "성악", "소프라노", "메조소프라노", "테너", "바리톤",
                   "베이스 바리톤", "리트", "아리아"]),
    ("실내악",    ["실내악", "사중주", "삼중주", "앙상블", "chamber", "duo", "trio",
                   "quartet", "quintet", "이중주", "사중주"]),
    ("피아노 독주", ["피아노 리사이틀", "피아노 독주", "건반"]),
]
# 위 키워드 중 어느 것도 해당하지 않으면 기타로 분류


# ─────────────────────────────────────────────────────────────────────────────
# 작곡가 데이터
# ─────────────────────────────────────────────────────────────────────────────
COMPOSERS = [
    # 바로크 (1600~1750)
    {"name": "Bach",         "name_ko": "바흐",         "era": "바로크", "featured": True,  "birth_year": 1685, "death_year": 1750},
    {"name": "Handel",       "name_ko": "헨델",         "era": "바로크", "featured": False, "birth_year": 1685, "death_year": 1759},
    {"name": "Vivaldi",      "name_ko": "비발디",       "era": "바로크", "featured": False, "birth_year": 1678, "death_year": 1741},
    # 고전 (1750~1820)
    {"name": "Haydn",        "name_ko": "하이든",       "era": "고전",   "featured": False, "birth_year": 1732, "death_year": 1809},
    {"name": "Mozart",       "name_ko": "모차르트",     "era": "고전",   "featured": True,  "birth_year": 1756, "death_year": 1791},
    # 낭만 (1820~1900) — 베토벤은 고전-낭만 경계이나 후기 작품 기준으로 낭만 분류
    {"name": "Beethoven",    "name_ko": "베토벤",       "era": "낭만",   "featured": True,  "birth_year": 1770, "death_year": 1827},
    {"name": "Schubert",     "name_ko": "슈베르트",     "era": "낭만",   "featured": False, "birth_year": 1797, "death_year": 1828},
    {"name": "Mendelssohn",  "name_ko": "멘델스존",     "era": "낭만",   "featured": False, "birth_year": 1809, "death_year": 1847},
    {"name": "Chopin",       "name_ko": "쇼팽",         "era": "낭만",   "featured": True,  "birth_year": 1810, "death_year": 1849},
    {"name": "Schumann",     "name_ko": "슈만",         "era": "낭만",   "featured": False, "birth_year": 1810, "death_year": 1856},
    {"name": "Liszt",        "name_ko": "리스트",       "era": "낭만",   "featured": False, "birth_year": 1811, "death_year": 1886},
    {"name": "Wagner",       "name_ko": "바그너",       "era": "낭만",   "featured": False, "birth_year": 1813, "death_year": 1883},
    {"name": "Bruckner",     "name_ko": "브루크너",     "era": "낭만",   "featured": False, "birth_year": 1824, "death_year": 1896},
    {"name": "Brahms",       "name_ko": "브람스",       "era": "낭만",   "featured": True,  "birth_year": 1833, "death_year": 1897},
    {"name": "Dvorak",       "name_ko": "드보르자크",   "era": "낭만",   "featured": False, "birth_year": 1841, "death_year": 1904},
    {"name": "Tchaikovsky",  "name_ko": "차이콥스키",   "era": "낭만",   "featured": True,  "birth_year": 1840, "death_year": 1893},
    {"name": "Puccini",      "name_ko": "푸치니",       "era": "낭만",   "featured": False, "birth_year": 1858, "death_year": 1924},
    {"name": "Mahler",       "name_ko": "말러",         "era": "낭만",   "featured": True,  "birth_year": 1860, "death_year": 1911},
    {"name": "Rachmaninoff", "name_ko": "라흐마니노프", "era": "낭만",   "featured": False, "birth_year": 1873, "death_year": 1943},
    # 근현대 (1900~)
    {"name": "Debussy",      "name_ko": "드뷔시",       "era": "근현대", "featured": False, "birth_year": 1862, "death_year": 1918},
    {"name": "Ravel",        "name_ko": "라벨",         "era": "근현대", "featured": False, "birth_year": 1875, "death_year": 1937},
    {"name": "Schonberg",    "name_ko": "쇤베르크",     "era": "근현대", "featured": False, "birth_year": 1874, "death_year": 1951},
    {"name": "Stravinsky",   "name_ko": "스트라빈스키", "era": "근현대", "featured": False, "birth_year": 1882, "death_year": 1971},
    {"name": "Bartok",       "name_ko": "바르톡",       "era": "근현대", "featured": False, "birth_year": 1881, "death_year": 1945},
    {"name": "Prokofiev",    "name_ko": "프로코피에프", "era": "근현대", "featured": False, "birth_year": 1891, "death_year": 1953},
    {"name": "Shostakovich", "name_ko": "쇼스타코비치", "era": "근현대", "featured": False, "birth_year": 1906, "death_year": 1975},
]

# ─────────────────────────────────────────────────────────────────────────────
# 아티스트 데이터 (지휘자·오케스트라·솔리스트·악장)
# ─────────────────────────────────────────────────────────────────────────────
ARTISTS = [
    # 지휘자
    {"name": "정명훈",   "role": "지휘자"},
    {"name": "김지현",   "role": "지휘자"},
    {"name": "최민재",   "role": "지휘자"},
    {"name": "임헌정",   "role": "지휘자"},
    # 오케스트라
    {"name": "서울시립교향악단",    "role": "오케스트라"},
    {"name": "KBS교향악단",         "role": "오케스트라"},
    {"name": "코리아심포니오케스트라", "role": "오케스트라"},
    {"name": "박연우",   "role": "오케스트라"},
    # 솔리스트
    {"name": "조성진",   "role": "솔리스트"},
    {"name": "임동혁",   "role": "솔리스트"},
    {"name": "이다현",   "role": "솔리스트"},
    {"name": "한규민",   "role": "솔리스트"},
    # 악장
    {"name": "차하린",   "role": "악장"},
    {"name": "문승우",   "role": "악장"},
]


# ─────────────────────────────────────────────────────────────────────────────
# 헬퍼 함수
# ─────────────────────────────────────────────────────────────────────────────

def _kopis_date_to_iso(date_str: str) -> str:
    """
    KOPIS 날짜 형식(2026.05.25)을 ISO 형식(2026-05-25)으로 변환.
    변환 실패 시 원본 문자열 반환 (안전하게 처리).
    """
    if not date_str:
        return ""
    return date_str.replace(".", "-").strip()


def _map_status(kopis_status: str) -> str:
    """
    KOPIS 상태명을 내부 상태 코드로 변환.
    공연예정/공연중 → upcoming, 공연완료 → past
    """
    if "완료" in kopis_status:
        return "past"
    return "upcoming"


def _assign_genre(title: str, genre_map: dict) -> object:
    """
    공연명 키워드를 기반으로 장르 ORM 객체를 반환.

    왜 키워드 기반으로 장르를 추론하는가:
        KOPIS CSV의 장르 컬럼이 모두 "서양음악(클래식)"이라 그대로 사용 불가.
        공연명에서 키워드를 추출해 7개 장르로 분류하는 것이 현실적인 대안.

    순서가 중요한 이유:
        "피아노 협주곡"에서 피아노 독주보다 협주곡이 먼저 매칭되어야 올바른 분류가 됨.
    """
    title_lower = title.lower()
    for genre_name, keywords in GENRE_KEYWORDS:
        for kw in keywords:
            if kw in title_lower:
                g = genre_map.get(genre_name)
                if g:
                    return g
    return genre_map.get("기타")


def _read_kopis_csv() -> list:
    """
    KOPIS CSV를 읽어 딕셔너리 리스트로 반환.
    CSV 헤더: 공연ID, 공연명, 시작일, 종료일, 공연장소, 장르, 포스터, 상태
    """
    if not os.path.exists(KOPIS_CSV):
        print(f"  [경고] KOPIS CSV를 찾을 수 없습니다: {KOPIS_CSV}")
        print("  → 수동 정의 샘플 데이터 10개로 대체합니다.")
        return []

    rows = []
    with open(KOPIS_CSV, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


# KOPIS CSV가 없을 때 사용하는 최소 샘플 데이터
# (개발 환경에서 CSV 없이도 서버가 동작할 수 있도록)
SAMPLE_PERFORMANCES = [
    {"title": "베토벤 교향곡 9번 합창",           "start": "2026-04-12", "end": "2026-04-12", "venue": "예술의전당 콘서트홀",       "poster": "http://www.kopis.or.kr/upload/pfmPoster/PF_PF285068_260212_131501.gif", "status": "upcoming"},
    {"title": "말러 교향곡 5번",                  "start": "2026-05-01", "end": "2026-05-01", "venue": "롯데콘서트홀",              "poster": None,                                                                     "status": "upcoming"},
    {"title": "라흐마니노프 피아노 협주곡 2번",   "start": "2026-05-15", "end": "2026-05-15", "venue": "예술의전당 콘서트홀",       "poster": None,                                                                     "status": "upcoming"},
    {"title": "멘델스존 바이올린 협주곡",          "start": "2026-04-20", "end": "2026-04-20", "venue": "롯데콘서트홀",              "poster": "http://www.kopis.or.kr/upload/pfmPoster/PF_PF286968_260313_111453.gif", "status": "upcoming"},
    {"title": "모차르트 마술피리",                 "start": "2026-05-02", "end": "2026-05-05", "venue": "예술의전당 오페라극장",     "poster": None,                                                                     "status": "upcoming"},
    {"title": "슈베르트 겨울나그네",               "start": "2026-05-10", "end": "2026-05-10", "venue": "금호아트홀 연세",           "poster": None,                                                                     "status": "upcoming"},
    {"title": "서울스프링실내악축제 개막공연",     "start": "2026-04-09", "end": "2026-04-09", "venue": "예술의전당 IBK챔버홀",      "poster": "http://www.kopis.or.kr/upload/pfmPoster/PF_PF285797_260225_152131.gif", "status": "upcoming"},
    {"title": "랑랑 피아노 리사이틀",              "start": "2026-04-03", "end": "2026-04-03", "venue": "예술의전당 콘서트홀",       "poster": "http://www.kopis.or.kr/upload/pfmPoster/PF_PF285941_260227_104911.gif", "status": "upcoming"},
    {"title": "국립오페라단 정기공연: 베르테르",  "start": "2026-04-16", "end": "2026-04-19", "venue": "예술의전당 오페라극장",     "poster": "http://www.kopis.or.kr/upload/pfmPoster/PF_PF285068_260212_131501.gif", "status": "upcoming"},
    {"title": "KBS교향악단 정기연주회",            "start": "2026-05-30", "end": "2026-05-30", "venue": "KBS홀",                    "poster": None,                                                                     "status": "upcoming"},
]


# ─────────────────────────────────────────────────────────────────────────────
# 메인 적재 함수
# ─────────────────────────────────────────────────────────────────────────────

def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        print("[시작] 시드 데이터 적재 시작...")

        # ── 1. 장르 ─────────────────────────────────────────────────────────
        print("  [1/4] 장르 적재 중...")
        genre_map: dict = {}
        for g_data in GENRES:
            parent = Genre(name=g_data["name"], name_en=g_data.get("name_en"))
            db.add(parent)
            db.flush()
            genre_map[g_data["name"]] = parent
        db.flush()
        print(f"     → {len(genre_map)}개 장르 등록")

        # ── 2. 작곡가 ────────────────────────────────────────────────────────
        print("  [2/4] 작곡가 적재 중...")
        for c_data in COMPOSERS:
            db.add(Composer(
                name=c_data["name"],
                name_ko=c_data["name_ko"],
                era=c_data["era"],
                featured=c_data["featured"],
                birth_year=c_data.get("birth_year"),
                death_year=c_data.get("death_year"),
            ))
        db.flush()
        print(f"     → {len(COMPOSERS)}명 작곡가 등록")

        # ── 3. 공연 (KOPIS CSV 우선, 없으면 샘플) ──────────────────────────
        print("  [3/4] 공연 적재 중 (KOPIS CSV)...")
        kopis_rows = _read_kopis_csv()

        if kopis_rows:
            # KOPIS CSV 컬럼 이름 (한국어 헤더)
            # 순서: 공연ID, 공연명, 시작일, 종료일, 공연장소, 장르, 포스터, 상태
            col_keys = list(kopis_rows[0].keys())
            COL_ID     = col_keys[0]  # 공연ID
            COL_TITLE  = col_keys[1]  # 공연명
            COL_START  = col_keys[2]  # 시작일
            COL_END    = col_keys[3]  # 종료일
            COL_VENUE  = col_keys[4]  # 공연장소
            # col_keys[5] = 장르 (모두 서양음악(클래식), 미사용)
            COL_POSTER = col_keys[6]  # 포스터
            COL_STATUS = col_keys[7]  # 상태

            count = 0
            for row in kopis_rows:
                title      = row[COL_TITLE].strip()
                start_date = _kopis_date_to_iso(row[COL_START])
                end_date   = _kopis_date_to_iso(row[COL_END])
                venue      = row[COL_VENUE].strip()
                poster_url = row[COL_POSTER].strip() or None
                status     = _map_status(row[COL_STATUS])
                kopis_id   = row[COL_ID].strip()

                genre_obj = _assign_genre(title, genre_map)

                perf = Performance(
                    kopis_id   = kopis_id,
                    title      = title,
                    venue      = venue,
                    poster_url = poster_url,
                    genre_id   = genre_obj.id if genre_obj else None,
                    start_date = start_date,
                    end_date   = end_date,
                    status     = status,
                )
                db.add(perf)
                db.flush()

                # PerformanceDate: 시작일 등록 (기간별 페이지 달력 점 표시에 사용)
                # 왜 시작일만 등록하는가:
                #   날짜 범위 전체를 PerformanceDate로 만들면 한 달짜리 오페라는
                #   30개의 레코드가 생겨 DB가 비대해짐.
                #   프론트 달력은 공연 시작일에 점을 찍는 것으로 충분.
                if start_date:
                    db.add(PerformanceDate(performance_id=perf.id, date=start_date))

                count += 1
                # 500건마다 중간 커밋으로 메모리 절약
                if count % 500 == 0:
                    db.flush()
                    print(f"     → {count}건 처리 중...")

            print(f"     → {count}건 공연 등록 (KOPIS)")

        else:
            # CSV 없으면 샘플 데이터 사용
            for p_data in SAMPLE_PERFORMANCES:
                genre_obj = _assign_genre(p_data["title"], genre_map)
                perf = Performance(
                    title      = p_data["title"],
                    venue      = p_data["venue"],
                    poster_url = p_data["poster"],
                    genre_id   = genre_obj.id if genre_obj else None,
                    start_date = p_data["start"],
                    end_date   = p_data["end"],
                    status     = p_data["status"],
                )
                db.add(perf)
                db.flush()
                if p_data["start"]:
                    db.add(PerformanceDate(performance_id=perf.id, date=p_data["start"]))
            print(f"     → {len(SAMPLE_PERFORMANCES)}건 공연 등록 (샘플)")

        # ── 4. 아티스트 ──────────────────────────────────────────────────────
        print("  [4/4] 아티스트 적재 중...")
        for a_data in ARTISTS:
            db.add(Artist(name=a_data["name"], role=a_data["role"]))
        print(f"     → {len(ARTISTS)}명 아티스트 등록")

        db.commit()
        print("\n[완료] 시드 데이터 적재 완료!")
        print("   서버 실행: uvicorn main:app --reload --port 8000")
        print("   API 문서:  http://localhost:8000/docs")

    except Exception as e:
        db.rollback()
        print(f"\n[오류] {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
