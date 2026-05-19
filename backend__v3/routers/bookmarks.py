"""
routers/bookmarks.py
사용자 찜(북마크) API

POST   /api/bookmarks                — 찜 추가
DELETE /api/bookmarks                — 찜 삭제 (query params: firebase_uid, performance_id)
GET    /api/bookmarks/{firebase_uid} — 찜 목록 조회
"""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from database import get_db
from models import Performance, User, UserBookmark
from schemas import BookmarkCreate, MessageResponse, PaginatedResponse, UserBookmarkItem

router = APIRouter(tags=["북마크"])


@router.post("/bookmarks", summary="찜 추가", response_model=MessageResponse)
def add_bookmark(body: BookmarkCreate, db: Session = Depends(get_db)):
    # firebase_uid는 프론트에서 받는 외부 값이므로 반드시 DB 존재 여부 검증
    user = db.query(User).filter(User.firebase_uid == body.firebase_uid).first()
    if not user:
        return JSONResponse(status_code=404, content={
            "success": False, "data": None,
            "message": "사용자를 찾을 수 없습니다.", "error_code": "USER_NOT_FOUND",
        })

    perf = db.query(Performance).filter(Performance.id == body.performance_id).first()
    if not perf:
        return JSONResponse(status_code=404, content={
            "success": False, "data": None,
            "message": "공연을 찾을 수 없습니다.", "error_code": "PERFORMANCE_NOT_FOUND",
        })

    # 중복 찜 확인: 이미 존재하면 서버 오류가 아닌 200으로 안전하게 응답
    existing = db.query(UserBookmark).filter(
        UserBookmark.firebase_uid == body.firebase_uid,
        UserBookmark.performance_id == body.performance_id,
    ).first()
    if existing:
        return {"success": True, "message": "이미 찜한 공연입니다."}

    bookmark = UserBookmark(
        firebase_uid=body.firebase_uid,
        performance_id=body.performance_id,
    )
    db.add(bookmark)
    try:
        db.commit()
    except IntegrityError:
        # 동시 요청으로 직전 중복 확인을 통과한 경우에도 DB UNIQUE 제약이 막음 — rollback 후 안전 응답
        db.rollback()
        return {"success": True, "message": "이미 찜한 공연입니다."}

    return {"success": True, "message": "찜 목록에 추가되었습니다."}


@router.delete("/bookmarks", summary="찜 삭제", response_model=MessageResponse)
def remove_bookmark(
    firebase_uid: str = Query(..., description="Firebase Auth UID"),
    performance_id: int = Query(..., description="공연 ID"),
    db: Session = Depends(get_db),
):
    bookmark = db.query(UserBookmark).filter(
        UserBookmark.firebase_uid == firebase_uid,
        UserBookmark.performance_id == performance_id,
    ).first()
    if not bookmark:
        return JSONResponse(status_code=404, content={
            "success": False, "data": None,
            "message": "북마크를 찾을 수 없습니다.", "error_code": "BOOKMARK_NOT_FOUND",
        })

    db.delete(bookmark)
    db.commit()
    return {"success": True, "message": "찜 목록에서 삭제되었습니다."}


@router.get(
    "/bookmarks/{firebase_uid}",
    summary="찜 목록 조회",
    response_model=PaginatedResponse[UserBookmarkItem],
)
def get_bookmarks(firebase_uid: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.firebase_uid == firebase_uid).first()
    if not user:
        return JSONResponse(status_code=404, content={
            "success": False, "data": None,
            "message": "사용자를 찾을 수 없습니다.", "error_code": "USER_NOT_FOUND",
        })

    # performance를 한 번에 로드 — UserBookmark.performance를 lazy load하면 N+1 발생
    bookmarks = (
        db.query(UserBookmark)
        .options(joinedload(UserBookmark.performance))
        .filter(UserBookmark.firebase_uid == firebase_uid)
        .all()
    )

    data = [
        UserBookmarkItem(
            id=b.id,
            performance_id=b.performance_id,
            title=b.performance.title,
            poster_url=b.performance.poster_url,
            start_date=b.performance.start_date,
            venue=b.performance.venue,
            status=b.performance.status,
        )
        for b in bookmarks
    ]

    return {"success": True, "message": "OK", "total": len(data), "data": data}
