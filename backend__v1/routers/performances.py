"""
routers/performances.py

공연 관련 API 3종을 하나의 파일에 통합:
  GET /api/performances/recent  — 최근 공연 (메인 화면)
  GET /api/performances         — 공연 목록 + 필터/검색/정렬/페이지네이션
  GET /api/performances/{id}    — 공연 상세

왜 한 파일에 통합했는가:
- classic-api에서는 concerts.py / performances.py 두 파일로 분리되어 있었음
- 하지만 엔드포인트가 모두 /api/performances 접두사를 공유하므로
  하나의 라우터 파일로 관리하는 것이 팀원이 파일 위치를 찾기 쉬움
- /recent 와 /{id} 경로 순서 충돌 문제도 한 파일 내에서 선언 순서로 해결 가능

⚠️ 경로 등록 순서 규칙:
  1. /performances/recent   (정적 경로 먼저)
  2. /performances          (목록)
  3. /performances/{id}     (변수 경로 마지막)
  순서가 바뀌면 'recent'를 id 파라미터로 오인하여 404 발생
"""
import re
from typing import Optional, List

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session, joinedload, selectinload

from database import get_db
from models import Performance, Work
from schemas import (
    ComposerRefItem,
    GenreParentItem,
    GenreRefItem,
    PaginatedResponse,
    PerformanceDetail,
    PerformanceSummary,
    ProgramDetailItem,
    ProgramSummaryItem,
    RecentPerformanceSummary,
    SuccessResponse,
    WorkRefItem,
)

router = APIRouter(tags=["공연"])

# ── 상수 정의 ────────────────────────────────────────────────────────────────

# 허용 정렬 값
VALID_SORTS = {"date_asc", "date_desc", "title_asc"}

# 허용 상태 값
VALID_STATUSES = {"upcoming", "past", "all"}

# 정렬 값 → SQL 절 매핑
# 왜 COALESCE를 사용하는가:
#   PerformanceDate가 없으면 MIN(pd.date) = NULL → NULL은 ASC 정렬에서 맨 뒤로 밀림.
#   KOPIS 데이터는 start_date를 항상 가지므로 COALESCE(MIN(pd.date), p.start_date)로
#   PerformanceDate가 없어도 start_date 기준으로 정렬이 동작하게 함.
SORT_SQL = {
    "date_asc":  "COALESCE(MIN(pd.date), p.start_date) ASC",
    "date_desc": "COALESCE(MIN(pd.date), p.start_date) DESC",
    "title_asc": "p.title ASC",
}

# 날짜 형식 검증용 정규식 (YYYY-MM-DD)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _err_date_format(field_name: str) -> JSONResponse:
    """날짜 형식 오류 400 응답"""
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
    """
    최근 등록된 공연 목록을 반환합니다.

    [메인 화면 D-Day 섹션에서 사용]
    - 포스터 이미지 URL (poster_url) 포함
    - 프로그램 요약 포함 (작곡가 + 곡명)
    - 상세 정보는 별도 /api/performances/{id} 호출

    [왜 별도 엔드포인트인가]
    - 메인 화면은 최신 N개만 빠르게 로드하면 충분
    - 필터/정렬/페이지네이션이 필요 없어 쿼리가 단순함
    """
    performances = (
        db.query(Performance)
        .options(
            joinedload(Performance.genre),
            selectinload(Performance.dates),
            selectinload(Performance.works).joinedload(Work.composer),
        )
        # 왜 start_date 기준 오름차순인가:
        #   메인 화면에서는 "곧 열리는 공연" 순으로 보여주는 것이 UX상 자연스럽다.
        #   past 공연을 제외하고 다가오는 공연을 먼저 노출.
        .filter(Performance.status == "upcoming")
        .order_by(Performance.start_date.asc())
        .limit(limit)
        .all()
    )

    result = [
        RecentPerformanceSummary(
            id=p.id,
            title=p.title,
            # PerformanceDate가 있으면 그 목록을, 없으면 start_date를 fallback으로 사용.
            # KOPIS 데이터는 start_date에만 PerformanceDate 레코드 1개가 있으므로 정상 동작.
            dates=sorted([d.date for d in p.dates]) or ([p.start_date] if p.start_date else []),
            venue=p.venue,
            genre=p.genre.name if p.genre else None,
            poster_url=p.poster_url,
            img=p.poster_url,
            date=(sorted([d.date for d in p.dates]) or ([p.start_date] if p.start_date else [None]))[0],
            programs=[
                ProgramSummaryItem(
                    composer=w.composer.name if w.composer else "",
                    work=w.title,
                )
                for w in p.works
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
    status: str = Query("upcoming", description="공연 상태: upcoming | past | all"),
    sort: str = Query("date_asc", description="정렬: date_asc | date_desc | title_asc"),
    page: int = Query(1, ge=1, description="페이지 번호 (1부터 시작)"),
    per_page: int = Query(20, ge=1, le=100, description="페이지당 항목 수 (최대 100)"),
    db: Session = Depends(get_db),
):
    """
    공연 목록을 필터·검색·정렬·페이지네이션 하여 반환합니다.

    [왜 필터를 모두 하나의 엔드포인트에 모았는가]
    - 프론트에서 장르별·장소별·기간별 조회가 모두 이 API 하나를 사용함
    - 조건을 AND로 조합하므로 "낭만 장르 + 예술의전당 + 5월" 같은 복합 검색 가능
    - 엔드포인트를 여러 개로 쪼개면 중복 코드가 늘어나고 유지보수가 어려움

    [사용 화면]
    - 장르별 조회: ?genre=교향곡
    - 장소별 조회: ?venue=예술의전당
    - 기간별 조회: ?date_from=2026-05-01&date_to=2026-05-31
    - 전체 검색:  ?keyword=베토벤
    """

    # 1. 파라미터 검증 (400 에러는 즉시 반환)
    if status not in VALID_STATUSES:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "data": None,
                "message": "status 값은 upcoming | past | all 중 하나여야 합니다.",
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

    # 통합 키워드: 공연명 OR 작곡가명 OR 곡명
    if keyword:
        conditions.append("(p.title LIKE :keyword OR c.name LIKE :keyword OR w.title LIKE :keyword)")
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

    # 왜 performance_date와 start_date/end_date 양쪽을 모두 체크하는가:
    #   - PerformanceDate에 날짜가 있는 공연: pd.date로 정확하게 필터
    #   - KOPIS 공연처럼 start_date만 있는 경우: start_date <= date_to AND end_date >= date_from
    #     ("범위 겹침" 조건 — 해당 기간에 공연이 진행 중인지 판단)
    #   두 조건을 OR로 합치면 어느 방식으로 입력된 데이터도 검색됨.
    if date_from and date_to:
        conditions.append(
            "(pd.date BETWEEN :date_from AND :date_to"
            " OR (p.start_date <= :date_to AND p.end_date >= :date_from))"
        )
        params["date_from"] = date_from
        params["date_to"]   = date_to
    elif date_from:
        conditions.append(
            "(pd.date >= :date_from OR p.end_date >= :date_from)"
        )
        params["date_from"] = date_from
    elif date_to:
        conditions.append(
            "(pd.date <= :date_to OR p.start_date <= :date_to)"
        )
        params["date_to"] = date_to

    if status != "all":
        conditions.append("p.status = :status")
        params["status"] = status

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    # 왜 LEFT JOIN을 사용하는가:
    # - work/composer/date가 없는 공연도 목록에 포함시키기 위해
    # - INNER JOIN이면 프로그램 미등록 공연이 검색에서 빠질 수 있음
    joins = """
        FROM performance p
        LEFT JOIN genre g              ON p.genre_id = g.id
        LEFT JOIN performance_work pw  ON p.id = pw.performance_id
        LEFT JOIN work w               ON pw.work_id = w.id
        LEFT JOIN composer c           ON w.composer_id = c.id
        LEFT JOIN performance_date pd  ON p.id = pd.performance_id
    """

    # 3. 전체 개수 (페이지네이션 total 계산용)
    total: int = (
        db.execute(
            text(f"SELECT COUNT(DISTINCT p.id) {joins} {where}"),
            params,
        ).scalar()
        or 0
    )

    # 4. 현재 페이지 데이터 조회
    offset = (page - 1) * per_page
    data_params = {**params, "per_page": per_page, "offset": offset}

    rows = db.execute(
        text(f"""
            SELECT
                p.id,
                p.title,
                p.venue,
                p.poster_url,
                p.source_url,
                g.name AS genre_name,
                p.genre_id,
                p.start_date
            {joins}
            {where}
            GROUP BY p.id, p.title, p.venue, p.poster_url, p.source_url,
                     g.name, p.genre_id, p.start_date
            ORDER BY {SORT_SQL[sort]}
            LIMIT :per_page OFFSET :offset
        """),
        data_params,
    ).fetchall()

    if not rows:
        return {"success": True, "message": "OK", "total": total, "data": []}

    # 5. 날짜·프로그램 정보를 공연 ID 목록으로 한 번에 조회
    #    (N+1 쿼리 방지: 공연마다 개별 쿼리 대신 IN 절로 일괄 조회)
    pids = [row[0] for row in rows]

    dates_stmt = text(
        "SELECT performance_id, date "
        "FROM performance_date "
        "WHERE performance_id IN :pids "
        "ORDER BY date"
    ).bindparams(bindparam("pids", expanding=True))

    dates_map: dict = {}
    for r in db.execute(dates_stmt, {"pids": pids}).fetchall():
        dates_map.setdefault(r[0], []).append(r[1])

    programs_stmt = text("""
        SELECT pw.performance_id, c.name, w.title
        FROM performance_work pw
        JOIN work w      ON pw.work_id = w.id
        JOIN composer c  ON w.composer_id = c.id
        WHERE pw.performance_id IN :pids
    """).bindparams(bindparam("pids", expanding=True))

    programs_map: dict = {}
    for r in db.execute(programs_stmt, {"pids": pids}).fetchall():
        programs_map.setdefault(r[0], []).append(
            {"composer": r[1], "work": r[2]}
        )

    # 6. 응답 데이터 조립
    # start_date 정보가 필요하므로 row에서 추가로 꺼낸다 (SELECT 쿼리에 p.start_date 포함)
    data = [
        PerformanceSummary(
            id=row[0],
            title=row[1],
            venue=row[2],
            poster_url=row[3],
            source_url=row[4],
            genre=row[5],
            genre_id=row[6],
            # PerformanceDate가 없으면 start_date로 대체 — KOPIS 데이터에서는 start_date
            # 컬럼에 날짜가 있고 PerformanceDate에도 같은 값이 들어가므로 항상 반환됨.
            dates=dates_map.get(row[0]) or ([row[7]] if row[7] else []),
            img=row[3],
            date=(dates_map.get(row[0]) or ([row[7]] if row[7] else [None]))[0],
            programs=[
                ProgramSummaryItem(**p)
                for p in programs_map.get(row[0], [])
            ],
        )
        for row in rows
    ]

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
    """
    공연 1개의 상세 정보를 반환합니다.

    [목록 조회와 차이점]
    - 프로그램 상세 (작곡가 한국어명, 연주 순서 포함)
    - 연주자(performers) 목록 포함
    - ticket_url (예매 링크) 포함

    [왜 ORM 방식을 사용하는가]
    - 단건 조회이므로 쿼리 수가 적어 N+1 문제 없음
    - joinedload/selectinload로 관계 데이터를 한 번에 로드
    """
    perf = (
        db.query(Performance)
        .options(
            joinedload(Performance.genre),
            selectinload(Performance.works).joinedload(Work.composer),
            selectinload(Performance.dates),
            selectinload(Performance.performers),
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

    # order_num은 Core Table에 있으므로 raw SQL로 조회
    order_rows = db.execute(
        text("SELECT work_id, order_num FROM performance_work WHERE performance_id = :pid"),
        {"pid": performance_id},
    ).fetchall()
    order_map: dict = {r[0]: r[1] for r in order_rows if r[1] is not None}

    programs = [
        ProgramDetailItem(
            order=order_map.get(work.id),
            work=WorkRefItem(
                id=work.id,
                title=work.title,
                composer=ComposerRefItem(
                    id=work.composer.id,
                    name=work.composer.name,
                    name_ko=work.composer.name_ko,
                    birth_year=work.composer.birth_year,
                    featured=bool(work.composer.featured),
                ) if work.composer else None,
            ),
        )
        for work in perf.works
    ]

    detail = PerformanceDetail(
        id=perf.id,
        title=perf.title,
        dates=sorted([d.date for d in perf.dates]),
        venue=perf.venue,
        genre=GenreRefItem(
            id=perf.genre.id,
            name=perf.genre.name,
            parent=GenreParentItem(
                id=perf.genre.parent.id,
                name=perf.genre.parent.name,
            ) if perf.genre.parent else None,
        ) if perf.genre else None,
        poster_url=perf.poster_url,
        source_url=perf.source_url,
        ticket_url=perf.ticket_url,
        start_date=perf.start_date,
        end_date=perf.end_date,
        status=perf.status,
        performers=[
            {"id": per.id, "name": per.name}
            for per in perf.performers
        ],
        programs=programs,
    )

    return {"success": True, "message": "OK", "data": detail}
