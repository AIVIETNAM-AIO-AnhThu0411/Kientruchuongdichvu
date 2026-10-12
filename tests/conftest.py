import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import Settings
from main import create_app
from models import Base, Role, User


ADMIN_HASH = '$argon2id$v=19$m=65536,t=3,p=4$jOGxldG8l3KuI/kqRQOQYQ$uEpxiN7tNk1E4XJFfWytOfbXPMT3G8YKCMtF7EoV0qY'
LANDLORD_HASH = '$argon2id$v=19$m=65536,t=3,p=4$S4s6oYjTG+eN6kYwO8+53g$oPzx6rZ6vxt3fyTAHcBJqFqB2oo6TNF3WrqLP4PPB8I'


@pytest.fixture
def app_env():
    # Chạy HTTP/ORM thật trên SQLite, không kết nối SQL Server của người dùng.
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)

    @event.listens_for(engine, 'connect')
    def attach_schema(connection, _record):
        connection.execute("ATTACH DATABASE ':memory:' AS dbo")
        connection.execute('PRAGMA foreign_keys=ON')

    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        admin = Role(role_id=11, role_name='ADMIN', description='Quản trị')
        owner = Role(role_id=22, role_name='LANDLORD', description='Chủ trọ')
        db.add_all([admin, owner])
        db.add_all([
            User(user_id=1, role=admin, full_name='Admin', email='admin@troviet.example', password_hash=ADMIN_HASH),
            User(user_id=2, role=owner, full_name='Chủ trọ', email='chutro@troviet.example', password_hash=LANDLORD_HASH),
        ])
        db.commit()
    app = create_app(Settings(login_limit=100), engine=engine, check_on_start=False)
    with TestClient(app) as client:
        yield client, factory, app
    engine.dispose()


def login(client, role='ADMIN'):
    email, password = ('admin@troviet.example', 'Admin@2026!') if role == 'ADMIN' else ('chutro@troviet.example', 'ChuTro@2026!')
    result = client.post('/auth/login', json={'email': email, 'password': password})
    assert result.status_code == 200, result.text
    return {'Authorization': 'Bearer ' + result.json()['access_token']}


@pytest.fixture
def admin_auth(app_env):
    return login(app_env[0])
