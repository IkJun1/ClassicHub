"""
routers/artists.py
GET /api/artists — 아티스트 목록 조회

아티스트.html에서 역할별 탭(지휘자/오케스트라/솔리스트/악장)에 사용
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from models import Artist
from schemas import ArtistItem, SuccessResponse

router = APIRouter(tags=["아티스트"])


@router.get(
    "/artists",
    summary="아티스트 목록 조회",
    response_model=SuccessResponse[List[ArtistItem]],
)
def get_artists(
    role: Optional[str] = Query(
        None,
        description="역할 필터 (예: 지휘자, 오케스트라, 솔리스트, 악장)",
    ),
    keyword: Optional[str] = Query(
        None,
        description="이름 부분 검색",
    ),
    db: Session = Depends(get_db),
):
    """
    아티스트 목록을 반환합니다.

    [사용 화면]
    - 아티스트.html: ?role=지휘자 처럼 URL 파라미터로 역할 필터링
    - 두 파라미터 생략 시 전체 아티스트 반환
    """
    query = db.query(Artist)

    if role:
        query = query.filter(Artist.role == role)

    if keyword:
        query = query.filter(Artist.name.like(f"%{keyword}%"))

    artists = query.order_by(Artist.name).all()

    return {
        "success": True,
        "message": "OK",
        "data": [
            ArtistItem(id=a.id, name=a.name, role=a.role)
            for a in artists
        ],
    }
