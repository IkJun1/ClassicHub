"""
schemas.py
Pydantic v2 Request/Response 스키마 정의

왜 DB 모델(models.py)과 분리했는가:
- DB 내부 구조가 바뀌어도 API 응답 형식을 독립적으로 유지할 수 있음
- 프론트가 필요한 필드만 골라서 보낼 수 있음 (DB 컬럼 전체 노출 방지)
- Swagger 자동 문서에서 응답 형태를 명확히 보여줄 수 있음

공통 응답 규칙:
- 성공: {"success": true, "message": "OK", "data": ...}
- 목록: {"success": true, "message": "OK", "total": N, "data": [...]}
- 실패: {"success": false, "data": null, "message": "...", "error_code": "..."}
"""
from typing import Generic, List, Optional, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


# ─────────────────────────────────────────────────────────────────────────────
# 공통 응답 스키마
# ─────────────────────────────────────────────────────────────────────────────

class SuccessResponse(BaseModel, Generic[T]):
    """
    단건 조회 / 일반 목록용 성공 응답
    예: GET /api/genres, GET /api/performances/{id}
    """
    success: bool = True
    message: str = "OK"
    data: T


class PaginatedResponse(BaseModel, Generic[T]):
    """
    페이지네이션이 필요한 목록 응답
    프론트엔드는 total 값으로 전체 페이지 수를 직접 계산함.
    예: GET /api/performances
    """
    success: bool = True
    message: str = "OK"
    total: int
    data: List[T]


class ErrorResponse(BaseModel):
    """
    에러 응답
    error_code를 항상 포함하는 이유:
    - 프론트가 에러 메시지 문자열 파싱 대신 코드로 분기 처리 가능
    - 다국어 지원 시 error_code 기준으로 번역 가능
    """
    success: bool = False
    data: None = None
    message: str
    error_code: str


class MessageResponse(BaseModel):
    """처리 결과만 반환 (POST /api/crawl 등)"""
    success: bool = True
    message: str


# ─────────────────────────────────────────────────────────────────────────────
# 공연 관련 스키마
# ─────────────────────────────────────────────────────────────────────────────

class ProgramSummaryItem(BaseModel):
    """공연 목록 카드에 표시할 프로그램 요약 (작곡가 + 곡명)"""
    composer: str   # 작곡가 영문 이름
    work: str       # 곡 제목


class ComposerRefItem(BaseModel):
    """programs 중첩 구조에서 사용하는 작곡가 참조 객체"""
    id: int
    name: str
    name_ko: Optional[str] = None
    birth_year: Optional[int] = None
    featured: bool = False


class WorkRefItem(BaseModel):
    """programs 중첩 구조에서 사용하는 곡 참조 객체"""
    id: int
    title: str
    composer: Optional[ComposerRefItem] = None


class ProgramDetailItem(BaseModel):
    """공연 상세 페이지의 프로그램 항목 (순서 + 곡 중첩 객체)"""
    order: Optional[int] = None   # 프로그램 연주 순서
    work: WorkRefItem             # 곡 정보 (제목 + 작곡가 중첩)


class PerformerItem(BaseModel):
    """공연 상세의 연주자 항목"""
    id: int
    name: str


class PerformanceSummary(BaseModel):
    """
    공연 목록 카드용 스키마
    사용 API: GET /api/performances
    사용 화면: 장르별·장소별·기간별 조회 결과 카드

    poster_url을 포함한 이유:
    - 공연 카드에서 포스터 이미지를 보여주기 위해 필요
    - 없는 경우 null이므로 프론트에서 placeholder 처리
    """
    id: int
    title: str
    dates: List[str]                   # 예: ["2026-05-10", "2026-05-11"]
    venue: Optional[str] = None
    genre: Optional[str] = None
    genre_id: Optional[int] = None
    poster_url: Optional[str] = None   # 포스터 이미지 URL
    source_url: Optional[str] = None
    programs: List[ProgramSummaryItem] = []
    img: Optional[str] = None          # poster_url alias (프론트 호환)
    date: Optional[str] = None         # dates[0] alias (프론트 호환)


class GenreParentItem(BaseModel):
    """장르 참조 객체의 상위 장르"""
    id: int
    name: str


class GenreRefItem(BaseModel):
    """공연 상세에서 genre 필드에 사용하는 중첩 객체"""
    id: int
    name: str
    parent: Optional[GenreParentItem] = None


class PerformanceDetail(BaseModel):
    """
    공연 상세 페이지용 스키마
    사용 API: GET /api/performances/{id}
    목록 스키마보다 더 자세한 정보 포함 (performers, ticket_url 등)
    """
    id: int
    title: str
    dates: List[str]
    venue: Optional[str] = None
    genre: Optional[GenreRefItem] = None
    poster_url: Optional[str] = None
    source_url: Optional[str] = None
    ticket_url: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    status: Optional[str] = None
    performers: List[PerformerItem] = []
    programs: List[ProgramDetailItem] = []


class RecentPerformanceSummary(BaseModel):
    """
    메인 화면 최근 공연 목록용 스키마
    사용 API: GET /api/performances/recent
    D-Day 섹션 카드에 poster_url이 필요하므로 포함
    """
    id: int
    title: str
    dates: List[str]
    venue: Optional[str] = None
    genre: Optional[str] = None
    poster_url: Optional[str] = None
    programs: List[ProgramSummaryItem] = []
    img: Optional[str] = None          # poster_url alias (프론트 호환)
    date: Optional[str] = None         # dates[0] alias (프론트 호환)


# ─────────────────────────────────────────────────────────────────────────────
# 작곡가 스키마
# ─────────────────────────────────────────────────────────────────────────────

class ComposerItem(BaseModel):
    """
    작곡가 항목
    era 필드를 포함한 이유:
    - 작곡가.html이 ?era=낭만 파라미터로 필터링하므로 응답에도 시대 포함
    """
    id: int
    name: str                          # 영문 이름 (예: Beethoven)
    name_ko: Optional[str] = None      # 한국어 이름 (예: 베토벤)
    era: Optional[str] = None          # 시대: 바로크/고전/낭만/근현대
    period: Optional[str] = None       # era alias (프론트 호환)
    featured: bool
    birth_year: Optional[int] = None
    death_year: Optional[int] = None
    work_count: Optional[int] = None   # 등록된 곡 수

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# 장르 스키마
# ─────────────────────────────────────────────────────────────────────────────

class GenreChildItem(BaseModel):
    """하위 장르 항목 (예: 협주곡 → 피아노 협주곡)"""
    id: int
    name: str
    name_en: Optional[str] = None
    parent_id: Optional[int] = None

    model_config = {"from_attributes": True}


class GenreItem(BaseModel):
    """
    상위 장르 항목 (하위 장르 배열 포함)
    사용 API: GET /api/genres
    프론트 장르 탭 UI를 계층 구조로 표현하기 위해 children 포함
    """
    id: int
    name: str
    name_en: Optional[str] = None
    parent_id: Optional[int] = None
    children: List[GenreChildItem] = []

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# 아티스트 스키마
# ─────────────────────────────────────────────────────────────────────────────

class ArtistItem(BaseModel):
    """
    아티스트 항목
    사용 API: GET /api/artists
    role로 역할 필터링 지원 (지휘자/오케스트라/솔리스트/악장)
    """
    id: int
    name: str
    role: Optional[str] = None

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# 크롤링 스키마
# ─────────────────────────────────────────────────────────────────────────────

class CrawlRequest(BaseModel):
    """POST /api/crawl 요청 바디"""
    site: str   # "all" | "site_1" | "site_2"


class CrawlResult(BaseModel):
    """크롤링 실행 결과"""
    total_crawled: int
    inserted: int
    updated: int
    skipped_duplicates: int
    errors: int
    duration_sec: float
