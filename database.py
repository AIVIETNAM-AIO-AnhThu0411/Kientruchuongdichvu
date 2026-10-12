import os
from dataclasses import dataclass
from pathlib import Path
from typing import Generator

from dotenv import load_dotenv
from fastapi import Request
from sqlalchemy import URL, create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class Settings:
    db_auth: str = 'windows'
    db_server: str = 'localhost'
    db_instance: str = ''
    db_port: str = '1433'
    db_database: str = 'quan_ly_tro'
    db_driver: str = 'ODBC Driver 17 for SQL Server'
    db_user: str = ''
    db_password: str = ''
    db_encrypt: bool = True
    db_trust_certificate: bool = True
    cors_origins: tuple[str, ...] = ('http://localhost:5173', 'http://localhost:3000')
    session_hours: int = 8
    login_limit: int = 10


def load_settings() -> Settings:
    load_dotenv(Path(__file__).resolve().parent / '.env')

    def flag(name: str, default: str) -> bool:
        value = os.getenv(name, default).strip().lower()
        if value not in {'true', 'false'}:
            raise ValueError(f'{name} chỉ nhận true hoặc false.')
        return value == 'true'

    hours = int(os.getenv('SESSION_HOURS', '8'))
    limit = int(os.getenv('LOGIN_LIMIT', '10'))
    if not 1 <= hours <= 24 or not 1 <= limit <= 100:
        raise ValueError('SESSION_HOURS: 1–24; LOGIN_LIMIT: 1–100.')
    return Settings(
        db_auth=os.getenv('DB_AUTH', 'windows').strip().lower(),
        db_server=os.getenv('DB_SERVER', 'localhost').strip(),
        db_instance=os.getenv('DB_INSTANCE', '').strip(),
        db_port=os.getenv('DB_PORT', '1433').strip(),
        db_database=os.getenv('DB_DATABASE', 'quan_ly_tro').strip(),
        db_driver=os.getenv('DB_DRIVER', 'ODBC Driver 17 for SQL Server').strip(),
        db_user=os.getenv('DB_USER', ''),
        db_password=os.getenv('DB_PASSWORD', ''),
        db_encrypt=flag('DB_ENCRYPT', 'true'),
        db_trust_certificate=flag('DB_TRUST_SERVER_CERTIFICATE', 'true'),
        cors_origins=tuple(item.strip() for item in os.getenv('CORS_ORIGINS', 'http://localhost:5173,http://localhost:3000').split(',') if item.strip()),
        session_hours=hours,
        login_limit=limit,
    )


def odbc_connection(settings: Settings) -> str:
    if settings.db_auth not in {'windows', 'sql'}:
        raise ValueError('DB_AUTH phải là windows hoặc sql.')
    server, instance = settings.db_server, settings.db_instance
    if '\\' in server:
        parts = server.split('\\')
        if len(parts) != 2 or instance:
            raise ValueError('Tách DB_SERVER và DB_INSTANCE theo .env.example.')
        server, instance = parts
    if not server or not settings.db_database or not settings.db_driver:
        raise ValueError('DB_SERVER, DB_DATABASE và DB_DRIVER không được trống.')
    if instance and settings.db_port:
        raise ValueError('Khi dùng DB_INSTANCE, để DB_PORT trống.')
    if instance:
        address = f'{server}\\{instance}'
    else:
        port = settings.db_port or '1433'
        if not port.isdecimal() or not 1 <= int(port) <= 65535:
            raise ValueError('DB_PORT không hợp lệ.')
        address = f'{server},{port}'

    def brace(value: str) -> str:
        return '{' + value.replace('}', '}}') + '}'

    fields = [
        ('DRIVER', settings.db_driver), ('SERVER', address), ('DATABASE', settings.db_database),
        ('Encrypt', 'yes' if settings.db_encrypt else 'no'),
        ('TrustServerCertificate', 'yes' if settings.db_trust_certificate else 'no'),
    ]
    if settings.db_auth == 'windows':
        fields.append(('Trusted_Connection', 'yes'))
    else:
        if not settings.db_user or not settings.db_password:
            raise ValueError('Điền DB_USER/DB_PASSWORD cho SQL Server Authentication.')
        fields.extend([('UID', settings.db_user), ('PWD', settings.db_password)])
    return ';'.join(f'{key}={brace(value)}' for key, value in fields) + ';'


def build_engine(settings: Settings) -> Engine:
    url = URL.create('mssql+pyodbc', query={'odbc_connect': odbc_connection(settings)})
    engine = create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=10, connect_args={'timeout': 15})

    @event.listens_for(engine, 'connect')
    def configure_connection(connection, _record):
        # Cần cho INSERT/UPDATE bảng có filtered unique index của SĐT.
        cursor = connection.cursor()
        cursor.execute('SET ANSI_NULLS ON; SET QUOTED_IDENTIFIER ON; SET ANSI_PADDING ON; '
                       'SET ANSI_WARNINGS ON; SET CONCAT_NULL_YIELDS_NULL ON; '
                       'SET ARITHABORT ON; SET NUMERIC_ROUNDABORT OFF; SET XACT_ABORT ON;')
        cursor.close()
        connection.commit()

    return engine


def check_schema(engine: Engine) -> None:
    with engine.connect() as connection:
        if connection.scalar(text("SELECT HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'VIEW DEFINITION')")) != 1:
            raise RuntimeError('Login SQL cần VIEW DEFINITION trên database để kiểm tra toàn bộ khóa ngoại trước khi xóa.')
        tables = connection.execute(text("SELECT OBJECT_ID(N'dbo.role', N'U'), OBJECT_ID(N'dbo.user', N'U'), OBJECT_ID(N'dbo.auth_session', N'U')")).one()
        if not all(tables):
            raise RuntimeError('Thiếu bảng. Chạy SQL theo HUONG_DAN.md, bao gồm 05_upgrade_auth.sql.')
        roles = list(connection.execute(text('SELECT role_name FROM dbo.[role]')).scalars())
        if len(roles) != 2 or set(roles) != {'ADMIN', 'LANDLORD'}:
            raise RuntimeError('Bảng role phải có đúng 2 vai trò: ADMIN và LANDLORD. Dừng API, chạy sql/05_upgrade_auth.sql trong SSMS rồi khởi động lại.')


def get_db(request: Request) -> Generator[Session, None, None]:
    with request.app.state.session_factory() as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise
