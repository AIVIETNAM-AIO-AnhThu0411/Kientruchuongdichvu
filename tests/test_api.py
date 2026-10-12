from datetime import timedelta

import pytest
from sqlalchemy import delete, select, update

from auth import token_digest, verify_password
from models import AuthSession, User, utc_now
from tests.conftest import login


def owner_payload(**changes):
    return {'full_name': 'Chủ trọ mới', 'email': 'owner2@gmail.com', 'password': 'OwnerMoi@2026!', **changes}


def test_login_uses_existing_argon2_hash_and_role(app_env):
    client, factory, _ = app_env
    result = client.post('/auth/login', json={'email': 'ADMIN@TROVIET.EXAMPLE', 'password': 'Admin@2026!'})
    assert result.status_code == 200
    body = result.json()
    assert body['role'] == 'ADMIN'
    assert body['user']['user_id'] == '1'
    assert body['user']['role_id'] == 11  # Không giả định role_id=1.
    assert body['expires_at'].endswith('Z')
    assert 'password_hash' not in result.text
    token = body['access_token']
    with factory() as db:
        saved = db.get(AuthSession, token_digest(token))
        assert saved and saved.token_hash != token
    headers = {'Authorization': 'Bearer ' + token}
    assert client.get('/auth/me', headers=headers).json()['email'] == 'admin@troviet.example'


@pytest.mark.parametrize('email,password', [
    ('admin@troviet.example', 'wrong'),
    ('unknown@gmail.com', 'Admin@2026!'),
    ('nguoithue@troviet.example', 'NguoiThue@2026!'),
])
def test_invalid_or_unknown_login_denied(app_env, email, password):
    assert app_env[0].post('/auth/login', json={'email': email, 'password': password}).status_code == 401


def test_owner_cannot_access_admin_endpoints(app_env):
    client = app_env[0]
    headers = login(client, 'LANDLORD')
    assert client.get('/auth/me', headers=headers).json()['role_name'] == 'LANDLORD'
    for url in ['/users', '/roles', '/users/overview', '/users/1']:
        assert client.get(url, headers=headers).status_code == 403
    assert client.post('/users', headers=headers, json=owner_payload()).status_code == 403
    assert client.patch('/users/1/status', headers=headers, json={'status': 'LOCKED'}).status_code == 403


def test_auth_requires_real_nonexpired_token(app_env):
    client, factory, _ = app_env
    assert client.get('/users').status_code == 401
    assert client.get('/auth/me', headers={'Authorization': 'Bearer invalid'}).status_code == 401
    headers = login(client)
    with factory() as db:
        db.execute(update(AuthSession).values(expires_at=utc_now() - timedelta(seconds=1)))
        db.commit()
    assert client.get('/auth/me', headers=headers).status_code == 401


def test_logout_revokes_session(app_env, admin_auth):
    client = app_env[0]
    assert client.post('/auth/logout', headers=admin_auth).status_code == 204
    assert client.get('/auth/me', headers=admin_auth).status_code == 401


def test_admin_list_has_two_roles_and_supports_filter(app_env, admin_auth):
    client = app_env[0]
    page = client.get('/users', headers=admin_auth).json()
    assert page['total'] == 2
    assert {user['role_name'] for user in page['data']} == {'ADMIN', 'LANDLORD'}
    owner = client.get('/users?role_name=LANDLORD&search=chutro', headers=admin_auth).json()
    assert owner['total'] == 1
    assert owner['data'][0]['user_id'] == '2'
    assert client.get('/users/3', headers=admin_auth).status_code == 404
    assert [row['role_name'] for row in client.get('/roles', headers=admin_auth).json()] == ['ADMIN', 'LANDLORD']
    assert client.get('/users/overview', headers=admin_auth).json() == {'total': 2, 'admins': 1, 'landlords': 1, 'active': 2, 'locked': 0}


def test_create_owner_unicode_name_and_hashed_password(app_env, admin_auth):
    client, factory, _ = app_env
    result = client.post('/users', headers=admin_auth, json=owner_payload(full_name='  Nguyễn Thị Ánh  '))
    assert result.status_code == 201
    body = result.json()
    assert body['role_name'] == 'LANDLORD' and body['role_id'] == 22
    assert body['full_name'] == 'Nguyễn Thị Ánh'
    with factory() as db:
        user = db.get(User, int(body['user_id']))
        assert user.password_hash.startswith('$argon2id$')
        assert verify_password(user.password_hash, 'OwnerMoi@2026!')
    assert client.post('/auth/login', json={'email': body['email'], 'password': 'OwnerMoi@2026!'}).json()['role'] == 'LANDLORD'


@pytest.mark.parametrize('changes', [
    {'role_name': 'TENANT'}, {'role_name': 'OWNER'}, {'full_name': '   '},
    {'email': 'invalid'}, {'phone': 'abc'}, {'password': '123456'}, {'admin': True},
])
def test_create_validation_and_no_password_echo(app_env, admin_auth, changes):
    result = app_env[0].post('/users', headers=admin_auth, json=owner_payload(**changes))
    assert result.status_code == 422
    assert 'OwnerMoi@2026!' not in result.text
    assert '123456' not in result.text
    assert '"input"' not in result.text


def test_unique_email_and_optional_phone(app_env, admin_auth):
    client = app_env[0]
    first = client.post('/users', headers=admin_auth, json=owner_payload(phone='0901234567'))
    assert first.status_code == 201
    assert client.post('/users', headers=admin_auth, json=owner_payload(email='OWNER2@GMAIL.COM')).status_code == 409
    assert client.post('/users', headers=admin_auth, json=owner_payload(email='owner3@gmail.com', phone='0901234567')).status_code == 409
    assert client.post('/users', headers=admin_auth, json=owner_payload(email='owner4@gmail.com')).status_code == 201


def test_lock_and_unlock_do_not_restore_old_session(app_env, admin_auth):
    client = app_env[0]
    owner_auth = login(client, 'LANDLORD')
    result = client.patch('/users/2/status', headers=admin_auth, json={'status': 'LOCKED'})
    assert result.status_code == 200 and result.json()['status'] == 'LOCKED'
    assert client.get('/auth/me', headers=owner_auth).status_code == 401
    assert client.post('/auth/login', json={'email': 'chutro@troviet.example', 'password': 'ChuTro@2026!'}).status_code == 401
    assert client.patch('/users/2/status', headers=admin_auth, json={'status': 'ACTIVE'}).status_code == 200
    assert client.get('/auth/me', headers=owner_auth).status_code == 401
    login(client, 'LANDLORD')


def test_password_reset_and_role_change_revoke_sessions(app_env, admin_auth):
    client = app_env[0]
    owner_auth = login(client, 'LANDLORD')
    result = client.patch('/users/2', headers=admin_auth, json={'password': 'MatKhauMoi@2026!'})
    assert result.status_code == 200
    assert client.get('/auth/me', headers=owner_auth).status_code == 401
    assert client.post('/auth/login', json={'email': 'chutro@troviet.example', 'password': 'ChuTro@2026!'}).status_code == 401
    login_result = client.post('/auth/login', json={'email': 'chutro@troviet.example', 'password': 'MatKhauMoi@2026!'})
    assert login_result.status_code == 200
    new_auth = {'Authorization': 'Bearer ' + login_result.json()['access_token']}
    assert client.patch('/users/2/role', headers=admin_auth, json={'role_name': 'ADMIN'}).status_code == 200
    assert client.get('/auth/me', headers=new_auth).status_code == 401
    assert client.post('/auth/login', json={'email': 'chutro@troviet.example', 'password': 'MatKhauMoi@2026!'}).json()['role'] == 'ADMIN'


def test_self_admin_cannot_lock_or_demote(app_env, admin_auth):
    client = app_env[0]
    assert client.patch('/users/1/status', headers=admin_auth, json={'status': 'LOCKED'}).status_code == 409
    assert client.patch('/users/1/role', headers=admin_auth, json={'role_name': 'LANDLORD'}).status_code == 409
    assert client.get('/auth/me', headers=admin_auth).status_code == 200


def test_second_admin_can_be_locked(app_env, admin_auth):
    client = app_env[0]
    created = client.post('/users', headers=admin_auth, json=owner_payload(role_name='ADMIN')).json()
    assert client.patch('/users/' + created['user_id'] + '/status', headers=admin_auth, json={'status': 'LOCKED'}).status_code == 200


@pytest.mark.parametrize('payload', [{}, {'email': None}, {'password': None}, {'full_name': ' '}, {'status': None}])
def test_update_validation(app_env, admin_auth, payload):
    assert app_env[0].patch('/users/2', headers=admin_auth, json=payload).status_code == 422


def test_edit_profile_and_clear_phone_without_revoking_session(app_env, admin_auth):
    client = app_env[0]
    owner_auth = login(client, 'LANDLORD')
    assert client.patch('/users/2', headers=admin_auth, json={'phone': '0912345678', 'full_name': 'Tên mới'}).status_code == 200
    result = client.patch('/users/2', headers=admin_auth, json={'phone': None})
    assert result.status_code == 200 and result.json()['phone'] is None
    assert client.get('/auth/me', headers=owner_auth).json()['full_name'] == 'Tên mới'


def test_bigint_id_preserved_for_browser(app_env, admin_auth):
    client, factory, _ = app_env
    exact_id = 9007199254740993
    with factory() as db:
        user = db.get(User, 2)
        user.user_id = exact_id
        db.commit()
    result = client.get(f'/users/{exact_id}', headers=admin_auth)
    assert result.status_code == 200 and result.json()['user_id'] == str(exact_id)
    assert client.get('/users/9223372036854775808', headers=admin_auth).status_code == 422


def test_login_rechecks_account_after_password_verification(app_env, monkeypatch):
    client = app_env[0]
    import routers.auth as route
    real_lock = route.lock_admin_writes

    def lock_then_disable(db):
        real_lock(db)
        db.execute(update(User).where(User.user_id == 1).values(status='LOCKED'))

    monkeypatch.setattr(route, 'lock_admin_writes', lock_then_disable)
    assert client.post('/auth/login', json={'email': 'admin@troviet.example', 'password': 'Admin@2026!'}).status_code == 401


def test_mutation_rechecks_revoked_actor(app_env, admin_auth, monkeypatch):
    client = app_env[0]
    import auth
    real_lock = auth.lock_admin_writes

    def lock_then_revoke(db):
        real_lock(db)
        db.execute(delete(AuthSession).where(AuthSession.user_id == 1))

    monkeypatch.setattr(auth, 'lock_admin_writes', lock_then_revoke)
    assert client.post('/users', headers=admin_auth, json=owner_payload()).status_code == 401


def test_login_rate_limit(app_env):
    client, _, app = app_env
    app.state.login_limiter.limit = 2
    for _ in range(2):
        assert client.post('/auth/login', json={'email': 'admin@troviet.example', 'password': 'wrong'}).status_code == 401
    result = client.post('/auth/login', json={'email': 'admin@troviet.example', 'password': 'wrong'})
    assert result.status_code == 429 and result.headers['retry-after'] == '900'


def test_docs_health_and_cors(app_env):
    client = app_env[0]
    assert client.get('/health').json() == {'status': 'ok', 'database': 'connected'}
    schema = client.get('/openapi.json').json()
    assert 'HTTPBearer' in schema['components']['securitySchemes']
    assert 'application/json' in schema['paths']['/auth/login']['post']['requestBody']['content']
    response = client.options('/users', headers={'Origin': 'http://localhost:5173', 'Access-Control-Request-Method': 'POST', 'Access-Control-Request-Headers': 'authorization,content-type'})
    assert response.status_code == 200
    assert response.headers['access-control-allow-origin'] == 'http://localhost:5173'
