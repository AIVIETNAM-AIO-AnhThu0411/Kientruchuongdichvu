"""Nghiệp vụ quản lý tài khoản dùng chung cho các endpoint."""

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth import ALLOWED_ROLES, CurrentAccount, current_admin_after_lock, hash_password
from models import AuthSession, Role, User, utc_now
from schemas import UserUpdate


def get_user(db: Session, user_id: int, lock=False) -> User:
    statement = (
        select(User).join(User.role)
        .where(User.user_id == user_id, Role.role_name.in_(ALLOWED_ROLES))
        .execution_options(populate_existing=True)
    )
    if lock:
        statement = statement.with_hint(User, 'WITH (XLOCK, HOLDLOCK)', dialect_name='mssql')
    user = db.scalar(statement)
    if user is None:
        raise HTTPException(404, 'Không tìm thấy tài khoản.')
    return user


def get_role(db: Session, name: str) -> Role:
    role = db.scalar(select(Role).where(Role.role_name == name))
    if role is None:
        raise HTTPException(503, f'Database thiếu vai trò {name}.')
    return role


def commit_change(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Email hoặc số điện thoại đã được sử dụng.') from None


def update_user(db: Session, actor: CurrentAccount, user_id: int, data: UserUpdate) -> User:
    current = current_admin_after_lock(db, actor)
    target = get_user(db, user_id)
    changes = data.model_dump(exclude_unset=True, mode='json')
    new_role = changes.get('role_name', target.role_name)
    new_status = changes.get('status', target.status)
    losing_active_admin = target.role_name == 'ADMIN' and target.status == 'ACTIVE' and (
        new_role != 'ADMIN' or new_status != 'ACTIVE'
    )
    if losing_active_admin:
        if target.user_id == current.user.user_id:
            raise HTTPException(409, 'Bạn không thể tự khóa hoặc tự hạ quyền ADMIN.')
        admins = db.scalar(
            select(func.count(User.user_id)).join(User.role)
            .where(Role.role_name == 'ADMIN', User.status == 'ACTIVE')
        )
        if admins <= 1:
            raise HTTPException(409, 'Phải còn ít nhất một ADMIN đang hoạt động.')

    revoke = new_role != target.role_name or new_status != target.status or 'password' in changes
    if 'role_name' in changes:
        target.role = get_role(db, changes.pop('role_name'))
    if 'password' in changes:
        target.password_hash = hash_password(changes.pop('password'))
    for field, value in changes.items():
        setattr(target, field, value)
    target.updated_at = utc_now()
    if revoke:
        db.execute(delete(AuthSession).where(AuthSession.user_id == target.user_id))
    commit_change(db)
    return target
