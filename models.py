from datetime import datetime, timezone

from sqlalchemy import BigInteger, CHAR, CheckConstraint, DateTime, ForeignKey, Identity, Index, Integer, String, Unicode, UniqueConstraint
from sqlalchemy.dialects.mssql import DATETIME2
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


ID_TYPE = BigInteger().with_variant(Integer(), 'sqlite')
EMAIL_TYPE = String(255, collation='Latin1_General_100_CI_AS').with_variant(String(255, collation='NOCASE'), 'sqlite')
UTC_TYPE = DATETIME2(precision=0).with_variant(DateTime(), 'sqlite')


class Role(Base):
    __tablename__ = 'role'
    __table_args__ = (
        CheckConstraint("role_name IN ('ADMIN', 'LANDLORD')", name='CK_role_role_name'),
        {'schema': 'dbo'},
    )

    role_id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    role_name: Mapped[str] = mapped_column(String(20), unique=True)
    description: Mapped[str | None] = mapped_column(Unicode(255), nullable=True)


class User(Base):
    __tablename__ = 'user'
    __table_args__ = (UniqueConstraint('email', name='UQ_user_email'), {'schema': 'dbo'})

    user_id: Mapped[int] = mapped_column(ID_TYPE, Identity(), primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey('dbo.role.role_id'), index=True)
    full_name: Mapped[str] = mapped_column(Unicode(100))
    email: Mapped[str] = mapped_column(EMAIL_TYPE)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default='ACTIVE')
    created_at: Mapped[datetime] = mapped_column(UTC_TYPE, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTC_TYPE, default=utc_now, onupdate=utc_now)
    role: Mapped[Role] = relationship(lazy='joined')

    @property
    def role_name(self) -> str:
        return self.role.role_name


Index('UX_user_phone', User.phone, unique=True, mssql_where=User.phone.is_not(None), sqlite_where=User.phone.is_not(None))


class AuthSession(Base):
    __tablename__ = 'auth_session'
    __table_args__ = {'schema': 'dbo'}

    token_hash: Mapped[str] = mapped_column(CHAR(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('dbo.user.user_id'), index=True)
    expires_at: Mapped[datetime] = mapped_column(UTC_TYPE, index=True)
    created_at: Mapped[datetime] = mapped_column(UTC_TYPE, default=utc_now)
    user: Mapped[User] = relationship(lazy='joined')
