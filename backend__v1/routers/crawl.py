"""
routers/crawl.py
POST /api/crawl — 수동 크롤링 실행 (관리용)

[보안 주의]
운영 환경에서는 이 엔드포인트에 반드시 IP 화이트리스트 또는 관리자 인증 적용 필요.
인증 없이 노출되면 무단 크롤링 실행이 가능함.

[현재 구현 범위]
실제 크롤링 로직은 추후 구현 예정.
현재는 API 명세서 응답 형식에 맞는 구조만 반환.

[409 CRAWL_ALREADY_RUNNING 처리]
threading.Lock으로 중복 실행을 방지.
FastAPI는 멀티스레드이므로 플래그 확인/설정을 원자적으로 처리해야 함.
"""
import threading
import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from schemas import CrawlRequest, CrawlResult, SuccessResponse

router = APIRouter(tags=["크롤링"])

_crawl_lock = threading.Lock()
_is_crawling = False

VALID_SITES = {"all", "site_1", "site_2"}


@router.post(
    "/crawl",
    summary="수동 크롤링 실행 (관리용)",
    response_model=SuccessResponse[CrawlResult],
)
def run_crawl(body: CrawlRequest):
    """
    지정한 사이트에서 공연 정보를 크롤링합니다.

    [site 값]
    - "all"    : 모든 사이트
    - "site_1" : 사이트 1만
    - "site_2" : 사이트 2만
    """
    global _is_crawling

    if body.site not in VALID_SITES:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "data": None,
                "message": "site 값은 all | site_1 | site_2 중 하나여야 합니다.",
                "error_code": "INVALID_PARAMETER",
            },
        )

    with _crawl_lock:
        if _is_crawling:
            return JSONResponse(
                status_code=409,
                content={
                    "success": False,
                    "data": None,
                    "message": "크롤링이 이미 실행 중입니다. 잠시 후 다시 시도해 주세요.",
                    "error_code": "CRAWL_ALREADY_RUNNING",
                },
            )
        _is_crawling = True

    try:
        start = time.time()
        # TODO: 실제 크롤링 로직 구현
        result = CrawlResult(
            total_crawled=0,
            inserted=0,
            updated=0,
            skipped_duplicates=0,
            errors=0,
            duration_sec=round(time.time() - start, 3),
        )
    finally:
        with _crawl_lock:
            _is_crawling = False

    return {"success": True, "message": "크롤링이 완료되었습니다.", "data": result}
