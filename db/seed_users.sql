-- Seed default users
-- Passwords stored as plain text temporarily; will be re-hashed by seed_users.py
-- Run seed_users.py instead of this file if Django is available

INSERT INTO users (username, password_hash, role, full_name) VALUES
  ('driver1',  '__needshash__',  'driver',  'Иванов Иван Иванович'),
  ('manager1', '__needshash__', 'manager', 'Петрова Анна Сергеевна'),
  ('courier1', '__needshash__', 'courier', 'Сидоров Алексей Петрович')
ON CONFLICT (username) DO NOTHING;
