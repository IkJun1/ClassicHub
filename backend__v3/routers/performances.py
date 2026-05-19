"""
routers/performances.py

공연 관련 API 3종:
  GET /api/performances/recent  — 최근 공연 (메인 화면)
  GET /api/performances         — 공연 목록 + 필터/검색/정렬/페이지네이션
  GET /api/performances/{id}    — 공연 상세

변경 이력:
  - performance_platform.db (ERD_v2) 매핑에 맞게 수정
  - PerformanceDate 테이블 제거 → start_date/end_date 직접 사용
  - Performer 모델 제거 → Performance_Artist → Artist 로 대체
  - Performance_Work ORM 모델 사용 (order_num 직접 접근)
  - 테이블명 PascalCase 적용 (raw SQL에 큰따옴표 사용)
"""
import re
from typing import Optional, List

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session, joinedload, selectinload

from database import get_db
from models import Genre, Performance, PerformanceWork, Work, PerformanceArtist
from utils import parse_ticket_price, parse_runtime
from schemas import (
    ComposerRefItem,
    GenreParentItem,
    GenreRefItem,
    PaginatedResponse,
    PerformanceDetail,
    PerformerItem,
    PerformanceSummary,
    ProgramDetailItem,
    ProgramSummaryItem,
    RecentPerformanceSummary,
    SuccessResponse,
    WorkRefItem,
)

router = APIRouter(tags=["공연"])

# ── 상수 정의 ────────────────────────────────────────────────────────────────

VALID_SORTS    = {"date_asc", "date_desc", "title_asc"}
# ETL이 KOPIS 원문 한국어 값을 그대로 저장하므로 허용값도 한국어 기준으로 통일
VALID_STATUSES = {"공연예정", "공연중", "공연완료", "all"}

# STATUS_DB_MAP: 이전 버전에서 영어 파라미터(upcoming/past)를 한국어 DB값으로 변환하던 맵.
# VALID_STATUSES가 한국어로 전환된 이후 검증 로직에서는 직접 사용되지 않음.
# ETL이 KOPIS 원문값(공연예정/공연중/공연완료)을 그대로 저장하므로 API도 동일 값을 사용.
STATUS_DB_MAP = {
    "upcoming": "공연예정",
    "past":     "공연완료",
}

# performance_date 테이블 제거 → start_date 기준 정렬
SORT_SQL = {
    "date_asc":  "p.start_date ASC",
    "date_desc": "p.start_date DESC",
    "title_asc": "p.title ASC",
}

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _err_date_format(field_name: str) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={
            "success": False,
            "data": None,
            "message": f"{field_name} 날짜 형식이 올바르지 않습니다. YYYY-MM-DD 형식을 사용하세요.",
            "error_code": "INVALID_PARAMETER",
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. 최근 공연 조회  GET /api/performances/recent
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/performances/recent",
    summary="최근 공연 조회 (메인 화면용)",
    response_model=SuccessResponse[List[RecentPerformanceSummary]],
)
def get_recent_performances(
    limit: int = Query(10, ge=1, le=50, description="조회할 공연 수 (기본 10, 최대 50)"),
    db: Session = Depends(get_db),
):
    performances = (
        db.query(Performance)
        .options(
            joinedload(Performance.genre),
            selectinload(Performance.performance_works)
                .joinedload(PerformanceWork.work)
                .joinedload(Work.composer),
        )
        .filter(Performance.status == "공연예정")
        .order_by(Performance.start_date.asc())
        .limit(limit)
        .all()
    )

    result = [
        RecentPerformanceSummary(
            id=p.id,
            title=p.title,
            dates=[p.start_date] if p.start_date else [],
            venue=p.venue,
            genre=p.genre.name if p.genre else None,
            poster_url=p.poster_url,
            img=p.poster_url,
            date=p.start_date,
            programs=[
                ProgramSummaryItem(
                    composer=pw.work.composer.name if pw.work and pw.work.composer else "",
                    work=pw.work.title if pw.work else "",
                )
                for pw in sorted(p.performance_works, key=lambda x: x.order_num or 0)
                if pw.work
            ],
        )
        for p in performances
    ]

    return {"success": True, "message": "OK", "data": result}


# ─────────────────────────────────────────────────────────────────────────────
# 2. 공연 목록 조회  GET /api/performances
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/performances",
    summary="공연 목록 조회 (검색·필터·정렬·페이지네이션)",
    response_model=PaginatedResponse[PerformanceSummary],
)
def get_performances(
    keyword: Optional[str] = Query(None, description="통합 키워드 검색 (공연명·작곡가·곡명)"),
    composer: Optional[str] = Query(None, description="작곡가 이름 필터"),
    genre: Optional[str] = Query(None, description="장르 이름 필터"),
    venue: Optional[str] = Query(None, description="공연 장소 필터"),
    date_from: Optional[str] = Query(None, description="시작 날짜 (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="종료 날짜 (YYYY-MM-DD)"),
    max_price: Optional[int] = Query(None, description="티켓 최저가가 이 값 이하인 공연만 검색"),
    max_runtime: Optional[int] = Query(None, description="총 런타임(분)이 이 값 이하인 공연만 검색"),
    status: str = Query("공연예정", description="공연 상태: 공연예정 | 공연중 | 공연완료 | all"),
    sort: str = Query("date_asc", description="정렬: date_asc | date_desc | title_asc"),
    page: int = Query(1, ge=1, description="페이지 번호 (1부터 시작)"),
    per_page: int = Query(20, ge=1, le=100, description="페이지당 항목 수 (최대 100)"),
    db: Session = Depends(get_db),
):
    # 1. 파라미터 검증
    if status not in VALID_STATUSES:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "data": None,
                "message": "status 값은 공연예정 | 공연중 | 공연완료 | all 중 하나여야 합니다.",
                "error_code": "INVALID_PARAMETER",
            },
        )

    if sort not in VALID_SORTS:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "data": None,
                "message": "sort 값은 date_asc | date_desc | title_asc 중 하나여야 합니다.",
                "error_code": "INVALID_PARAMETER",
            },
        )

    if date_from and not DATE_RE.match(date_from):
        return _err_date_format("date_from")
    if date_to and not DATE_RE.match(date_to):
        return _err_date_format("date_to")

    # 2. WHERE 조건 동적 조립
    conditions: list = []
    params: dict = {}

    if keyword:
        conditions.append("(p.title LIKE :keyword OR c.name LIKE :keyword OR w.title LIKE :keyword OR p.raw_program_info LIKE :keyword)")
        params["keyword"] = f"%{keyword}%"

    if composer:
        conditions.append("c.name LIKE :composer")
        params["composer"] = f"%{composer}%"

    if genre:
        conditions.append("g.name = :genre")
        params["genre"] = genre

    if venue:
        conditions.append("p.venue LIKE :venue")
        params["venue"] = f"%{venue}%"

    # 날짜 필터: start_date/end_date 범위 겹침 조건 (performance_date 테이블 없음)
    if date_from and date_to:
        conditions.append("(p.start_date <= :date_to AND p.end_date >= :date_from)")
        params["date_from"] = date_from
        params["date_to"]   = date_to
    elif date_from:
        conditions.append("p.end_date >= :date_from")
        params["date_from"] = date_from
    elif date_to:
        conditions.append("p.start_date <= :date_to")
        params["date_to"] = date_to

    if status != "all":
        conditions.append("p.status = :status")
        # VALID_STATUSES가 한국어 기준이므로 변환 없이 직접 전달
        params["status"] = status

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    # PascalCase 테이블명은 큰따옴표로 감싸 SQLite에서 안전하게 참조
    joins = """
        FROM "Performance" p
        LEFT JOIN "Genre" g               ON p.genre_id = g.id
        LEFT JOIN "Performance_Work" pw   ON p.id = pw.performance_id
        LEFT JOIN "Work" w                ON pw.work_id = w.id
        LEFT JOIN "Composer" c            ON w.composer_id = c.id
    """

    # 3. 데이터 조회 및 필터링 적용 전략 분기
    if max_price is not None or max_runtime is not None:
        # SQLite에서 정규식 파싱이 어려우므로 Python 인메모리 필터링 사용
        base_rows = db.execute(
            text(f"""
                SELECT p.id, p.ticket_price, p.runtime 
                {joins} {where} 
                GROUP BY p.id, p.ticket_price, p.runtime 
                ORDER BY {SORT_SQL[sort]}
            """),
            params,
        ).fetchall()
        
        filtered_pids = []
        for r in base_rows:
            pid, t_price, r_time = r[0], r[1], r[2]
            if max_price is not None:
                min_p = parse_ticket_price(t_price)
                if min_p > max_price or min_p == 0:
                    continue
            if max_runtime is not None:
                tot, _ = parse_runtime(r_time)
                if tot > max_runtime or tot == 0:
                    continue
            filtered_pids.append(pid)
            
        total = len(filtered_pids)
        offset = (page - 1) * per_page
        paged_pids = filtered_pids[offset : offset + per_page]
        
        if not paged_pids:
            return {"success": True, "message": "OK", "total": total, "data": []}
            
        # 필터링된 ID들로 상세 데이터 조회 (순서 유지 필요)
        rows_query = db.execute(
            text(f"""
                SELECT
                    p.id, p.title, p.venue, p.poster_url, p.reservation_url,
                    g.name AS genre_name, p.genre_id, p.start_date,
                    p.ticket_price, p.runtime
                FROM "Performance" p
                LEFT JOIN "Genre" g ON p.genre_id = g.id
                WHERE p.id IN :pids
            """).bindparams(bindparam("pids", expanding=True)),
            {"pids": paged_pids}
        ).fetchall()
        
        # IN 절은 순서를 보장하지 않으므로 paged_pids 순서대로 재정렬
        rows_map = {r[0]: r for r in rows_query}
        rows = [rows_map[pid] for pid in paged_pids if pid in rows_map]
    else:
        # 3. 전체 개수 (일반 쿼리)
        total = (
            db.execute(
                text(f"SELECT COUNT(DISTINCT p.id) {joins} {where}"),
                params,
            ).scalar()
            or 0
        )

        # 4. 현재 페이지 데이터 (일반 쿼리)
        offset = (page - 1) * per_page
        data_params = {**params, "per_page": per_page, "offset": offset}

        rows = db.execute(
            text(f"""
                SELECT
                    p.id, p.title, p.venue, p.poster_url, p.reservation_url,
                    g.name AS genre_name, p.genre_id, p.start_date,
                    p.ticket_price, p.runtime
                {joins}
                {where}
                GROUP BY p.id, p.title, p.venue, p.poster_url, p.reservation_url,
                         g.name, p.genre_id, p.start_date, p.ticket_price, p.runtime
                ORDER BY {SORT_SQL[sort]}
                LIMIT :per_page OFFSET :offset
            """),
            data_params,
        ).fetchall()

    if not rows:
        return {"success": True, "message": "OK", "total": total, "data": []}

    pids = [row[0] for row in rows]

    # 5. dates: performance_date 없음 → start_date 기반으로 구성
    dates_map: dict = {row[0]: [row[7]] for row in rows if row[7]}

    # 6. 프로그램 정보 일괄 조회
    programs_stmt = text("""
        SELECT pw.performance_id, c.name, w.title
        FROM "Performance_Work" pw
        JOIN "Work" w      ON pw.work_id = w.id
        JOIN "Composer" c  ON w.composer_id = c.id
        WHERE pw.performance_id IN :pids
    """).bindparams(bindparam("pids", expanding=True))

    programs_map: dict = {}
    for r in db.execute(programs_stmt, {"pids": pids}).fetchall():
        programs_map.setdefault(r[0], []).append(
            {"composer": r[1], "work": r[2]}
        )

    # 7. 응답 데이터 조립
    data = []
    for row in rows:
        tot_time, _ = parse_runtime(row[9])
        data.append(PerformanceSummary(
            id=row[0],
            title=row[1],
            venue=row[2],
            poster_url=row[3],
            reservation_url=row[4],
            genre=row[5],
            genre_id=row[6],
            dates=dates_map.get(row[0]) or [],
            img=row[3],
            date=(dates_map.get(row[0]) or [None])[0],
            min_price=parse_ticket_price(row[8]),
            runtime_min=tot_time if tot_time > 0 else None,
            programs=[
                ProgramSummaryItem(**p)
                for p in programs_map.get(row[0], [])
            ],
        ))

    return {"success": True, "message": "OK", "total": total, "data": data}


# ─────────────────────────────────────────────────────────────────────────────
# 3. 공연 상세 조회  GET /api/performances/{id}
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/performances/{performance_id}",
    summary="공연 상세 조회",
    response_model=SuccessResponse[PerformanceDetail],
)
def get_performance_detail(performance_id: int, db: Session = Depends(get_db)):
    perf = (
        db.query(Performance)
        .options(
            # genre.parent까지 한 번에 로드 — 별도 쿼리 없이 계층 구조 접근 가능 (N+1 방지)
            joinedload(Performance.genre).joinedload(Genre.parent),
            # Performance_Work → Work → Composer 체인을 한 번에 로드 (N+1 방지)
            selectinload(Performance.performance_works)
                .joinedload(PerformanceWork.work)
                .joinedload(Work.composer),
            # Performance_Artist → Artist 로드
            selectinload(Performance.performance_artists)
                .joinedload(PerformanceArtist.artist),
        )
        .filter(Performance.id == performance_id)
        .first()
    )

    if not perf:
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "data": None,
                "message": "공연을 찾을 수 없습니다.",
                "error_code": "PERFORMANCE_NOT_FOUND",
            },
        )

    # 프로그램 목록 조립 (PerformanceWork.order_num 직접 접근)
    programs = [
        ProgramDetailItem(
            order=pw.order_num,
            work=WorkRefItem(
                id=pw.work.id,
                title=pw.work.title,
                composer=ComposerRefItem(
                    id=pw.work.composer.id,
                    name=pw.work.composer.name,
                    era=pw.work.composer.era,  # Composer.era 전달 (None이면 Optional로 처리)
                ) if pw.work.composer else None,
            ),
        )
        for pw in sorted(perf.performance_works, key=lambda x: x.order_num or 0)
        if pw.work
    ]

    # 아티스트 역할 그룹핑 처리
    artist_map = {}
    for pa in perf.performance_artists:
        if not pa.artist: continue
        if pa.artist.id not in artist_map:
            artist_map[pa.artist.id] = {"artist": pa.artist.name, "roles": set()}
        if pa.role:
            artist_map[pa.artist.id]["roles"].add(pa.role)
            
    grouped_artists = [
        PerformerItem(id=aid, artist=info["artist"], roles=list(info["roles"]))
        for aid, info in artist_map.items()
    ]
    
    tot_time, inter_time = parse_runtime(perf.runtime)
    
    detail = PerformanceDetail(
        id=perf.id,
        title=perf.title,
        dates=[perf.start_date] if perf.start_date else [],
        venue=perf.venue,
        region=perf.region,
        # genre.parent는 eager load로 이미 로드됨 — 별도 쿼리 없이 접근 가능
        genre=GenreRefItem(
            id=perf.genre.id,
            name=perf.genre.name,
            parent=GenreParentItem(
                id=perf.genre.parent.id,
                name=perf.genre.parent.name,
            ) if perf.genre.parent else None,
        ) if perf.genre else None,
        poster_url=perf.poster_url,
        detail_image_url=perf.detail_image_url,
        reservation_url=perf.reservation_url,
        source_url=None,            # 레거시 필드, 항상 None
        start_date=perf.start_date,
        end_date=perf.end_date,
        runtime=perf.runtime,
        age_rating=perf.age_rating,
        ticket_price=perf.ticket_price,
        raw_program_info=perf.raw_program_info,
        status=perf.status,
        min_price=parse_ticket_price(perf.ticket_price),
        runtime_min=tot_time if tot_time > 0 else None,
        intermission_min=inter_time if inter_time > 0 else None,
        artists=grouped_artists,
        # order_num 기준 정렬은 programs 변수에서 이미 처리됨
        programs=programs,
    )

    return {"success": True, "message": "OK", "data": detail}
