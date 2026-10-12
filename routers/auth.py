import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from auth import (
    ALLOWED_ROLES, CurrentAccount, client_key, get_current_account,
    lock_admin_writes, token_digest, verify_password, hash_password, authenticate_hash,
)
from database import get_db
from models import AuthSession, Role, User, utc_now
from schemas import LoginRequest, LoginResponse, UserOut, PasswordChange


router = APIRouter(prefix='/auth', tags=['Đăng nhập'])


@router.post('/login', response_model=LoginResponse)
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    key = client_key(request)
    attempt = request.app.state.login_limiter.reserve(key)
    query = select(User).join(User.role).where((User.email == payload.identifier) if '@' in payload.identifier else (User.phone == payload.identifier))
    user = db.scalar(query)
    original_hash = user.password_hash if user else None
    verified = verify_password(original_hash, payload.password)
    if not verified or user.status != 'ACTIVE' or user.role_name not in ALLOWED_ROLES:
        raise HTTPException(401, 'Email/SĐT hoặc mật khẩu không đúng, hoặc tài khoản không được phép đăng nhập.')

    lock_admin_writes(db)
    # Đọc lại sau khi lấy khóa: một yêu cầu khác có thể vừa khóa/đổi mật khẩu.
    user = db.scalar(query.execution_options(populate_existing=True))
    if user is None or user.password_hash != original_hash or user.status != 'ACTIVE' or user.role_name not in ALLOWED_ROLES:
        raise HTTPException(401, 'Tài khoản vừa thay đổi. Vui lòng đăng nhập lại.')

    now = utc_now()
    expires_at = (now + timedelta(hours=request.app.state.settings.session_hours)).replace(microsecond=0)
    token = secrets.token_urlsafe(32)
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.user_id, AuthSession.expires_at <= now))
    db.add(AuthSession(token_hash=token_digest(token), user_id=user.user_id, expires_at=expires_at))
    db.commit()
    request.app.state.login_limiter.success(key, attempt)
    response.headers['Cache-Control'] = 'no-store'
    return LoginResponse(access_token=token, expires_at=expires_at, role=user.role_name, user=UserOut.model_validate(user))


@router.get('/me', response_model=UserOut)
def me(account: CurrentAccount = Depends(get_current_account)):
    return account.user


@router.post('/logout', status_code=204)
def logout(account: CurrentAccount = Depends(get_current_account), db: Session = Depends(get_db)):
    db.execute(delete(AuthSession).where(AuthSession.token_hash == account.token_hash))
    db.commit()
    return Response(status_code=204)


@router.post('/change-password', status_code=204)
def change_password(payload: PasswordChange, account: CurrentAccount = Depends(get_current_account), db: Session = Depends(get_db)):
    lock_admin_writes(db)
    current = authenticate_hash(db, account.token_hash)
    if not verify_password(current.user.password_hash, payload.current_password):
        raise HTTPException(400, 'Mật khẩu hiện tại không đúng.')
    current.user.password_hash = hash_password(payload.new_password)
    current.user.updated_at = utc_now()
    # Đổi mật khẩu thu hồi tất cả phiên, kể cả phiên hiện tại.
    db.execute(delete(AuthSession).where(AuthSession.user_id == current.user.user_id))
    db.commit()
    return Response(status_code=204)
