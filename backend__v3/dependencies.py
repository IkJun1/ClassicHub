import os
import firebase_admin

from firebase_admin import credentials, auth as firebase_auth
from firebase_admin.auth import RevokedIdTokenError, ExpiredIdTokenError

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from database import get_db
from models import User

cred_path = os.environ.get("FIREBASE_CREDENTIALS_PATH", "serviceAccountKey.json")

if not firebase_admin._apps:
    try:
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)

    except Exception as e:
        print(f"Firebase 초기화 경고 (키 파일 확인 필요): {e}")

security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    token = credentials.credentials
    try:
        decoded_token = firebase_auth.verify_id_token(token, check_revoked=True)
        uid = decoded_token["uid"]
        email = decoded_token.get("email", "")
        nickname = decoded_token.get("name", "ClassicHub_User")

        # 🚨 [최적화] Firebase JWT 검증 직후 Supabase DB 강제 동기화 (UPSERT)
        # 인증이 필요한 모든 API 호출 시, DB에 유저 레코드가 존재함을 100% 보장하여 외래키 충돌 방지
        stmt = insert(User).values(
            firebase_uid=uid,
            email=email,
            nickname=nickname
        ).on_conflict_do_update(
            index_elements=['firebase_uid'],
            set_={'email': email, 'nickname': nickname}
        )
        db.execute(stmt)
        db.commit()

        return {
            "firebase_uid": uid,
            "email": email,
            "nickname": nickname
        }

    except RevokedIdTokenError:
        raise HTTPException(status_code=401, detail="차단되거나 탈퇴 처리된 계정입니다.")

    except ExpiredIdTokenError:
        raise HTTPException(status_code=401, detail="만료된 세션입니다. 다시 로그인해 주세요.")

    except Exception:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")