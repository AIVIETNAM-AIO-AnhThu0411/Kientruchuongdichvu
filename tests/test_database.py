from dataclasses import replace

import pytest

from database import Settings, odbc_connection


def test_windows_auth_and_named_instance():
    result = odbc_connection(Settings())
    assert 'DRIVER={ODBC Driver 17 for SQL Server}' in result
    assert 'Trusted_Connection={yes}' in result and 'UID=' not in result
    named = odbc_connection(replace(Settings(), db_server='MAYBAN', db_instance='SQLEXPRESS', db_port=''))
    assert 'SERVER={MAYBAN\\SQLEXPRESS}' in named
    same = odbc_connection(replace(Settings(), db_server='MAYBAN\\SQLEXPRESS', db_port=''))
    assert same == named


def test_sql_connection_escapes_password_delimiters():
    result = odbc_connection(replace(Settings(), db_auth='sql', db_user='auth_user', db_password='p};UID=intruder;'))
    assert 'PWD={p}};UID=intruder;}' in result
    assert 'Trusted_Connection=' not in result


@pytest.mark.parametrize('changes', [
    {'db_auth': 'bad'}, {'db_server': ''}, {'db_port': '70000'},
    {'db_instance': 'SQLEXPRESS'}, {'db_auth': 'sql'},
])
def test_invalid_database_settings(changes):
    with pytest.raises(ValueError):
        odbc_connection(replace(Settings(), **changes))
