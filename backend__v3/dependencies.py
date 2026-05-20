import os
import firebase_admin

from firebase_admin import credentials, auth as firebase_auth
from firebase_admin.auth import RevokedIdTokenError, ExpiredIdTokenError

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

cred_path = os.environ.get("FIREBASE_CREDENTIALS_PATH", "serviceAccountKey.json")

if not firebase_admin._apps:
    try:
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)

    except Exception as e:
        print(f"Firebase 초기화 경고 (키 파일 확인 필요): {e}")

security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        decoded_token = firebase_auth.verify_id_token(token, check_revoked=True)
        return {
            "firebase_uid": decoded_token["uid"],
            "email": decoded_token.get("email", ""),
            "nickname": decoded_token.get("name", "ClassicHub_User")
        }

    except RevokedIdTokenError:
        raise HTTPException(status_code=401, detail="차단되거나 탈퇴 처리된 계정입니다.")

    except ExpiredIdTokenError:
        raise HTTPException(status_code=401, detail="만료된 세션입니다. 다시 로그인해 주세요.")

    except Exception:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")