# 🚀 시스템 아키텍처 개편 및 24시간 자동화 구축 가이드

본 프로젝트의 데이터베이스 아키텍처 변경 및 24시간 무인 데이터 수집 자동화(스케줄러) 구축이 성공적으로 완료되었습니다.

## 1. 시스템 아키텍처 전면 개편 내역 (Architecture Review)

### 🔻 [AS-IS] 로컬 의존형 구조

* **개별 PC 환경:** `SQLite` 파일(`sqlite.db`) 기반 데이터 저장.
* **제한적 스케줄링:** 개발자 로컬 PC가 가동 중일 때만 `while True` 루프로 동작.
* **단점:** 팀원 간 실시간 데이터 동기화 불가 및 로컬 환경 의존성.

### 🔵 [TO-BE] 서버리스 클라우드 통합 구조

* **Database:** `Supabase(PostgreSQL)` 클라우드 DB로 전면 마이그레이션 적용 완료. (모든 팀원이 동일한 실시간 데이터 엔드포인트 공유)
* **Automation:** `GitHub Actions` 기반의 Serverless 아키텍처 도입. 로컬 PC 가동 여부와 무관하게 GitHub 클라우드 서버에서 매일 02:00(KST) KOPIS API 데이터를 자동 수집 및 DB UPSERT(중복 방지 적재) 수행.

---

## 2. 스케줄러 자동화를 위한 핵심 추가 및 변경 사항

새로운 아키텍처를 지원하기 위해 `main` 브랜치에 병합된 핵심 파일은 다음과 같습니다.

* **`.github/workflows/daily_crawler.yml` (신규)**
* GitHub Actions 워크플로우 정의 파일.
* UTC 기준 17:00 (한국 시간 새벽 02:00)에 Ubuntu 가상 서버를 기동하여 크롤링 파이프라인을 1회성으로 자동 실행하도록 트리거(`cron`) 설정.


* **`DB/run_batch_once.py` (신규)**
* 기존 무한 루프 스케줄러를 우회하여, GitHub Actions 환경에서 단발성(1회)으로 배치 작업을 안전하게 실행하고 프로세스를 종료(`sys.exit`)하도록 설계된 래퍼(Wrapper) 스크립트.


* **`DB/daily_scheduler.py` (리팩토링)**
* 실무 운영 환경(새벽 2시 가동)과 테스트 환경(1분 단위 가동)을 모듈화하여 분리.
* 로그 출력을 직관적인 시스템 표준(`[INFO]`, `[ERROR]`)으로 정제.


* **`requirements.txt` (업데이트)**
* 클라우드 연동 및 서버 구동에 필요한 `firebase-admin`, `psycopg2-binary` 등 필수 의존성 패키지 명세 추가 완료.



---

## 3. 팀장 (Repository Owner) 최종 수행 방법론 (Action Item)

> 🚨 **[IMPORTANT]**
> 스케줄러 코드 로직은 완벽히 구성되어 `main`에 병합되었으나, 보안 정책상 자동화 로봇이 DB와 API에 접근하기 위한 환경변수(Secrets)는 **Repository Owner**만이 등록할 수 있습니다. 따라서 스케줄러 작동을 위해서는 다음의 절차를 관리자가 수행해야 합니다.

### 🔐 환경변수(Secrets) 등록 절차

1. **보안 설정 진입:** 상단 탭에서 **[Settings]** 클릭 
   ➔ 좌측 사이드바 하단의 **[Secrets and variables]** 탭 확장 
   ➔ [Actions]를 클릭합니다.

2. **데이터베이스 URL 등록:**
* **[New repository secret]** 초록색 버튼 클릭.
* **Name:** `DATABASE_URL`
* **Secret:** Supabase PostgreSQL 연결 주소.
* [Add secret]을 클릭하여 저장.

3. **KOPIS API 키 등록:**
* 다시 **[New repository secret]** 버튼 클릭.
* **Name:** `KOPIS_API_KEY`
* **Secret:** 공공데이터포털 KOPIS API 키값.
* [Add secret]을 클릭하여 저장.

---

### 가동 테스트 (선택 사항)

> 💡 **[TIP]** > 설정이 끝난 후 수동으로 파이프라인을 실행하여 정상 동작을 검증할 수 있습니다.

1. 상단의 **[Actions]** 탭 이동 ➔ 좌측 워크플로우 목록에서 `KOPIS Daily ETL Pipeline` 선택.
2. 우측 **[Run workflow]** 버튼을 수동으로 클릭하여, 가상 서버가 정상적으로 DB에 데이터를 적재하는지 실시간 로그로 점검.

> 위 절차가 모두 완료되는 즉시, 본 프로젝트의 24시간 무인 데이터 수집 및 클라우드 동기화 파이프라인은 완전한 **운영(Production)** 상태로 전환됩니다.