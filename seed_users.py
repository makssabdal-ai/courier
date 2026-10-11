"""Seed default users into courier_db. Run once after init."""
import os
import hashlib
import hmac
import base64
import struct
import binascii
import secrets

import psycopg2

DB = dict(
    host=os.environ.get('DB_HOST', 'localhost'),
    port=os.environ.get('DB_PORT', '5432'),
    dbname=os.environ.get('DB_NAME', 'courier_db'),
    user=os.environ.get('DB_USER', 'postgres'),
    password=os.environ.get('DB_PASSWORD', ''),
)


def pbkdf2_sha256(password: str, iterations: int = 260000) -> str:
    """Minimal PBKDF2-SHA256 hasher compatible with Django's make_password."""
    salt = base64.b64encode(secrets.token_bytes(12)).decode()
    dk = hashlib.pbkdf2_hmac(
        'sha256', password.encode(), salt.encode(), iterations)
    h = base64.b64encode(dk).decode()
    return f'pbkdf2_sha256${iterations}${salt}${h}'


def main():
    conn = psycopg2.connect(**DB)
    conn.autocommit = True
    cur = conn.cursor()

    users = [
        ('driver1',  pbkdf2_sha256('driver123'),
         'driver',  'Иванов Иван Иванович'),
        ('manager1', pbkdf2_sha256('manager123'),
         'manager', 'Петрова Анна Сергеевна'),
        ('courier1', pbkdf2_sha256('courier123'),
         'courier', 'Сидоров Алексей Петрович'),
    ]

    for username, pw_hash, role, full_name in users:
        cur.execute(
            '''INSERT INTO users (username, password_hash, role, full_name)
               VALUES (%s,%s,%s,%s)
               ON CONFLICT (username) DO UPDATE
                 SET password_hash=EXCLUDED.password_hash,
                     full_name=EXCLUDED.full_name''',
            (username, pw_hash, role, full_name)
        )
        print(f'  + {username} ({role})')

    cur.close()
    conn.close()
    print('\nGot it! Users created:')
    print('  driver1  / driver123')
    print('  manager1 / manager123')
    print('  courier1 / courier123')


if __name__ == '__main__':
    main()
