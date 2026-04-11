"""
routers/venues.py
GET /api/venues — 공연 장소 목록 조회

역할:
- 장소별 조회 페이지의 탭 목록 데이터 제공
- 공연을 장소로 필터링하는 기능은 performances.py의 ?venue= 파라미터 담당
"""
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import distinct
from sqlalchemy.orm import Session

from database import get_db
from models import Performance
from schemas import SuccessResponse

router = APIRouter(tags=["장소"])


@router.get(
    "/venues",
    summary="공연 장소 목록 조회",
    response_model=SuccessResponse[List[str]],
)
def get_venues(db: Session = Depends(get_db)):
    """
    DB에 등록된 공연 장소 목록을 중복 없이 반환합니다.

    [왜 별도 API로 분리했는가]
    - 장소별 조회 페이지의 탭/드롭다운에서 선택지가 필요
    - 선택지를 하드코딩하면 새 공연장 추가 시 프론트 코드 수정이 필요
    - DB에서 동적으로 조회하면 seed 데이터 추가만으로 자동 반영됨
    """
    rows = (
        db.query(distinct(Performance.venue))
        .filter(
            Performance.venue != None,  # noqa: E711
            Performance.venue != "",
        )
        .order_by(Performance.venue)
        .all()
    )

    venues = [row[0] for row in rows]

    return {"success": True, "message": "OK", "data": venues}
