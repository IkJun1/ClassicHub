# ClassicHub

ClassicHub는 클래식 공연 정보를 한 곳에서 조회하기 위한 웹 서비스입니다. 
공연을 장르, 기간, 장소, 작곡가, 아티스트 기준으로 탐색할 수 있고, Firebase 로그인 후 관심 공연을 찜할 수 있습니다.

(최근 업데이트: 팀원 모두가 실시간으로 데이터를 공유할 수 있는 클라우드 기반 Supabase(PostgreSQL) 아키텍처 및 
서버리스 24시간 무인 데이터 수집 자동화 파이프라인이 성공적으로 구축되었습니다.)

## 주요 기능

- 공연 목록 조회 및 상세 모달
- 장르별 / 기간별 / 장소별 공연 탐색
- 작곡가 목록 및 작곡가별 공연 조회
- 아티스트 목록 검색 및 페이지네이션
- 공연장 목록 검색 및 페이지네이션
- 공연 상태 표시: 예정 / 진행중 / 완료
- Firebase 이메일 회원가입 / 로그인 / 로그아웃
- 로그인 사용자 기준 공연 북마크(찜) 추가, 삭제, 목록 조회
- KOPIS API 기반 24시간 무인 데이터 수집 파이프라인 (GitHub Actions)
- 실시간 동기화 지원 클라우드 데이터베이스 (Supabase PostgreSQL)

## 프로젝트 구조

```text
ClassicHub/
├── .github/workflows/        # GitHub Actions 서버리스 자동화 스케줄러
├── .env                      # 환경변수 설정 파일 (프로젝트 최상단 단일 관리)
├── backend__v3/              # FastAPI 백엔드
│   ├── main.py               # API 앱 진입점
│   ├── dependencies.py       # Firebase 토큰 검증 및 Supabase User 강제 동기화(UPSERT) 미들웨어
│   ├── database.py           # [MODIFIED] Supabase PostgreSQL 연결 엔진 
│   ├── routers/              # API 라우터 (비즈니스 로직)
│   ├── models.py             # SQLAlchemy 모델 (클래스 설계)
│   └── requirements.txt      # [MODIFIED] psycopg2-binary, python-dotenv 등 의존성 추가
├── DB/                       # ETL 데이터 수집 및 정제 파이프라인
│   ├── etl_loader.py         # SQLAlchemy 기반 DB UPSERT 로직
│   ├── daily_scheduler.py    # 로컬 테스트용 스케줄러
│   └── run_batch_once.py     # GitHub Actions용 1회성 배치 실행기
├── front_v3/                 # 정적 프론트엔드
│   ├── firebase-config.js    # Firebase Web Config 입력 파일
│   └── ... (html, js, css)
├── serve_all.py              # 백엔드 + 프론트 동시 서빙 스크립트
└── README.md
```

## 실행 준비

### 1. Python 가상환경 준비

```bash
cd ClassicHub
cd backend__v3
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 환경변수(.env) 설정
프로젝트 최상단 폴더(ClassicHub/)에 .env 파일을 만들고 아래 정보들을 입력해야 합니다. (절대 Git에 커밋하지 마세요!)

```bash
# Supabase PostgreSQL 연결 주소
DATABASE_URL="postgresql://[USER]:[PASSWORD]@[HOST]:[PORT]/[DB_NAME]"

# KOPIS API 키 (데이터 수집 파이프라인용)
KOPIS_API_KEY="발급받은_오픈API_키"

# Firebase 관리자 키 경로 (기본값)
FIREBASE_CREDENTIALS_PATH="backend__v3/serviceAccountKey.json"
```

### 3. Firebase Web Config 설정

프론트 로그인/회원가입을 위해 `front_v3/firebase-config.js`에 Firebase Web App 설정값을 입력합니다.

```js
export const firebaseConfig = {
    apiKey: "...",
    authDomain: "...",
    projectId: "...",
    appId: "...",
    storageBucket: "...",
    messagingSenderId: "...",
};
```

Firebase Console에서 확인 위치:

```text
Project settings → General → Your apps(Web)
```

또한 Firebase Console에서 이메일 로그인을 활성화해야 합니다.

```text
Authentication → Sign-in method → Email/Password → Enable
```

### 4. Firebase Service Account Key 설정

백엔드가 Firebase ID Token을 검증하려면 서비스 계정 키가 필요합니다.

Firebase Console에서 다운로드:

```text
Project settings → Service accounts → Generate new private key
```

다운로드한 JSON 파일을 아래 위치에 둡니다.

```text
backend__v3/serviceAccountKey.json
```

> 주의: `serviceAccountKey.json`은 관리자 비밀 키입니다. 절대 Git에 커밋하지 마세요.

## 실행 방법

### 권장: 백엔드와 프론트를 함께 실행

프로젝트 루트에서 실행합니다.

```bash
backend__v3/.venv/bin/python serve_all.py
```

브라우저에서 접속:

```text
http://127.0.0.1:8000/app/main.html
```

API는 그대로 아래 경로에서 제공됩니다.

```text
http://127.0.0.1:8000/api/...
```

이 방식은 프론트와 백엔드가 같은 origin에서 동작하므로 CORS 문제를 피할 수 있습니다.

### 백엔드만 실행

```bash
cd backend__v3
source .venv/bin/activate
python -m uvicorn main:app --reload --port 8000
```

API 문서:

```text
http://127.0.0.1:8000/docs
```

프론트는 `front_v3/*.html`을 직접 열거나 별도 정적 서버로 열 수 있습니다.
단, Live Server를 사용할 경우 파일 감지로 자동 새로고침이 반복될 수 있으므로 `serve_all.py` 사용을 권장합니다.

## 자동 데이터 수집
기존 로컬 기반의 크롤링을 완전히 자동화했습니다.

운영 배포 (GitHub Actions): 리포지토리에 코드가 푸시되면 매일 자동으로 run_batch_once.py가 가동되어 
KOPIS 최신 데이터를 수집하고 Supabase에 무결성(UPSERT)을 유지하며 적재합니다. 팀원 개인 PC가 꺼져있어도 서버리스로 돌아갑니다!

* **배치 갱신율 모니터링 지원:** 데이터 적재 시 `Performance` 테이블의 `updated_at` 컬럼이 자동 갱신되도록 설계되어 있습니다. 이를 통해 매일 자정에 실행되는 스케줄러가 실제로 몇 건의 기존 데이터를 최신화했는지 파악하고 모니터링할 수 있습니다.

로컬 테스트: 필요한 경우 터미널에서 python DB/daily_scheduler.py를 직접 실행하여 정상 작동 여부를 손쉽게 확인할 수 있습니다.

## 주요 API

| Method | Path | 설명 | 인증 |
|---|---|---|---|
| GET | `/api/performances` | 공연 목록 조회 | 불필요 |
| GET | `/api/performances/{id}` | 공연 상세 조회 | 불필요 |
| GET | `/api/genres` | 장르 목록 조회 | 불필요 |
| GET | `/api/composers` | 작곡가 목록 조회 | 불필요 |
| GET | `/api/artists` | 아티스트 목록 조회 | 불필요 |
| GET | `/api/venues` | 공연장 목록 조회 | 불필요 |
| POST | `/api/bookmarks` | 찜 추가 | 필요 |
| DELETE | `/api/bookmarks` | 찜 삭제 | 필요 |
| GET | `/api/bookmarks` | 내 찜 목록 조회 | 필요 |

## 인증 및 데이터 동기화 (Firebase + Supabase)

본 프로젝트는 Firebase Authentication을 통해 발급받은 JWT(ID Token)를 사용하여 백엔드 API 인증을 수행합니다.

* **자동 동기화 미들웨어 (UPSERT):** 인증이 필요한 모든 API는 내부적으로 `get_current_user` 미들웨어를 거칩니다. 
  토큰 검증에 통과하는 즉시 Supabase의 `User` 테이블에 해당 유저 정보가 자동으로 동기화(생성 및 최신화)됩니다. 
  
  이를 통해 분산 아키텍처 환경에서 발생할 수 있는 외래키(FK) 참조 무결성 충돌을 완벽히 방어합니다. 
  프론트엔드에서는 별도의 '유저 데이터 생성 API'를 호출할 필요가 없습니다.

* **API 토큰 전달 방법:** 인증이 필요한 API(예: 찜하기 등)를 호출할 때는, 프론트엔드에서 HTTP 요청 헤더(Header)에 
  아래와 같은 형식으로 Firebase ID Token을 담아 전달해야 합니다.

```http
Authorization: Bearer <Firebase ID Token>
```

## 사용 흐름

1. `serve_all.py` 실행
2. `http://127.0.0.1:8000/app/main.html` 접속
3. 우측 상단 계정 아이콘 클릭
4. 회원가입 또는 로그인
5. 공연 카드 클릭
6. 상세 모달에서 `♡ 찜하기` 클릭
7. 계정 모달의 `내 찜`에서 북마크 목록 확인

## 팀원

- 20221367 임익준
- 20231348 김혜연
- 20231346 김푸름
- 20221360 김종현
- 20231337 신지한
