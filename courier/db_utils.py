from django.db import connection


def dictfetchone(cursor):
    columns = [col[0] for col in cursor.description] if cursor.description else []
    row = cursor.fetchone()
    return dict(zip(columns, row)) if row else None


def dictfetchall(cursor):
    columns = [col[0] for col in cursor.description] if cursor.description else []
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def fetchone(sql, params=None):
    with connection.cursor() as cur:
        cur.execute(sql, params)
        return dictfetchone(cur)


def fetchall(sql, params=None):
    with connection.cursor() as cur:
        cur.execute(sql, params)
        return dictfetchall(cur)


def execute(sql, params=None):
    with connection.cursor() as cur:
        cur.execute(sql, params)


def execute_returning(sql, params=None):
    with connection.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()
