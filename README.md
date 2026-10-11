# КурьерПро — Система управления курьерской доставкой

Веб-приложение для автоматизации работы локального пункта выдачи и доставки посылок. Поддерживает три роли: **водитель-экспедитор**, **менеджер**, **курьер**.

---

## Технологии

| Компонент | Версия |
|---|---|
| Python | 3.x |
| Django | 3.2.16 |
| PostgreSQL | 16+ |
| psycopg2-binary | ≥ 2.9 |
| OpenCV | 4.9.0.80 |
| CSS | Кастомный (адаптивная вёрстка) |

---

## Структура проекта

```
de_2026_089/
├── courier/                        # Django-приложение
│   ├── views/
│   │   ├── auth_views.py           # Вход / выход
│   │   ├── driver_views.py         # Водитель-экспедитор
│   │   ├── manager_views.py        # Менеджер
│   │   └── courier_views.py        # Курьер
│   ├── utils/
│   │   └── qr_utils.py             # Генерация и декодирование QR-кодов (OpenCV)
│   ├── templatetags/
│   │   └── courier_tags.py         # Фильтры: status_ru, waybill_type_ru
│   ├── apps.py
│   ├── auth_decorators.py          # Декоратор @role_required
│   ├── db_utils.py                 # Обёртки fetchone / fetchall / execute
│   ├── validators.py               # Валидация трек-номера, телефона
│   └── urls.py
├── courier_project/                # Настройки Django
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── templates/
│   ├── base.html
│   ├── auth/
│   │   └── login.html
│   ├── driver/                     # Шаблоны водителя
│   ├── manager/                    # Шаблоны менеджера
│   ├── courier_tmpl/               # Шаблоны курьера
│   ├── shared/                     # Общие шаблоны (накладная)
│   └── offline.html                # Страница офлайн-режима (PWA)
├── static/
│   ├── css/style.css
│   ├── js/
│   │   ├── app.js
│   │   └── sw.js                   # Service Worker (PWA)
│   └── manifest.json               # PWA-манифест
├── db/
│   ├── schema.sql                  # SQL-схема + триггеры + функции
│   ├── seed_users.sql
│   └── seed.sql
├── docs/                           # UML-изображения
├── qr_output/                      # Сохранённые QR-коды (генерируется автоматически)
├── seed_users.py                   # Создание тестовых пользователей
├── manage.py
└── requirements.txt
```

---

## Установка и запуск

### 1. Требования

- Python 3.10+
- PostgreSQL 16+
- pip

### 2. Установка и активация виртуального окружения

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 4. Создание базы данных

```sql
-- В psql (под суперпользователем postgres):
CREATE USER courier_user WITH PASSWORD '<your-database-password>';
CREATE DATABASE courier_db OWNER courier_user;
```

```bash
# Применить схему:
psql -U courier_user -d courier_db -f db/schema.sql
```

### Настройка окружения

Задайте переменные в терминале перед запуском. Пример для PowerShell:

```powershell
$env:SECRET_KEY = python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
$env:DB_NAME = 'courier_db'
$env:DB_USER = 'courier_user'
$env:DB_PASSWORD = '<your-database-password>'
$env:DB_HOST = 'localhost'
$env:DB_PORT = '5432'
```

Файл `.env.example` описывает переменные; приложение не загружает его автоматически.
Приведённые ниже учётные записи предназначены только для демонстрации.

### 5. Создание пользователей

```bash
python seed_users.py
```

### 6. Запуск сервера

```bash
python manage.py runserver 8000
```

Приложение доступно по адресу: **http://127.0.0.1:8000**

---

## Учётные записи

| Логин | Пароль | Роль |
|---|---|---|
| driver1 | driver123 | Водитель-экспедитор |
| manager1 | manager123 | Менеджер |
| courier1 | courier123 | Курьер |

---

## Функциональность

### Водитель-экспедитор
- Пакетный ввод посылок по сессиям (с валидацией трек-номера `RU-NN-NNNNNNNNN`)
- Подтверждение приёма посылок из центрального склада
- Регистрация возвратов посылок с QR-сканированием
- Просмотр накладных на доставку и возврат

### Менеджер
- Приём посылок с автоматическим присвоением внутреннего номера (`ДДММ-XXXXXX`)
- Генерация QR-кодов (PNG) и их массовое сохранение
- Сканирование QR-кодов при возврате от курьера
- Формирование накладных на доставку (FIFO, до 30 поз., доступно после 17:00)
- Контроль сроков хранения (просрочены > 14 дней — выделяются на дашборде)
- Недельная выгрузка в CSV

### Курьер
- Просмотр актуальной накладной с приоритетной сортировкой
- Отметка результата доставки: доставлено / не доставлено / перенос даты
- QR-сканирование для быстрого поиска посылки

---

## База данных

Схема: `db/schema.sql`

Основные таблицы:
- `users` — учётные записи и роли
- `delivery_sessions` — сессии ввода посылок водителем
- `packages` — посылки (полный жизненный цикл)
- `waybills` / `waybill_items` — накладные (delivery / return / missing)
- `package_history` — аудит смен статусов (триггер `trg_package_status`)
- `monthly_counter` — атомарный счётчик внутренних номеров
- `district_stats` — статистика по районам (из датасета)

---

*КурьерПро — 26.06.2026*
Cмирнов Максим Сергеевич
