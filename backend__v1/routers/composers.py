"""
routers/composers.py
GET /api/composers — 작곡가 목록 조회

주요 기능:
- era 파라미터로 시대별 필터 (작곡가.html ?era=낭만)
- featured 파라미터로 UI 빠른 버튼용 주요 작곡가만 필터
- keyword 파라미터로 이름 부분 검색 (영문·한국어 모두)
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import Composer, Work
from schemas import ComposerItem, PaginatedResponse

router = APIRouter(tags=["작곡가"])

# 허용 시대 값 (작곡가.html 메가메뉴와 동일)
VALID_ERAS = {"바로크", "고전", "낭만", "근현대"}


@router.get(
    "/composers",
    summary="작곡가 목록 조회",
    response_model=PaginatedResponse[ComposerItem],
)
def get_composers(
    era: Optional[str] = Query(
        None,
        description="시대 필터: 바로크 | 고전 | 낭만 | 근현대",
    ),
    featured: Optional[bool] = Query(
        None,
        description="true이면 UI 빠른 버튼용 주요 작곡가만 반환",
    ),
    keyword: Optional[str] = Query(
        None,
        description="작곡가 이름 부분 검색 (영문·한국어 모두 검색)",
    ),
    db: Session = Depends(get_db),
):
    """
    작곡가 목록을 반환합니다.

    [사용 화면]
    - 작곡가.html: ?era=낭만 처럼 URL 파라미터로 시대 필터링
    - 메인 화면 빠른 버튼: ?featured=true 로 주요 작곡가만
    - 공연 검색 필터: ?keyword=베토벤 로 이름 검색

    [era 필드를 추가한 이유]
    - classic-api에는 Composer.era가 없었음
    - 작곡가.html의 바로크/고전/낭만/근현대 탭이 URL ?era= 파라미터로 동작하므로
      DB에 era 저장 및 필터가 반드시 필요
    """
    # era 유효성 검증 (입력한 경우에만)
    if era and era not in VALID_ERAS:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "data": None,
                "message": f"era 값은 {' | '.join(VALID_ERAS)} 중 하나여야 합니다.",
                "error_code": "INVALID_PARAMETER",
            },
        )

    query = db.query(Composer)

    if era:
        query = query.filter(Composer.era == era)

    if featured is True:
        query = query.filter(Composer.featured == True)  # noqa: E712

    if keyword:
        query = query.filter(
            Composer.name.ilike(f"%{keyword}%") |
            Composer.name_ko.ilike(f"%{keyword}%")
        )

    composers = query.order_by(Composer.name).all()

    # 작곡가별 등록된 곡 수 집계 (work_count)
    work_counts: dict = dict(
        db.query(Work.composer_id, func.count(Work.id))
        .group_by(Work.composer_id)
        .all()
    )

    return {
        "success": True,
        "message": "OK",
        "total": len(composers),
        "data": [
            ComposerItem(
                id=c.id,
                name=c.name,
                name_ko=c.name_ko,
                era=c.era,
                period=c.era,           # era alias (프론트 호환)
                featured=bool(c.featured),
                birth_year=c.birth_year,
                death_year=c.death_year,
                work_count=work_counts.get(c.id, 0),
            )
            for c in composers
        ],
    }
