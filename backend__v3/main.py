"""
main.py
FastAPI 앱 진입점

실행 방법:
    cd backend_v1/app
    uvicorn main:app --reload --port 8000

    또는 backend_v1/ 루트에서:
    uvicorn app.main:app --reload --port 8000

API 문서:
    http://localhost:8000/docs     (Swagger UI — 팀원이 직접 테스트 가능)
    http://localhost:8000/redoc    (ReDoc)
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import database
import models
from routers import artists, bookmarks, composers, crawl, genres, performances, venues


# ── 앱 생명주기 ───────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    DB 테이블 자동 생성 비활성화.
    performance_platform.db는 조원의 create_db.py / etl_loader.py가 생성하므로
    앱 시작 시 create_all을 실행하지 않는다.
    """
    yield


# ── FastAPI 앱 생성 ───────────────────────────────────────────────────────────
app = FastAPI(
    title="클래식 공연 통합 검색 플랫폼 API",
    description=(
        "클래식 공연 정보를 통합 검색·필터링하는 RESTful API.\n\n"
        "### Base URL\n"
        "`http://localhost:8000/api`\n\n"
        "### 주요 엔드포인트\n"
        "- `GET /api/performances` — 공연 목록 (검색·필터·정렬·페이지네이션)\n"
        "- `GET /api/performances/recent` — 최근 공연 (메인 화면)\n"
        "- `GET /api/performances/{id}` — 공연 상세\n"
        "- `GET /api/genres` — 장르 목록\n"
        "- `GET /api/composers` — 작곡가 목록 (era 시대 필터 지원)\n"
        "- `GET /api/artists` — 아티스트 목록 (role 역할 필터 지원)\n"
        "- `GET /api/venues` — 공연 장소 목록\n"
        "- `POST /api/crawl` — 크롤링 수동 실행 (관리용)\n\n"
        "### 공통 응답 형식\n"
        "```json\n"
        '{"success": true, "message": "OK", "data": ...}\n'
        "```"
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# ── CORS 미들웨어 ─────────────────────────────────────────────────────────────
# 변경 사유:
# - 기존 allow_origins=["*"] 환경에서는 보안상 인증 토큰(Authorization 헤더)을 주고받을 수 없습니다.
# - 파이어베이스 인증 도입 및 토큰 통신을 위해 allow_credentials를 True로 변경하고,
#   프론트엔드가 실행되는 로컬 개발 서버 주소(Live Server 등)를 명시적으로 허용해야 합니다.
# - 주의: 로컬 테스트 시 반드시 file:// 경로가 아닌 http://localhost:5500 환경에서 브라우저를 열어야 합니다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5500",    # VS Code Live Server 기본 도메인 주소
        "http://127.0.0.1:5500",   # 로컬 루프백 IP 주소 대응
    ],
    allow_credentials=True,         # 인증 토큰(Authorization 헤더) 및 쿠키 통신 허용
    allow_methods=["*"],            # GET, POST, DELETE 등 모든 HTTP 메서드 허용
    allow_headers=["*"],            # Authorization, Content-Type 등 모든 헤더 허용
)


# ── 전역 예외 핸들러 ──────────────────────────────────────────────────────────

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Pydantic 검증 실패 (기본 422) → 명세서 형식의 400으로 변환.
    예: page=-1, per_page=999 등 Query 파라미터 범위 위반
    """
    return JSONResponse(
        status_code=400,
        content={
            "success": False,
            "data": None,
            "message": "잘못된 파라미터 값입니다.",
            "error_code": "INVALID_PARAMETER",
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """처리되지 않은 모든 예외 → 500 반환. 스택 트레이스는 응답에 포함하지 않음."""
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "data": None,
            "message": "서버 내부 오류가 발생했습니다.",
            "error_code": "SERVER_ERROR",
        },
    )


# ── 라우터 등록 ───────────────────────────────────────────────────────────────
#
# ⚠️ performances 라우터를 가장 먼저 등록해야 하는 이유:
#    /api/performances/recent (정적) vs /api/performances/{id} (동적) 경로가
#    같은 라우터 파일 안에서 선언 순서로 우선순위가 결정됨.
#    이미 파일 내부에서 recent → 목록 → {id} 순으로 선언되어 있으므로 안전.
#
app.include_router(performances.router, prefix="/api")
app.include_router(genres.router,       prefix="/api")
app.include_router(composers.router,    prefix="/api")
app.include_router(artists.router,      prefix="/api")
app.include_router(venues.router,       prefix="/api")
app.include_router(crawl.router,        prefix="/api")
app.include_router(bookmarks.router,    prefix="/api")


# ── 헬스체크 ─────────────────────────────────────────────────────────────────
@app.get("/", tags=["상태"])
def health_check():
    """서버 동작 확인용 엔드포인트"""
    return {"success": True, "message": "클래식 공연 API 서버가 실행 중입니다."}
