from django import template

register = template.Library()

STATUS_RU = {
    'pending':              'Ожидает',
    'delivered_to_office':  'В локальном офисе',
    'ready_for_delivery':   'Готово к доставке',
    'out_for_delivery':     'Передано курьеру',
    'delivered':            'Доставлено',
    'delivery_failed':      'Не доставлено',
    'error_missing':        'Посылка отсутствует',
    'returned_to_sender':   'Возвращено отправителю',
    'draft':                'Черновик',
    'active':               'Активна',
    'pending_session':      'Ожидает подтверждения',
    'confirmed':            'Подтверждена',
}

WAYBILL_TYPE_RU = {
    'delivery': 'Накладная на доставку',
    'return':   'Накладная на возврат',
    'missing':  'Накладная об отсутствующих',
}


@register.filter(name='status_ru')
def status_ru(value):
    return STATUS_RU.get(str(value), str(value))


@register.filter(name='waybill_type_ru')
def waybill_type_ru(value):
    return WAYBILL_TYPE_RU.get(str(value), str(value))
