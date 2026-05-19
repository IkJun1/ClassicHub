"""
routers/crawl.py
POST /api/crawl — ETL 프로세스 수동 실행 (관리용 trigger)

[crawl.py의 역할]
직접 크롤링/데이터 가공/DB INSERT를 하지 않는다.
실제 데이터 적재 책임은 etl_loader.py의 run_etl_process()에 있다.
이 라우터는 그것을 호출하는 trigger 역할만 수행한다.

[etl_loader.py import 안전 처리]
etl_loader.py가 없거나 의존성 오류가 있어도 서버 자체는 정상 기동되어야 한다.
_etl_available 플래그로 가용 여부를 확인하고, 불가 시 503을 반환한다.

[보안 주의]
운영 환경에서는 이 엔드포인트에 반드시 IP 화이트리스트 또는 관리자 인증 적용 필요.
"""
import threading

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from schemas import CrawlRequest, MessageResponse

router = APIRouter(tags=["크롤링"])

# etl_loader.py 미존재/import 오류 시 서버 기동이 죽지 않도록 안전하게 처리
# 파일이 배치되기 전에도 서버가 정상 동작해야 하므로 ImportError를 조용히 처리
try:
    from etl_loader import run_etl_process as _run_etl_process
    _etl_available = True
except ImportError:
    _etl_available = False
    _run_etl_process = None

_crawl_lock = threading.Lock()
_is_crawling = False


@router.post(
    "/crawl",
    summary="ETL 프로세스 수동 실행 (관리용)",
    response_model=MessageResponse,
)
def run_crawl(body: CrawlRequest):
    """
    etl_loader.py의 run_etl_process를 trigger합니다.
    직접 크롤링/INSERT를 하지 않고 ETL 파이프라인에 위임합니다.
    """
    global _is_crawling

    # etl_loader.py가 없으면 503 반환 (서버는 정상, 해당 기능만 비활성화)
    if not _etl_available:
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "data": None,
                "message": "etl_loader.py가 없어 크롤링을 실행할 수 없습니다.",
                "error_code": "ETL_NOT_AVAILABLE",
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
        # run_etl_process는 site 파라미터를 지원하지 않음
        # body.site는 API 호환용으로 수신하되 실행 시에는 전달하지 않음
        _run_etl_process()
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "data": None,
                "message": f"ETL 실행 중 오류가 발생했습니다: {e}",
                "error_code": "ETL_ERROR",
            },
        )
    finally:
        with _crawl_lock:
            _is_crawling = False

    return {"success": True, "message": "ETL 프로세스가 완료되었습니다."}
