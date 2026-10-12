from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, HTTPException, Response
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from auth import ALLOWED_ROLES, CurrentAccount, current_admin_after_lock, hash_password, require_admin
from database import get_db
from models import AuthSession, Role, User
from schemas import RoleName, RoleOut, RoleUpdate, StatusUpdate, UserCreate, UserOut, UserPage, UserStatus, UserUpdate
from reference_checks import refuse_references, commit_delete
from services import commit_change, get_role, get_user, update_user


router = APIRouter(tags=['Quản lý tài khoản'])
Db = Annotated[Session, Depends(get_db)]
Admin = Annotated[CurrentAccount, Depends(require_admin)]
UserId = Annotated[int, Path(ge=1, le=9223372036854775807)]


@router.get('/roles', response_model=list[RoleOut])
def roles(db: Db, actor: Admin):
    return db.scalars(select(Role).where(Role.role_name.in_(ALLOWED_ROLES)).order_by(Role.role_id)).all()


@router.get('/users/overview')
def overview(db: Db, actor: Admin):
    rows = db.execute(
        select(Role.role_name, User.status, func.count(User.user_id))
        .join(User, User.role_id == Role.role_id)
        .where(Role.role_name.in_(ALLOWED_ROLES))
        .group_by(Role.role_name, User.status)
    ).all()
    result = {'total': 0, 'admins': 0, 'landlords': 0, 'active': 0, 'locked': 0}
    for role, status, count in rows:
        result['total'] += count
        result['admins' if role == 'ADMIN' else 'landlords'] += count
        result['active' if status == 'ACTIVE' else 'locked'] += count
    return result


@router.get('/users', response_model=UserPage)
def users(
    db: Db, actor: Admin,
    role_name: RoleName | None = None,
    status: UserStatus | None = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    filters = [Role.role_name.in_(ALLOWED_ROLES)]
    if role_name:
        filters.append(Role.role_name == role_name.value)
    if status:
        filters.append(User.status == status.value)
    if search and search.strip():
        # contains(autoescape) tìm ký tự %/_ như văn bản, không dùng làm wildcard.
        value = search.strip()
        filters.append(or_(User.full_name.contains(value, autoescape=True), User.email.contains(value, autoescape=True), User.phone.contains(value, autoescape=True)))
    total = db.scalar(select(func.count(User.user_id)).join(User.role).where(*filters))
    rows = db.scalars(
        select(User).join(User.role).where(*filters).order_by(User.user_id.desc())
        .offset((page - 1) * limit).limit(limit)
    ).all()
    return UserPage(data=[UserOut.model_validate(row) for row in rows], page=page, limit=limit, total=total)


@router.post('/users', response_model=UserOut, status_code=201)
def create_user(payload: UserCreate, db: Db, actor: Admin):
    current_admin_after_lock(db, actor)
    role = get_role(db, payload.role_name.value)
    user = User(
        role=role, full_name=payload.full_name, email=str(payload.email), phone=payload.phone,
        password_hash=hash_password(payload.password), status=payload.status.value,
    )
    db.add(user)
    commit_change(db)
    return user


@router.get('/users/{user_id}', response_model=UserOut)
def user_detail(user_id: UserId, db: Db, actor: Admin):
    return get_user(db, user_id)


@router.patch('/users/{user_id}', response_model=UserOut)
def edit_user(user_id: UserId, payload: UserUpdate, db: Db, actor: Admin):
    return update_user(db, actor, user_id, payload)


@router.patch('/users/{user_id}/status', response_model=UserOut)
def edit_status(user_id: UserId, payload: StatusUpdate, db: Db, actor: Admin):
    return update_user(db, actor, user_id, UserUpdate(status=payload.status))


@router.patch('/users/{user_id}/role', response_model=UserOut)
def edit_role(user_id: UserId, payload: RoleUpdate, db: Db, actor: Admin):
    return update_user(db, actor, user_id, UserUpdate(role_name=payload.role_name))


@router.delete('/users/{user_id}', status_code=204)
def delete_user(user_id: UserId, db: Db, actor: Admin):
    current = current_admin_after_lock(db, actor)
    target = get_user(db, user_id, lock=True)
    if target.user_id == current.user.user_id:
        raise HTTPException(409, 'Không thể tự xóa tài khoản đang đăng nhập.')
    if target.role_name == 'ADMIN' and target.status == 'ACTIVE':
        count = db.scalar(select(func.count(User.user_id)).join(User.role).where(Role.role_name == 'ADMIN', User.status == 'ACTIVE'))
        if count <= 1:
            raise HTTPException(409, 'Phải còn ít nhất một ADMIN đang hoạt động.')
    refuse_references(db, 'user', 'user_id', target.user_id, ignore={'auth_session'})
    db.execute(delete(AuthSession).where(AuthSession.user_id == target.user_id))
    db.delete(target)
    commit_delete(db)
    return Response(status_code=204)
