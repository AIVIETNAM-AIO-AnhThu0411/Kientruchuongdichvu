"""Băm mật khẩu, phiên đăng nhập và kiểm tra quyền ở server."""

import hashlib
import re
import secrets
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from models import AuthSession, Role, User, utc_now


ALLOWED_ROLES = ('ADMIN', 'LANDLORD')
password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)
# Cùng phép verify khi email không tồn tại, để không trả lời ngay lập tức.
_DUMMY_HASH = password_hasher.hash(secrets.token_urlsafe(32))
bearer = HTTPBearer(auto_error=False, description='Dán access_token từ POST /auth/login.')


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(encoded: str | None, password: str) -> bool:
    try:
        return password_hasher.verify(encoded or _DUMMY_HASH, password) and encoded is not None
    except (VerificationError, InvalidHashError):
        return False


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode('ascii')).hexdigest()


def unauthorized() -> HTTPException:
    return HTTPException(401, 'Phiên đăng nhập không hợp lệ hoặc đã hết hạn.', headers={'WWW-Authenticate': 'Bearer'})


@dataclass
class CurrentAccount:
    user: User
    token_hash: str
    expires_at: datetime


def authenticate_hash(db: Session, digest: str) -> CurrentAccount:
    statement = (
        select(AuthSession)
        .join(AuthSession.user)
        .join(User.role)
        .where(
            AuthSession.token_hash == digest,
            AuthSession.expires_at > utc_now(),
            User.status == 'ACTIVE',
            Role.role_name.in_(ALLOWED_ROLES),
        )
        .execution_options(populate_existing=True)
    )
    session = db.scalar(statement)
    if session is None:
        raise unauthorized()
    return CurrentAccount(session.user, session.token_hash, session.expires_at)


def get_current_account(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> CurrentAccount:
    if credentials is None or credentials.scheme.lower() != 'bearer':
        raise unauthorized()
    if not re.fullmatch(r'[A-Za-z0-9_-]{43}', credentials.credentials):
        raise unauthorized()
    return authenticate_hash(db, token_digest(credentials.credentials))


def require_admin(account: CurrentAccount = Depends(get_current_account)) -> CurrentAccount:
    if account.user.role_name != 'ADMIN':
        raise HTTPException(403, 'Chỉ ADMIN được quản lý tài khoản.')
    return account


def lock_admin_writes(db: Session) -> None:
    # Mọi đăng nhập và sửa tài khoản cùng khóa dòng ADMIN trong transaction.
    # SQL Server giữ khóa đến commit/rollback, tránh khóa tài khoản trong lúc login.
    statement = (
        select(Role.role_id)
        .where(Role.role_name == 'ADMIN')
        .with_hint(Role, 'WITH (UPDLOCK, HOLDLOCK)', dialect_name='mssql')
    )
    if db.scalar(statement) is None:
        raise HTTPException(503, 'Database thiếu vai trò ADMIN.')


def current_admin_after_lock(db: Session, account: CurrentAccount) -> CurrentAccount:
    lock_admin_writes(db)
    current = authenticate_hash(db, account.token_hash)
    if current.user.role_name != 'ADMIN':
        raise HTTPException(403, 'Chỉ ADMIN được quản lý tài khoản.')
    return current


class LoginLimiter:
    """Giới hạn theo IP trong một process; cửa sổ 15 phút."""

    def __init__(self, limit: int, window_seconds: int = 900):
        self.limit = limit
        self.window_seconds = window_seconds
        self._attempts: dict[str, deque[tuple[float, str]]] = {}
        self._lock = threading.Lock()

    def reserve(self, key: str) -> str:
        now = time.monotonic()
        with self._lock:
            for old_key in list(self._attempts):
                queue = self._attempts[old_key]
                while queue and queue[0][0] <= now - self.window_seconds:
                    queue.popleft()
                if not queue:
                    del self._attempts[old_key]
            if key not in self._attempts and len(self._attempts) >= 10_000:
                raise HTTPException(429, 'Có quá nhiều yêu cầu đăng nhập. Thử lại sau.', headers={'Retry-After': '900'})
            attempts = self._attempts.setdefault(key, deque())
            if len(attempts) >= self.limit:
                raise HTTPException(429, 'Đăng nhập sai quá nhiều lần. Thử lại sau 15 phút.', headers={'Retry-After': '900'})
            identifier = secrets.token_hex(8)
            attempts.append((now, identifier))
            return identifier

    def success(self, key: str, identifier: str) -> None:
        with self._lock:
            queue = self._attempts.get(key)
            if queue is not None:
                self._attempts[key] = deque(item for item in queue if item[1] != identifier)
                if not self._attempts[key]:
                    del self._attempts[key]


def client_key(request: Request) -> str:
    # Không tự tin cậy X-Forwarded-For do client gửi.
    return request.client.host if request.client else 'unknown'
