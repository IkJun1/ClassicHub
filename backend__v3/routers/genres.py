"""
routers/genres.py
GET /api/genres — 장르 목록 조회 (계층 구조)

이 API의 역할:
- 프론트 장르 탭 UI에서 표시할 장르 이름 목록 제공
- 상위 장르(교향곡) → 하위 장르(합창 교향곡) 계층 구조 반환

이 파일에서 담당하지 않는 것:
- 실제 공연을 장르로 필터링하는 기능 → performances.py의 ?genre= 파라미터
"""
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, selectinload

from database import get_db
from models import Genre
from schemas import GenreChildItem, GenreItem, PaginatedResponse

router = APIRouter(tags=["장르"])


@router.get(
    "/genres",
    summary="장르 목록 조회 (계층 구조)",
    response_model=PaginatedResponse[GenreItem],
)
def get_genres(db: Session = Depends(get_db)):
    """
    장르 목록을 계층 구조로 반환합니다.

    [반환 구조]
    상위 장르(parent_id=NULL) → children 배열에 하위 장르 포함

    [왜 계층 구조인가]
    - "협주곡" 탭 선택 시 하위 분류(피아노 협주곡, 바이올린 협주곡)를
      드롭다운으로 보여주는 UI 확장에 대비
    - 지금은 상위 장르만 탭으로 사용하더라도 구조를 미리 갖춰두는 것이 유지보수에 유리

    [왜 selectinload를 사용하는가]
    - children을 lazy load하면 장르 수만큼 쿼리가 발생 (N+1 문제)
    - selectinload로 자식들을 한 번에 IN 쿼리로 로드
    """
    top_genres = (
        db.query(Genre)
        .options(selectinload(Genre.children))
        .filter(Genre.parent_id == None)  # noqa: E711 — None 비교는 IS NULL
        .order_by(Genre.id)
        .all()
    )

    result = [
        GenreItem(
            id=g.id,
            name=g.name,
            name_en=None,      # DB 스키마(ERD_v2)에 name_en 컬럼 없음
            parent_id=g.parent_id,
            children=[
                GenreChildItem(
                    id=child.id,
                    name=child.name,
                    name_en=None,  # DB 스키마(ERD_v2)에 name_en 컬럼 없음
                    parent_id=child.parent_id,
                )
                for child in sorted(g.children, key=lambda x: x.id)
            ],
        )
        for g in top_genres
    ]

    return {"success": True, "message": "OK", "total": len(result), "data": result}
