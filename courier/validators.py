import re
import html

PHONE_RE = re.compile(
    r'^\+7[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}$'
)
TRACK_RE = re.compile(r'^RU-\d{2}-\d{9}$')
MAX_STR_LEN = 255


def validate_phone(phone):
    if not phone:
        return None
    cleaned = phone.strip()
    if not cleaned:
        return None
    if not PHONE_RE.match(cleaned):
        raise ValueError(
            'Неверный формат телефона. '
            'Используйте: +7XXXXXXXXXX или +7 (XXX) XXX-XX-XX'
        )
    return cleaned


def validate_track(track):
    if not track or not track.strip():
        raise ValueError('Трек-номер обязателен для заполнения')
    cleaned = track.strip().upper()
    if not TRACK_RE.match(cleaned):
        raise ValueError(
            'Неверный формат трек-номера. '
            'Требуется: RU-XX-XXXXXXXXX (например, RU-77-123456789)'
        )
    return cleaned


def validate_required(value, field_name):
    if not value or not str(value).strip():
        raise ValueError(f'Поле «{field_name}» обязательно для заполнения')
    cleaned = str(value).strip()
    if len(cleaned) > MAX_STR_LEN:
        raise ValueError(
            f'Поле «{field_name}» не должно превышать {MAX_STR_LEN} символов'
        )
    return cleaned


def sanitize(value):
    if value is None:
        return ''
    return html.escape(str(value).strip())
