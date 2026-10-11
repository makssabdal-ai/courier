from datetime import date
from django.shortcuts import render, redirect
from django.contrib import messages
from django.db import connection
from courier.auth_decorators import role_required
from courier.db_utils import fetchone, fetchall, execute
from courier.utils.qr_utils import decode_qr_from_bytes, parse_qr_data


@role_required('courier')
def dashboard(request):
    selected_date_str = request.GET.get('date', date.today().isoformat())
    try:
        selected_date = date.fromisoformat(selected_date_str)
    except ValueError:
        selected_date = date.today()

    waybill = fetchone(
        '''SELECT w.id, w.delivery_date, COUNT(wi.id) AS pkg_count
           FROM waybills w
           LEFT JOIN waybill_items wi ON wi.waybill_id=w.id
           WHERE w.waybill_type='delivery' AND w.delivery_date=%s
           GROUP BY w.id LIMIT 1''',
        (selected_date,)
    )
    stats = None
    if waybill:
        stats = fetchone(
            '''SELECT
                 COUNT(*) FILTER (WHERE p.status='delivered') AS delivered,
                 COUNT(*) FILTER (WHERE p.status='delivery_failed') AS failed,
                 COUNT(*) FILTER (WHERE p.status='out_for_delivery') AS pending
               FROM waybill_items wi JOIN packages p ON wi.package_id=p.id
               WHERE wi.waybill_id=%s''',
            (waybill['id'],)
        )
        pkg_count = waybill['pkg_count']
    else:
        pkg_count = 0
    return render(request, 'courier_tmpl/dashboard.html', {
        'waybill': waybill, 'pkg_count': pkg_count, 'stats': stats,
        'selected_date': selected_date.isoformat(),
        'today': date.today().isoformat(),
    })


@role_required('courier')
def delivery_waybill(request):
    date_filter = request.GET.get('date', '')

    if date_filter:
        waybill = fetchone(
            "SELECT * FROM waybills WHERE waybill_type='delivery' AND delivery_date=%s "
            "ORDER BY created_at DESC LIMIT 1",
            (date_filter,)
        )
    else:
        waybill = fetchone(
            "SELECT * FROM waybills WHERE waybill_type='delivery' AND delivery_date=%s "
            "ORDER BY created_at DESC LIMIT 1",
            (date.today(),)
        )
        if not waybill:
            waybill = fetchone(
                "SELECT * FROM waybills WHERE waybill_type='delivery' "
                "ORDER BY delivery_date DESC, created_at DESC LIMIT 1"
            )

    items = []
    if waybill:
        items = fetchall(
            '''SELECT p.*, wi.package_id, wi.sort_order
               FROM waybill_items wi JOIN packages p ON wi.package_id=p.id
               WHERE wi.waybill_id=%s
                 AND p.status NOT IN ('returned_to_sender', 'error_missing')
               ORDER BY wi.sort_order''',
            (waybill['id'],)
        )

    return render(request, 'courier_tmpl/delivery_waybill.html', {
        'waybill': waybill, 'items': items, 'date_filter': date_filter
    })


@role_required('courier')
def mark_delivery(request, pid):
    pkg = fetchone('SELECT * FROM packages WHERE id=%s', (pid,))
    if not pkg:
        messages.error(request, 'Посылка не найдена')
        return redirect('courier_delivery_waybill')

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'delivered':
            with connection.cursor() as cur:
                cur.execute("UPDATE packages SET status='delivered' WHERE id=%s", (pid,))
                cur.execute(
                    '''INSERT INTO package_history (package_id,old_status,new_status,changed_by,notes)
                       VALUES (%s,%s,'delivered',%s,'Посылка вручена адресату')''',
                    (pid, pkg['status'], request.session['user_id'])
                )
            messages.success(request, 'Посылка отмечена как доставленная')

        elif action == 'failed':
            new_count = (pkg['delivery_fail_count'] or 0) + 1
            with connection.cursor() as cur:
                if new_count >= 2:
                    cur.execute(
                        '''UPDATE packages SET
                             status='ready_for_delivery',
                             delivery_fail_count=%s,
                             expeditor_delivery_date=NOW()
                           WHERE id=%s''',
                        (new_count, pid)
                    )
                    cur.execute(
                        '''INSERT INTO package_history (package_id,old_status,new_status,changed_by,notes)
                           VALUES (%s,%s,'ready_for_delivery',%s,
                                   'Доставка не удалась (повторно). Дата обновлена')''',
                        (pid, pkg['status'], request.session['user_id'])
                    )
                else:
                    cur.execute(
                        '''UPDATE packages SET status='delivery_failed', delivery_fail_count=%s
                           WHERE id=%s''',
                        (new_count, pid)
                    )
                    cur.execute(
                        '''INSERT INTO package_history (package_id,old_status,new_status,changed_by,notes)
                           VALUES (%s,%s,'delivery_failed',%s,'Доставка не удалась. Адресат недоступен')''',
                        (pid, pkg['status'], request.session['user_id'])
                    )
            messages.warning(request, 'Статус доставки обновлён')

        elif action == 'postpone':
            new_date_str = request.POST.get('postpone_date', '')
            try:
                new_date = date.fromisoformat(new_date_str)
            except ValueError:
                messages.error(request, 'Неверный формат даты')
                return redirect('courier_mark_delivery', pid=pid)

            with connection.cursor() as cur:
                cur.execute(
                    '''UPDATE packages SET status='ready_for_delivery', planned_delivery_date=%s
                       WHERE id=%s''',
                    (new_date, pid)
                )
                cur.execute(
                    '''INSERT INTO package_history (package_id,old_status,new_status,changed_by,notes)
                       VALUES (%s,%s,'ready_for_delivery',%s,%s)''',
                    (pid, pkg['status'], request.session['user_id'],
                     f'Доставка перенесена на {new_date}')
                )
                cur.execute(
                    '''SELECT id FROM waybills
                       WHERE waybill_type='delivery' AND delivery_date=%s LIMIT 1''',
                    (new_date,)
                )
                row = cur.fetchone()
                if row:
                    wid = row[0]
                else:
                    cur.execute(
                        '''INSERT INTO waybills (waybill_type,delivery_date,created_by,status)
                           VALUES ('delivery',%s,%s,'draft') RETURNING id''',
                        (new_date, request.session['user_id'])
                    )
                    wid = cur.fetchone()[0]

                cur.execute(
                    'SELECT id FROM waybill_items WHERE waybill_id=%s AND package_id=%s',
                    (wid, pid)
                )
                if not cur.fetchone():
                    cur.execute(
                        '''INSERT INTO waybill_items (waybill_id,package_id,sort_order)
                           VALUES (%s,%s,
                             (SELECT COALESCE(MAX(sort_order),0)+1 FROM waybill_items WHERE waybill_id=%s))''',
                        (wid, pid, wid)
                    )
            messages.success(request, f'Доставка перенесена на {new_date}')

        return redirect('courier_delivery_waybill')

    return render(request, 'courier_tmpl/mark_delivery.html', {
        'pkg': pkg, 'today': date.today().isoformat()
    })


@role_required('courier')
def scan_qr(request):
    if request.method == 'POST':
        f = request.FILES.get('qr_image')
        if not f:
            messages.warning(request, 'Выберите изображение')
            return redirect('courier_scan_qr')

        raw = decode_qr_from_bytes(f.read())
        if not raw:
            messages.error(request, 'QR-код не распознан')
            return redirect('courier_scan_qr')

        parsed = parse_qr_data(raw)
        track = parsed.get('TRACK', '')
        pkg = fetchone('SELECT id FROM packages WHERE track_number=%s', (track,))
        if not pkg:
            messages.error(request, f'Посылка с трек-номером {track} не найдена')
            return redirect('courier_scan_qr')

        return redirect('courier_mark_delivery', pid=pkg['id'])

    return render(request, 'courier_tmpl/scan_qr.html')
