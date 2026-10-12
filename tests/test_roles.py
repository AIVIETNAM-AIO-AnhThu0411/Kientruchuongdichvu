import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError

from database import check_schema
from models import Role


@pytest.mark.parametrize('roles', [
    ('ADMIN', 'LANDLORD'),
    ('LANDLORD', 'ADMIN'),
    ('ADMIN', 'OWNER'),
    ('ADMIN', 'LANDLORD', 'OWNER', 'TENANT'),
    ('ADMIN', 'LANDLORD', 'TENANT'),
    ('ADMIN', 'LANDLORD', 'LANDLORD'),
    ('ADMIN',),
    (),
])
def test_startup_requires_exactly_two_database_roles(roles):
    # Chạy truy vấn role thật trên schema cũ. Chỉ giả lập các hàm metadata
    # của SQL Server; kiểm tra này không thay thế chạy migration trong SSMS.
    engine = create_engine('sqlite://')

    @event.listens_for(engine, 'connect')
    def attach_schema(connection, _record):
        connection.execute("ATTACH DATABASE ':memory:' AS dbo")
        connection.create_function('DB_NAME', 0, lambda: 'quan_ly_tro')
        connection.create_function('HAS_PERMS_BY_NAME', 3, lambda *args: 1)
        connection.create_function('OBJECT_ID', 2, lambda *args: 1)

    @event.listens_for(engine, 'before_cursor_execute', retval=True)
    def adapt_metadata_literals(_connection, _cursor, statement, parameters, _context, _many):
        # SQLite không hỗ trợ tiền tố N của chuỗi Unicode T-SQL.
        return statement.replace("N'", "'"), parameters

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql('CREATE TABLE dbo.role (role_name VARCHAR(20))')
            for role in roles:
                connection.exec_driver_sql('INSERT INTO dbo.role (role_name) VALUES (?)', (role,))
        if len(roles) == 2 and set(roles) == {'ADMIN', 'LANDLORD'}:
            check_schema(engine)
        else:
            with pytest.raises(RuntimeError, match='đúng 2 vai trò'):
                check_schema(engine)
    finally:
        engine.dispose()


@pytest.mark.parametrize('role_name', ['OWNER', 'TENANT'])
def test_database_rejects_unsupported_role_rows(app_env, role_name):
    with app_env[1]() as db:
        db.add(Role(role_name=role_name))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        assert db.query(Role).count() == 2
