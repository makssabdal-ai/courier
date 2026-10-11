import os
import io
from datetime import date, timedelta, datetime
from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import HttpResponse
from django.db import connection
from django.urls import reverse
from courier.auth_decorators import role_required
from courier.db_utils import fetchone, fetchall, execute, execute_returning
from courier.validators import validate_phone, validate_required
from courier.utils.qr_utils import (generate_qr_bytes, decode_qr_from_bytes,
                                     make_qr_data, parse_qr_data)


@role_required('manager')
def dashboard(request):
    stats = fetchone(
        '''SELECT
             COUNT(*) FILTER (WHERE status='delivered_to_office') AS office,
             COUNT(*) FILTER (WHERE status='ready_for_delivery')  AS ready,
             COUNT(*) FILTER (WHERE status='delivery_failed')     AS failed,
             COUNT(*) FILTER (WHERE status='error_missing')       AS missing,
             COUNT(*) FILTER (WHERE status='delivered')           AS delivered,
             COUNT(*) FILTER (WHERE status='returned_to_sender')  AS returned
           FROM packages'''
    )
    overdue = fetchall(
        '''SELECT id, track_number, internal_number, recipient_name,
                  recipient_address, expeditor_delivery_date
           FROM packages
           WHERE status NOT IN ('delivered','returned_to_sender','error_missing')
             AND expeditor_delivery_date <= NOW() - INTERVAL '14 days'
           ORDER BY expeditor_delivery_date ASC'''
    )
    return render(request, 'manager/dashboard.html', {'stats': stats, 'overdue': overdue})


@role_required('manager')
def delivery_waybill(request):
    date_filter = request.GET.get('date', '')
    waybills = _get_waybills('delivery', date_filter)
    return render(request, 'manager/waybill_list.html', {
        'waybills': waybills, 'date_filter': date_filter,
        'waybill_type': 'delivery', 'title': 'Накладные на доставку'
    })


@role_required('manager')
def view_delivery_waybill(request, wid):
    return _view_waybill(request, wid, 'delivery', 'manager_delivery_waybill')


@role_required('manager')
def return_waybill(request):
    date_filter = request.GET.get('date', '')
    waybills = _get_waybills('return', date_filter)
    return render(request, 'manager/waybill_list.html', {
        'waybills': waybills, 'date_filter': date_filter,
        'waybill_type': 'return', 'title': 'Накладные на возврат'
    })


@role_required('manager')
def view_return_waybill(request, wid):
    return _view_waybill(request, wid, 'return', 'manager_return_waybill')


@role_required('manager')
def missing_waybill(request):
    pkgs = fetchall(
        '''SELECT p.*, h.changed_at AS marked_at
           FROM packages p
           LEFT JOIN package_history h ON h.package_id=p.id AND h.new_status='error_missing'
           WHERE p.status='error_missing'
           ORDER BY h.changed_at DESC NULLS LAST'''
    )
    return render(request, 'manager/missing_waybill.html', {'packages': pkgs})


@role_required('manager')
def accept_packages(request):
    pkgs = fetchall(
        '''SELECT p.*, ds.confirmed_at AS session_date, u.full_name AS driver_name
           FROM packages p
           LEFT JOIN delivery_sessions ds ON p.session_id=ds.id
           LEFT JOIN users u ON ds.driver_id=u.id
           WHERE p.status='delivered_to_office'
           ORDER BY p.expeditor_delivery_date DESC, p.id'''
    )
    return render(request, 'manager/accept_packages.html', {'packages': pkgs})


@role_required('manager')
def edit_package(request, pid):
    pkg = fetchone("SELECT * FROM packages WHERE id=%s AND status='delivered_to_office'", (pid,))
    if not pkg:
        messages.warning(request, 'Посылка не найдена или уже обработана')
        return redirect('manager_accept_packages')

    if request.method == 'POST':
        errors = []
        try:
            s_name = validate_required(request.POST.get('sender_name', ''), 'ФИО отправителя')
        except ValueError as e:
            errors.append(str(e)); s_name = None
        try:
            s_addr = validate_required(request.POST.get('sender_address', ''), 'Адрес отправителя')
        except ValueError as e:
            errors.append(str(e)); s_addr = None
        try:
            r_name = validate_required(request.POST.get('recipient_name', ''), 'ФИО получателя')
        except ValueError as e:
            errors.append(str(e)); r_name = None
        try:
            r_addr = validate_required(request.POST.get('recipient_address', ''), 'Адрес доставки')
        except ValueError as e:
            errors.append(str(e)); r_addr = None
        try:
            r_phone = validate_phone(request.POST.get('recipient_phone', ''))
        except ValueError as e:
            errors.append(str(e)); r_phone = None

        if errors:
            for err in errors:
                messages.error(request, err)
            return render(request, 'manager/edit_package.html', {'pkg': pkg})

        execute(
            '''UPDATE packages SET
                 sender_name=%s, sender_address=%s,
                 recipient_name=%s, recipient_address=%s, recipient_phone=%s
               WHERE id=%s''',
            (s_name, s_addr, r_name, r_addr, r_phone, pid)
        )
        messages.success(request, 'Данные посылки успешно обновлены')
        return redirect('manager_accept_packages')

    return render(request, 'manager/edit_package.html', {'pkg': pkg})


@role_required('manager')
def mark_missing(request, pid):
    if request.method == 'POST':
        if fetchone("SELECT id FROM packages WHERE id=%s AND status='delivered_to_office'", (pid,)):
            with connection.cursor() as cur:
                cur.execute("UPDATE packages SET status='error_missing' WHERE id=%s", (pid,))
                cur.execute(
                    '''INSERT INTO package_history (package_id,old_status,new_status,changed_by,notes)
                       VALUES (%s,'delivered_to_office','error_missing',%s,'Посылка отсутствует')''',
                    (pid, request.session['user_id'])
                )
            messages.warning(request, 'Посылке присвоен статус "Ошибка: посылка отсутствует"')
    return redirect('manager_accept_packages')


@role_required('manager')
def confirm_package(request, pid):
    if request.method == 'POST':
        if fetchone("SELECT id FROM packages WHERE id=%s AND status='delivered_to_office'", (pid,)):
            with connection.cursor() as cur:
                cur.execute('SELECT next_internal_number()')
                internal = cur.fetchone()[0]
                cur.execute(
                    '''UPDATE packages SET
                         status='ready_for_delivery', internal_number=%s, ready_date=NOW()
                       WHERE id=%s''',
                    (internal, pid)
                )
                cur.execute(
                    '''INSERT INTO package_history
                           (package_id,old_status,new_status,changed_by,notes)
                       VALUES (%s,'delivered_to_office','ready_for_delivery',%s,%s)''',
                    (pid, request.session['user_id'], f'Принято. Внутренний номер: {internal}')
                )
            messages.success(request, f'Посылке присвоен внутренний номер {internal}')
    return redirect('manager_accept_packages')


@role_required('manager')
def confirm_all(request):
    if request.method == 'POST':
        pkgs = fetchall("SELECT id FROM packages WHERE status='delivered_to_office'")
        if not pkgs:
            messages.info(request, 'Нет посылок для подтверждения')
            return redirect('manager_accept_packages')

        confirmed_ids = []
        with connection.cursor() as cur:
            for pkg in pkgs:
                cur.execute('SELECT next_internal_number()')
                internal = cur.fetchone()[0]
                cur.execute(
                    '''UPDATE packages SET
                         status='ready_for_delivery', internal_number=%s, ready_date=NOW()
                       WHERE id=%s''',
                    (internal, pkg['id'])
                )
                cur.execute(
                    '''INSERT INTO package_history
                           (package_id,old_status,new_status,changed_by,notes)
                       VALUES (%s,'delivered_to_office','ready_for_delivery',%s,%s)''',
                    (pkg['id'], request.session['user_id'], f'Принято. Внутренний номер: {internal}')
                )
                confirmed_ids.append(str(pkg['id']))

        messages.success(request, f'Подтверждено {len(confirmed_ids)} посылок')
        return redirect(f'/manager/qr-generator/?batch={",".join(confirmed_ids)}')
    return redirect('manager_accept_packages')


@role_required('manager')
def form_delivery_list(request):
    now = datetime.now()
    can_form = now.hour >= 17

    office_cnt = fetchone("SELECT COUNT(*) AS c FROM packages WHERE status='delivered_to_office'")
    has_office = office_cnt and office_cnt['c'] > 0

    if request.method == 'POST':
        if not can_form:
            messages.warning(request, 'Формирование накладных доступно только после 17:00')
            return redirect('manager_form_delivery_list')
        if has_office:
            messages.warning(request, 'Сначала обработайте посылки со статусом "Доставлена в локальный офис"')
            return redirect('manager_form_delivery_list')

        failed = fetchall(
            '''SELECT id FROM packages
               WHERE status='delivery_failed' AND delivery_fail_count=1
               ORDER BY updated_at ASC LIMIT 5'''
        )
        ready_limit = 30 - len(failed)
        ready = fetchall(
            '''SELECT id FROM packages WHERE status='ready_for_delivery'
               ORDER BY expeditor_delivery_date ASC, ready_date ASC
               LIMIT %s''',
            (ready_limit,)
        )

        all_pkgs = list(failed) + list(ready)
        if not all_pkgs:
            messages.info(request, 'Нет посылок для формирования накладной')
            return redirect('manager_form_delivery_list')

        next_day = date.today() + timedelta(days=1)
        wid = None
        with connection.cursor() as cur:
            cur.execute(
                '''INSERT INTO waybills (waybill_type,delivery_date,created_by)
                   VALUES ('delivery',%s,%s) RETURNING id''',
                (next_day, request.session['user_id'])
            )
            wid = cur.fetchone()[0]
            for i, pkg in enumerate(all_pkgs):
                cur.execute(
                    'INSERT INTO waybill_items (waybill_id,package_id,sort_order) VALUES (%s,%s,%s)',
                    (wid, pkg['id'], i + 1)
                )
                cur.execute(
                    "UPDATE packages SET status='out_for_delivery' WHERE id=%s",
                    (pkg['id'],)
                )

        messages.success(request, f'Сформирована накладная #{wid}: {len(all_pkgs)} посылок на {next_day}')
        return redirect('manager_view_delivery_waybill', wid=wid)

    failed_prev = fetchall(
        '''SELECT id,track_number,internal_number,recipient_name,recipient_address,delivery_fail_count
           FROM packages WHERE status='delivery_failed' AND delivery_fail_count=1
           ORDER BY updated_at ASC LIMIT 5'''
    )
    ready_prev = fetchall(
        '''SELECT id,track_number,internal_number,recipient_name,recipient_address
           FROM packages WHERE status='ready_for_delivery'
           ORDER BY expeditor_delivery_date ASC, ready_date ASC
           LIMIT %s''',
        (30 - len(failed_prev),)
    )

    return render(request, 'manager/form_delivery_list.html', {
        'can_form': can_form, 'has_office': has_office,
        'failed_preview': failed_prev, 'ready_preview': ready_prev, 'now': now
    })


@role_required('manager')
def mark_return(request, pid):
    if request.method == 'POST':
        with connection.cursor() as cur:
            cur.execute(
                '''UPDATE packages SET status='returned_to_sender'
                   WHERE id=%s AND status NOT IN ('delivered','returned_to_sender')''',
                (pid,)
            )
            cur.execute(
                '''INSERT INTO package_history (package_id,old_status,new_status,changed_by,notes)
                   SELECT %s, status,'returned_to_sender',%s,'Истёк срок хранения (14 дней)'
                   FROM packages WHERE id=%s''',
                (pid, request.session['user_id'], pid)
            )
        messages.success(request, 'Посылка отмечена как "Возвращена отправителю"')
    return redirect('manager_dashboard')


@role_required('manager')
def weekly_export(request):
    import csv
    today = date.today()
    date_from = request.POST.get('date_from', '') or str(today - timedelta(days=7))
    date_to = request.POST.get('date_to', '') or str(today)
    status_filter = request.POST.get('status_filter', '')

    pkgs = None
    if request.method == 'POST':
        sql = '''SELECT p.track_number, p.internal_number, p.sender_name,
                        p.recipient_name, p.recipient_phone, p.recipient_address,
                        p.status, p.expeditor_delivery_date, p.updated_at
                 FROM packages p
                 WHERE DATE(p.updated_at) BETWEEN %s AND %s'''
        params = [date_from, date_to]
        if status_filter:
            sql += ' AND p.status=%s'
            params.append(status_filter)
        sql += ' ORDER BY p.updated_at DESC'
        pkgs = fetchall(sql, params)

        if request.POST.get('export_csv'):
            response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
            response['Content-Disposition'] = f'attachment; filename="export_{date_from}_{date_to}.csv"'
            writer = csv.writer(response)
            writer.writerow(['Трек-номер','Внутр.№','Отправитель','Получатель','Телефон','Адрес','Статус','Дата поступления','Обновлено'])
            for p in pkgs:
                writer.writerow([p['track_number'],p['internal_number'] or '',p['sender_name'],
                                  p['recipient_name'],p['recipient_phone'] or '',p['recipient_address'],
                                  p['status'],p['expeditor_delivery_date'] or '',p['updated_at']])
            return response

    return render(request, 'manager/weekly_export.html', {
        'packages': pkgs, 'date_from': date_from, 'date_to': date_to
    })


@role_required('manager')
def qr_generator(request):
    batch_str = request.GET.get('batch', '')
    if batch_str:
        try:
            ids = [int(x) for x in batch_str.split(',') if x.strip()]
        except ValueError:
            ids = []
        pkgs = []
        for pid in ids:
            pkg = fetchone(
                'SELECT id,track_number,internal_number,recipient_name FROM packages WHERE id=%s',
                (pid,)
            )
            if pkg:
                pkgs.append(pkg)
    else:
        pkgs = fetchall(
            '''SELECT id,track_number,internal_number,recipient_name
               FROM packages WHERE status='ready_for_delivery'
               ORDER BY ready_date DESC LIMIT 50'''
        )
    return render(request, 'manager/qr_generator.html', {'packages': pkgs})


@role_required('manager')
def get_qr(request, pid):
    pkg = fetchone('SELECT * FROM packages WHERE id=%s', (pid,))
    if not pkg:
        return HttpResponse(status=404)
    data = make_qr_data(
        pkg['track_number'], pkg['internal_number'] or '',
        pkg['recipient_name'], pkg['recipient_address']
    )
    img = generate_qr_bytes(data)
    return HttpResponse(img, content_type='image/png')


@role_required('manager')
def export_qr(request):
    if request.method == 'POST':
        ids = request.POST.getlist('pkg_ids')
        directory = request.POST.get('directory', '').strip() or 'qr_output'

        try:
            os.makedirs(directory, exist_ok=True)
        except OSError as e:
            messages.error(request, f'Не удалось создать директорию: {e}')
            return redirect('manager_qr_generator')

        count = 0
        for pid in ids:
            pkg = fetchone('SELECT * FROM packages WHERE id=%s', (pid,))
            if pkg:
                data = make_qr_data(
                    pkg['track_number'], pkg['internal_number'] or '',
                    pkg['recipient_name'], pkg['recipient_address']
                )
                img = generate_qr_bytes(data)
                fname = os.path.join(directory, f"{pkg['track_number']}.png")
                with open(fname, 'wb') as f:
                    f.write(img)
                count += 1

        messages.success(request, f'Сохранено {count} QR-кодов в папку: {directory}')
    return redirect('manager_qr_generator')


@role_required('manager')
def scan_return_qr(request):
    if request.method == 'POST':
        files = request.FILES.getlist('qr_images')
        scan_results = []
        ok_count = 0
        for f in files:
            if f:
                raw = decode_qr_from_bytes(f.read())
                if raw:
                    parsed = parse_qr_data(raw)
                    track = parsed.get('TRACK', '')
                    pkg = fetchone('SELECT * FROM packages WHERE track_number=%s', (track,))
                    if pkg:
                        scan_results.append({
                            'status': 'ok',
                            'track_number': track,
                            'recipient_name': pkg['recipient_name'],
                            'recipient_address': pkg['recipient_address'],
                            'package_id': pkg['id'],
                        })
                        ok_count += 1
                    else:
                        scan_results.append({'status': 'error', 'error': f'Посылка не найдена: {track}'})
                else:
                    scan_results.append({'status': 'error', 'error': 'QR-код не распознан'})
        request.session['qr_scan_results'] = scan_results
        request.session['qr_scan_ok_count'] = ok_count
        return redirect('manager_scan_return_qr')

    scan_results = request.session.get('qr_scan_results', [])
    ok_count = request.session.get('qr_scan_ok_count', 0)
    recent_returns = fetchall(
        '''SELECT w.id, w.created_at, COUNT(wi.id) AS item_count
           FROM waybills w LEFT JOIN waybill_items wi ON wi.waybill_id=w.id
           WHERE w.waybill_type='return'
           GROUP BY w.id ORDER BY w.created_at DESC LIMIT 10'''
    )
    return render(request, 'manager/scan_return_qr.html', {
        'scan_results': scan_results, 'ok_count': ok_count, 'recent_returns': recent_returns
    })


@role_required('manager')
def confirm_return_waybill(request):
    if request.method == 'POST':
        scan_results = request.session.get('qr_scan_results', [])
        pkg_ids = [str(r['package_id']) for r in scan_results if r.get('status') == 'ok' and r.get('package_id')]
        if not pkg_ids:
            messages.warning(request, 'Не выбраны посылки')
            return redirect('manager_scan_return_qr')

        wid = None
        with connection.cursor() as cur:
            cur.execute(
                '''INSERT INTO waybills (waybill_type,delivery_date,created_by)
                   VALUES ('return',%s,%s) RETURNING id''',
                (date.today(), request.session['user_id'])
            )
            wid = cur.fetchone()[0]
            for i, pid in enumerate(pkg_ids):
                cur.execute(
                    'INSERT INTO waybill_items (waybill_id,package_id,sort_order) VALUES (%s,%s,%s)',
                    (wid, pid, i + 1)
                )
                # Статус packages обновляет водитель при физическом подтверждении возврата (QR-скан)

        if 'qr_scan_results' in request.session:
            del request.session['qr_scan_results']
        messages.success(request, f'Накладная на возврат #{wid} создана. Водитель-экспедитор должен подтвердить приём посылок.')
        return redirect('manager_view_return_waybill', wid=wid)
    return redirect('manager_scan_return_qr')

@role_required('manager')
def change_delivery_date(request, pid):
    if request.method == 'POST':
        new_date_str = request.POST.get('planned_delivery_date', '').strip()
        try:
            new_date = date.fromisoformat(new_date_str)
        except ValueError:
            messages.error(request, 'Неверный формат даты')
            return redirect('manager_form_delivery_list')

        pkg = fetchone(
            "SELECT id, status FROM packages WHERE id=%s AND status IN ('ready_for_delivery','delivery_failed')",
            (pid,)
        )
        if not pkg:
            messages.warning(request, 'Посылка не найдена или недоступна для изменения даты')
            return redirect('manager_form_delivery_list')

        with connection.cursor() as cur:
            cur.execute(
                'UPDATE packages SET planned_delivery_date=%s WHERE id=%s',
                (new_date, pid)
            )
            cur.execute(
                '''INSERT INTO package_history (package_id,old_status,new_status,changed_by,notes)
                   VALUES (%s,%s,%s,%s,%s)''',
                (pid, pkg['status'], pkg['status'],
                 request.session['user_id'], f'Менеджер перенёс дату доставки на {new_date}')
            )
        messages.success(request, f'Дата доставки посылки #{pid} изменена на {new_date}')
    return redirect('manager_form_delivery_list')


def _get_waybills(wtype, date_filter):
    if date_filter:
        return fetchall(
            '''SELECT w.*, u.full_name AS author, COUNT(wi.id) AS item_count
               FROM waybills w LEFT JOIN users u ON w.created_by=u.id
               LEFT JOIN waybill_items wi ON wi.waybill_id=w.id
               WHERE w.waybill_type=%s AND w.delivery_date=%s
               GROUP BY w.id,u.full_name ORDER BY w.created_at DESC''',
            (wtype, date_filter)
        )
    return fetchall(
        '''SELECT w.*, u.full_name AS author, COUNT(wi.id) AS item_count
           FROM waybills w LEFT JOIN users u ON w.created_by=u.id
           LEFT JOIN waybill_items wi ON wi.waybill_id=w.id
           WHERE w.waybill_type=%s
           GROUP BY w.id,u.full_name ORDER BY w.created_at DESC LIMIT 30''',
        (wtype,)
    )


def _view_waybill(request, wid, wtype, back_url_name):
    waybill = fetchone(
        '''SELECT w.*, u.full_name AS author
           FROM waybills w LEFT JOIN users u ON w.created_by=u.id
           WHERE w.id=%s AND w.waybill_type=%s''',
        (wid, wtype)
    )
    if not waybill:
        messages.error(request, 'Накладная не найдена')
        return redirect(back_url_name)
    items = fetchall(
        '''SELECT p.*, wi.sort_order
           FROM waybill_items wi JOIN packages p ON wi.package_id=p.id
           WHERE wi.waybill_id=%s ORDER BY wi.sort_order''',
        (wid,)
    )
    return render(request, 'shared/view_waybill.html', {
        'waybill': waybill, 'items': items, 'back_url': reverse(back_url_name)
    })
