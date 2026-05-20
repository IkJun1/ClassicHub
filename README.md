# ClassicHub

ClassicHub는 클래식 공연 정보를 한 곳에서 조회하기 위한 웹 서비스입니다. 공연을 장르, 기간, 장소, 작곡가, 아티스트 기준으로 탐색할 수 있고, Firebase 로그인 후 관심 공연을 찜할 수 있습니다.

## 주요 기능

- 공연 목록 조회 및 상세 모달
- 장르별 / 기간별 / 장소별 공연 탐색
- 작곡가 목록 및 작곡가별 공연 조회
- 아티스트 목록 검색 및 페이지네이션
- 공연장 목록 검색 및 페이지네이션
- 공연 상태 표시: 예정 / 진행중 / 완료
- Firebase 이메일 회원가입 / 로그인 / 로그아웃
- 로그인 사용자 기준 공연 북마크(찜) 추가, 삭제, 목록 조회

## 프로젝트 구조

```text
ClassicHub/
├── backend__v3/              # FastAPI 백엔드
│   ├── main.py               # API 앱 진입점
│   ├── dependencies.py       # Firebase 토큰 검증 의존성
│   ├── routers/              # API 라우터
│   ├── models.py             # SQLAlchemy 모델
│   ├── schemas.py            # Pydantic 응답/요청 스키마
│   └── requirements.txt
├── db/
│   └── performance_platform.db
├── front_v3/                 # 정적 프론트엔드
│   ├── main.html
│   ├── main.js
│   ├── main.css
│   ├── firebase-config.js    # Firebase Web Config 입력 파일
│   └── *.html
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

Firebase 인증 기능을 사용하려면 Firebase Admin SDK도 필요합니다.
현재 환경에 없다면 추가로 설치합니다.

```bash
pip install firebase-admin
```

### 2. Firebase Web Config 설정

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

### 3. Firebase Service Account Key 설정

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

인증이 필요한 API는 프론트에서 Firebase ID Token을 아래 형태로 전달합니다.

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
