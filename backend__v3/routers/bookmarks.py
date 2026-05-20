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

# 🔐 새로 만든 의존성 파일에서 인증 함수 임포트
from dependencies import get_current_user 

router = APIRouter(tags=["북마크"])

@router.post("/bookmarks", summary="찜 추가", response_model=MessageResponse)
def add_bookmark(
    body: BookmarkCreate, 
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user) # 🛡️ 토큰 검증 미들웨어 부착
):
    # 🚨 보안: 프론트가 보낸 body.firebase_uid 대신 위조 불가능한 토큰의 UID 사용
    uid = current_user["firebase_uid"]

    # 1. User 테이블 UPSERT (SQLAlchemy 방식)
    user = db.query(User).filter(User.firebase_uid == uid).first()
    if user:
        # 이미 존재하면 이메일과 닉네임 최신화 (Stale Data 방지)
        user.email = current_user["email"]
        user.nickname = current_user["nickname"]
    else:
        # 최초 접근이면 신규 유저 생성
        user = User(
            firebase_uid=uid, 
            email=current_user["email"], 
            nickname=current_user["nickname"]
        )
        db.add(user)
    
    # User 정보를 DB에 확정 (외래 키 제약 조건 통과를 위해)
    db.commit() 

    # 2. 공연 존재 여부 검증
    perf = db.query(Performance).filter(Performance.id == body.performance_id).first()
    if not perf:
        return JSONResponse(status_code=404, content={
            "success": False, "data": None,
            "message": "공연을 찾을 수 없습니다.", "error_code": "PERFORMANCE_NOT_FOUND",
        })

    # 3. 찜 중복 검사 및 추가
    existing = db.query(UserBookmark).filter(
        UserBookmark.firebase_uid == uid,
        UserBookmark.performance_id == body.performance_id,
    ).first()
    if existing:
        return {"success": True, "message": "이미 찜한 공연입니다."}

    bookmark = UserBookmark(firebase_uid=uid, performance_id=body.performance_id)
    db.add(bookmark)
    
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return {"success": True, "message": "이미 찜한 공연입니다."}

    return {"success": True, "message": "찜 목록에 추가되었습니다."}


@router.delete("/bookmarks", summary="찜 삭제", response_model=MessageResponse)
def remove_bookmark(
    performance_id: int = Query(..., description="공연 ID"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user) # 🛡️ 토큰 검증
):
    uid = current_user["firebase_uid"]
    
    bookmark = db.query(UserBookmark).filter(
        UserBookmark.firebase_uid == uid,
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


# 💡 프론트엔드 연동 팁: 이제 {firebase_uid} 경로 변수가 없어도 내 토큰으로 목록을 가져옵니다.
@router.get("/bookmarks", summary="내 찜 목록 조회", response_model=PaginatedResponse[UserBookmarkItem])
def get_my_bookmarks(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user) # 🛡️ 토큰 검증
):
    uid = current_user["firebase_uid"]

    bookmarks = (
        db.query(UserBookmark)
        .options(joinedload(UserBookmark.performance))
        .filter(UserBookmark.firebase_uid == uid)
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