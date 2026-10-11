-- Seed data: default users
-- Passwords are hashed with Werkzeug's generate_password_hash

-- Run this after schema.sql
-- Default passwords: driver123, manager123, courier123

INSERT INTO users (username, password_hash, role, full_name) VALUES
  ('driver1',  'scrypt:32768:8:1$salt$hashplaceholder', 'driver',  'Иванов Иван Иванович'),
  ('manager1', 'scrypt:32768:8:1$salt$hashplaceholder', 'manager', 'Петрова Анна Сергеевна'),
  ('courier1', 'scrypt:32768:8:1$salt$hashplaceholder', 'courier', 'Сидоров Алексей Петрович')
ON CONFLICT (username) DO NOTHING;
