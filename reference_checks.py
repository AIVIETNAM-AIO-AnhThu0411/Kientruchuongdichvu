"""Kiểm tra tham chiếu trước khi xóa; không cho CASCADE làm mất lịch sử."""
from fastapi import HTTPException
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError


def table_exists(db, name):
    return inspect(db.connection()).has_table(name, schema='dbo')


def quoted(db, name):
    return db.bind.dialect.identifier_preparer.quote_identifier(name)


def has_rows(db, table, column, value, schema='dbo'):
    q = lambda name: quoted(db, name)
    hint = ' WITH (UPDLOCK, HOLDLOCK)' if db.bind.dialect.name == 'mssql' else ''
    sql = f'SELECT COUNT(*) FROM {q(schema)}.{q(table)}{hint} WHERE {q(column)} = :value'
    return db.scalar(text(sql), {'value': value}) > 0


def refuse_references(db, parent, primary_key, value, ignore=frozenset()):
    if db.bind.dialect.name == 'mssql':
        # Metadata bao gồm cả FK CASCADE và FK đang disabled; không dựa vào lỗi DELETE.
        rows = db.execute(text('''SELECT s.name AS schema_name, t.name AS table_name, c.name AS column_name
            FROM sys.foreign_key_columns f
            JOIN sys.tables t ON t.object_id=f.parent_object_id
            JOIN sys.schemas s ON s.schema_id=t.schema_id
            JOIN sys.columns c ON c.object_id=f.parent_object_id AND c.column_id=f.parent_column_id
            JOIN sys.columns r ON r.object_id=f.referenced_object_id AND r.column_id=f.referenced_column_id
            WHERE f.referenced_object_id=OBJECT_ID(:target) AND r.name=:pk'''),
            {'target': 'dbo.' + parent, 'pk': primary_key}).mappings().all()
        for row in rows:
            if row['schema_name'] == 'dbo' and row['table_name'] in ignore:
                continue
            if has_rows(db, row['table_name'], row['column_name'], value, row['schema_name']):
                raise HTTPException(409, 'Đã có dữ liệu liên quan. Không thể xóa; hãy khóa tài khoản để giữ lịch sử.')
        inspector = None
    else:
        inspector = inspect(db.connection())
    schemas = ['dbo'] if inspector else []
    for schema in schemas:
        for name in inspector.get_table_names(schema=schema):
            if schema == 'dbo' and name in ignore:
                continue
            for fk in inspector.get_foreign_keys(name, schema=schema):
                if fk['referred_table'] != parent or (fk.get('referred_schema') or schema) != 'dbo':
                    continue
                for local, remote in zip(fk['constrained_columns'], fk['referred_columns']):
                    if remote == primary_key and has_rows(db, name, local, value, schema):
                        raise HTTPException(409, 'Đã có dữ liệu liên quan. Không thể xóa; có thể khóa/ngừng hoạt động để giữ lịch sử.')
    # Các liên kết nghiệp vụ chuẩn vẫn được kiểm tra khi DB cũ thiếu FK.
    pairs = [('boarding_house', 'owner_id')] if parent == 'user' else [
        ('room', 'boarding_house_id'), ('billing_period', 'boarding_house_id'), ('utility_rate', 'boarding_house_id')]
    for table, column in pairs:
        if table_exists(db, table) and has_rows(db, table, column, value):
            raise HTTPException(409, 'Đã có dữ liệu liên quan. Không thể xóa; hãy khóa/ngừng hoạt động.')


def commit_delete(db):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Không thể xóa vì còn dữ liệu tham chiếu.') from None
