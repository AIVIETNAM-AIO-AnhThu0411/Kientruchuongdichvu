import pytest
from sqlalchemy import Column, ForeignKey, Integer, MetaData, String, Table, select
from sqlalchemy.dialects import mssql
from auth import verify_password
from models import AuthSession, User
from reference_checks import refuse_references
from tests.conftest import login


def test_phone_login_and_email_compatibility(app_env, admin_auth):
    client = app_env[0]
    assert client.patch('/users/2', headers=admin_auth, json={'phone': '0901234567'}).status_code == 200
    result = client.post('/auth/login', json={'identifier': ' 0901234567 ', 'password': 'ChuTro@2026!'})
    assert result.status_code == 200 and result.json()['role'] == 'LANDLORD'
    assert client.post('/auth/login', json={'identifier': 'ADMIN@TROVIET.EXAMPLE', 'password': 'Admin@2026!'}).status_code == 200
    assert client.post('/auth/login', json={'identifier': '0901234567', 'password': 'wrong'}).status_code == 401
    assert client.post('/auth/login', json={'identifier': 'admin@troviet.example', 'email': 'admin@troviet.example', 'password': 'secret'}).status_code == 422
    assert client.post('/auth/login', json={'identifier': ' ', 'password': 'secret'}).status_code == 422


def test_password_change_validates_and_revokes_all_sessions(app_env):
    client, factory, _ = app_env
    first = login(client, 'LANDLORD'); second = login(client, 'LANDLORD')
    payload = {'current_password': 'ChuTro@2026!', 'new_password': 'Moi@2026!abcdefgh', 'confirm_password': 'Moi@2026!abcdefgh'}
    assert client.post('/auth/change-password', headers=first, json=dict(payload, current_password='wrong')).status_code == 400
    result = client.post('/auth/change-password', headers=first, json=dict(payload, confirm_password='NotSame@2026!'))
    assert result.status_code == 422 and payload['new_password'] not in result.text
    assert client.post('/auth/change-password', headers=first, json=payload).status_code == 204
    for headers in [first, second]:
        assert client.get('/auth/me', headers=headers).status_code == 401
    assert client.post('/auth/login', json={'identifier': 'chutro@troviet.example', 'password': 'ChuTro@2026!'}).status_code == 401
    assert client.post('/auth/login', json={'identifier': 'chutro@troviet.example', 'password': payload['new_password']}).status_code == 200
    with factory() as db:
        assert verify_password(db.get(User, 2).password_hash, payload['new_password'])


def test_password_change_has_no_target_user_and_requires_auth(app_env):
    client = app_env[0]; headers = login(client, 'LANDLORD')
    payload = {'current_password': 'ChuTro@2026!', 'new_password': 'abcdefgh@2026!', 'confirm_password': 'abcdefgh@2026!'}
    assert client.post('/auth/change-password', json=payload).status_code == 401
    assert client.post('/auth/change-password', headers=headers, json=dict(payload, user_id='1')).status_code == 422
    assert client.post('/auth/change-password', headers=headers, json=dict(payload, new_password='ChuTro@2026!', confirm_password='ChuTro@2026!')).status_code == 422


def test_delete_unreferenced_user_revokes_sessions(app_env, admin_auth):
    client, factory, _ = app_env
    owner = login(client, 'LANDLORD')
    assert client.delete('/users/2', headers=admin_auth).status_code == 204
    assert client.get('/auth/me', headers=owner).status_code == 401
    assert client.get('/users/2', headers=admin_auth).status_code == 404
    with factory() as db:
        assert not db.scalar(select(AuthSession).where(AuthSession.user_id == 2))
    assert client.delete('/users/1', headers=admin_auth).status_code == 409


def test_landlord_cannot_delete_or_change_other_account(app_env):
    client = app_env[0]; headers = login(client, 'LANDLORD')
    assert client.delete('/users/1', headers=headers).status_code == 403
    assert client.patch('/users/1', headers=headers, json={'full_name': 'Changed'}).status_code == 403


@pytest.mark.parametrize('cascade', [False, True])
def test_reference_blocks_delete_even_if_fk_has_cascade(app_env, admin_auth, cascade):
    client, factory, _ = app_env
    with factory() as db:
        metadata = MetaData()
        Table('user', metadata, Column('user_id', Integer, primary_key=True), schema='dbo')
        history = Table('custom_history', metadata, Column('id', Integer, primary_key=True),
                        Column('account_id', Integer, ForeignKey('dbo.user.user_id', ondelete='CASCADE' if cascade else None)), schema='dbo')
        history.create(db.connection())
        db.execute(history.insert().values(id=1, account_id=2)); db.commit()
    assert client.delete('/users/2', headers=admin_auth).status_code == 409
    with factory() as db:
        assert db.get(User, 2) is not None
        assert db.scalar(select(history.c.id)) == 1


def test_business_link_without_fk_still_blocks_user_deletion(app_env, admin_auth):
    client, factory, _ = app_env
    with factory() as db:
        table = Table('boarding_house', MetaData(), Column('id', Integer, primary_key=True), Column('owner_id', Integer), schema='dbo')
        table.create(db.connection()); db.execute(table.insert().values(id=1, owner_id=2)); db.commit()
    assert client.delete('/users/2', headers=admin_auth).status_code == 409


def test_locked_user_cannot_change_password(app_env, admin_auth):
    client = app_env[0]; headers = login(client, 'LANDLORD')
    assert client.patch('/users/2/status', headers=admin_auth, json={'status': 'LOCKED'}).status_code == 200
    payload = {'current_password': 'ChuTro@2026!', 'new_password': 'abcdefgh@2026!', 'confirm_password': 'abcdefgh@2026!'}
    assert client.post('/auth/change-password', headers=headers, json=payload).status_code == 401


def test_static_ui_and_auth_only_scope(app_env):
    client = app_env[0]
    assert client.get('/ui/').status_code == 200
    assert 'identifier' in client.get('/ui/').text
    assert client.get('/ui/admin.html').status_code == 200
    assert client.get('/ui/admin.js').status_code == 200
    schema = client.get('/openapi.json').json()
    assert not any('boarding-houses' in path for path in schema['paths'])
    assert '/auth/change-password' in schema['paths']
    assert 'delete' in schema['paths']['/users/{user_id}']
