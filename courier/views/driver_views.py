import re
from datetime import date
from django.shortcuts import render, redirect
from django.contrib import messages
from django.db import connection
from django.urls import reverse
from courier.auth_decorators import role_required
from courier.db_utils import fetchone, fetchall, execute, execute_returning
from courier.validators import validate_track, validate_phone, validate_required
from courier.utils.qr_utils import decode_qr_from_bytes, parse_qr_data


@role_required('driver')
def dashboard(request):
    pending = fetchone(
        '''SELECT ds.id, ds.created_at, COUNT(p.id) AS pkg_count
           FROM delivery_sessions ds
           LEFT JOIN packages p ON p.session_id = ds.id
           WHERE ds.driver_id = %s AND ds.status = 'pending'
           GROUP BY ds.id
           ORDER BY ds.created_at DESC LIMIT 1''',
        (request.session['user_id'],)
    )
    return render(request, 'driver/dashboard.html', {'pending_session': pending})


@role_required('driver')
def delivery_waybill(request):
    date_filter = request.GET.get('date', '')
    waybills = _get_waybills('delivery', date_filter)
    return render(request, 'driver/waybill_list.html', {
        'waybills': waybills, 'date_filter': date_filter,
        'waybill_type': 'delivery', 'title': 'Накладные на доставку'
    })


@role_required('driver')
def view_delivery_waybill(request, wid):
    return _view_waybill(request, wid, 'delivery', 'driver_delivery_waybill')


@role_required('driver')
def return_waybill(request):
    date_filter = request.GET.get('date', '')
    waybills = _get_waybills('return', date_filter)
    return render(request, 'driver/waybill_list.html', {
        'waybills': waybills, 'date_filter': date_filter,
        'waybill_type': 'return', 'title': 'Накладные на возврат'
    })


@role_required('driver')
def view_return_waybill(request, wid):
    return _view_waybill(request, wid, 'return', 'driver_return_waybill')


@role_required('driver')
def input_packages(request):
    sess = _get_pending_session(request)
    pkgs = []
    if sess:
        pkgs = fetchall(
            'SELECT * FROM packages WHERE session_id = %s ORDER BY id',
            (sess['id'],)
        )
    return render(request, 'driver/input_packages.html',
                  {'pending_session': sess, 'packages': pkgs})


@role_required('driver')
def start_session(request):
    if request.method == 'POST':
        if not _get_pending_session(request):
            execute_returning(
                'INSERT INTO delivery_sessions (driver_id) VALUES (%s) RETURNING id',
                (request.session['user_id'],)
            )
    return redirect('driver_input_packages')


@role_required('driver')
def add_package(request):
    if request.method != 'POST':
        return redirect('driver_input_packages')

    sess = _get_pending_session(request)
    if not sess:
        messages.warning(request, 'Нет активной сессии. Начните новую.')
        return redirect('driver_input_packages')

    errors = []

    try:
        track = validate_track(request.POST.get('track_number', ''))
    except ValueError as e:
        errors.append(str(e))
        track = None

    try:
        s_name = validate_required(request.POST.get('sender_name', ''), 'ФИО отправителя')
    except ValueError as e:
        errors.append(str(e))
        s_name = None

    try:
        s_addr = validate_required(request.POST.get('sender_address', ''), 'Адрес отправителя')
    except ValueError as e:
        errors.append(str(e))
        s_addr = None

    try:
        r_name = validate_required(request.POST.get('recipient_name', ''), 'ФИО получателя')
    except ValueError as e:
        errors.append(str(e))
        r_name = None

    try:
        r_addr = validate_required(request.POST.get('recipient_address', ''), 'Адрес доставки')
    except ValueError as e:
        errors.append(str(e))
        r_addr = None

    try:
        r_phone = validate_phone(request.POST.get('recipient_phone', ''))
    except ValueError as e:
        errors.append(str(e))
        r_phone = None

    if errors:
        for err in errors:
            messages.error(request, err)
        return redirect('driver_input_packages')

    if fetchone('SELECT id FROM packages WHERE track_number = %s', (track,)):
        messages.warning(request, f'Посылка с трек-номером {track} уже зарегистрирована в системе')
        return redirect('driver_input_packages')

    execute(
        '''INSERT INTO packages
               (track_number, sender_name, sender_address,
                recipient_name, recipient_address, recipient_phone,
                status, session_id, created_by)
           VALUES (%s,%s,%s,%s,%s,%s,'pending',%s,%s)''',
        (track, s_name, s_addr, r_name, r_addr,
         r_phone, sess['id'], request.session['user_id'])
    )
    messages.success(request, f'Посылка {track} успешно добавлена')
    return redirect('driver_input_packages')


@role_required('driver')
def remove_package(request, pid):
    if request.method == 'POST':
        pkg = fetchone(
            '''SELECT p.id FROM packages p
               JOIN delivery_sessions ds ON p.session_id = ds.id
               WHERE p.id = %s AND ds.driver_id = %s AND ds.status = 'pending' ''',
            (pid, request.session['user_id'])
        )
        if pkg:
            execute('DELETE FROM packages WHERE id = %s', (pid,))
            messages.success(request, 'Посылка удалена из сессии')
        else:
            messages.error(request, 'Посылка не найдена или не принадлежит текущей сессии')
    return redirect('driver_input_packages')


@role_required('driver')
def confirm_session(request, sid):
    if request.method != 'POST':
        return redirect('driver_input_packages')

    sess = fetchone(
        "SELECT id FROM delivery_sessions WHERE id=%s AND driver_id=%s AND status='pending'",
        (sid, request.session['user_id'])
    )
    if not sess:
        messages.error(request, 'Сессия не найдена или уже подтверждена')
        return redirect('driver_input_packages')

    cnt = fetchone('SELECT COUNT(*) AS c FROM packages WHERE session_id=%s', (sid,))
    if not cnt or cnt['c'] == 0:
        messages.warning(request, 'Добавьте хотя бы одну посылку перед подтверждением')
        return redirect('driver_input_packages')

    with connection.cursor() as cur:
        cur.execute(
            "UPDATE delivery_sessions SET status='confirmed', confirmed_at=NOW() WHERE id=%s",
            (sid,)
        )
        cur.execute(
            '''UPDATE packages SET status='delivered_to_office', expeditor_delivery_date=NOW()
               WHERE session_id=%s AND status='pending' ''',
            (sid,)
        )
        cur.execute(
            '''INSERT INTO package_history (package_id, old_status, new_status, changed_by, notes)
               SELECT id,'pending','delivered_to_office',%s,'Подтверждено водителем-экспедитором'
               FROM packages WHERE session_id=%s''',
            (request.session['user_id'], sid)
        )

    messages.success(
        request,
        f'Сессия подтверждена. {cnt["c"]} посылок передано в локальный офис.'
    )
    return redirect('driver_dashboard')

@role_required('driver')
def scan_return_qr(request):
    if request.method == 'POST':
        action = request.POST.get('action', 'scan')

        if action == 'scan':
            files = request.FILES.getlist('qr_images')
            if not files:
                messages.warning(request, 'Выберите изображения QR-кодов')
                return redirect('driver_scan_return_qr')

            scan_errors = []
            scanned_tracks = []
            for f in files:
                raw = decode_qr_from_bytes(f.read())
                if raw:
                    parsed = parse_qr_data(raw)
                    track = parsed.get('TRACK', '')
                    if track:
                        scanned_tracks.append(track)
                    else:
                        scan_errors.append(f'Нет трек-номера в файле: {f.name}')
                else:
                    scan_errors.append(f'QR-код не распознан: {f.name}')

            ref_waybill = fetchone(
                '''SELECT w.id, w.created_at, u.full_name AS author
                   FROM waybills w LEFT JOIN users u ON w.created_by=u.id
                   WHERE w.waybill_type='return'
                   ORDER BY w.created_at DESC LIMIT 1'''
            )

            comparison = []
            if ref_waybill:
                waybill_pkgs = fetchall(
                    '''SELECT p.id, p.track_number, p.recipient_name, p.recipient_address, p.status
                       FROM waybill_items wi JOIN packages p ON wi.package_id=p.id
                       WHERE wi.waybill_id=%s''',
                    (ref_waybill['id'],)
                )
                waybill_map = {p['track_number']: p for p in waybill_pkgs}
                scanned_set = set(scanned_tracks)

                for track, pkg in waybill_map.items():
                    comparison.append({
                        'track_number': track,
                        'recipient_name': pkg['recipient_name'],
                        'recipient_address': pkg['recipient_address'],
                        'pkg_status': pkg['status'],
                        'match': 'ok' if track in scanned_set else 'missing',
                        'package_id': pkg['id'],
                    })
                for track in scanned_tracks:
                    if track not in waybill_map:
                        pkg = fetchone(
                            'SELECT id, recipient_name, recipient_address, status FROM packages WHERE track_number=%s',
                            (track,)
                        )
                        comparison.append({
                            'track_number': track,
                            'recipient_name': pkg['recipient_name'] if pkg else '—',
                            'recipient_address': pkg['recipient_address'] if pkg else '—',
                            'pkg_status': pkg['status'] if pkg else '',
                            'match': 'extra',
                            'package_id': pkg['id'] if pkg else None,
                        })
            else:

                for track in scanned_tracks:
                    pkg = fetchone(
                        'SELECT id, recipient_name, recipient_address, status FROM packages WHERE track_number=%s',
                        (track,)
                    )
                    comparison.append({
                        'track_number': track,
                        'recipient_name': pkg['recipient_name'] if pkg else '—',
                        'recipient_address': pkg['recipient_address'] if pkg else '—',
                        'pkg_status': pkg['status'] if pkg else '',
                        'match': 'new',
                        'package_id': pkg['id'] if pkg else None,
                    })

            request.session['driver_return_scan'] = comparison
            request.session['driver_return_waybill_id'] = ref_waybill['id'] if ref_waybill else None
            request.session['driver_scan_errors'] = scan_errors
            return redirect('driver_scan_return_qr')

        elif action == 'clear':
            for key in ('driver_return_scan', 'driver_return_waybill_id', 'driver_scan_errors'):
                request.session.pop(key, None)
            return redirect('driver_scan_return_qr')

        elif action == 'confirm':
            selected_ids = [pid for pid in request.POST.getlist('pkg_ids') if pid]
            if not selected_ids:
                messages.warning(request, 'Отметьте хотя бы одну посылку для подтверждения возврата')
                return redirect('driver_scan_return_qr')

            ref_wid = request.session.get('driver_return_waybill_id')
            with connection.cursor() as cur:
                if not ref_wid:
                    cur.execute(
                        '''INSERT INTO waybills (waybill_type, delivery_date, created_by)
                           VALUES ('return', %s, %s) RETURNING id''',
                        (date.today(), request.session['user_id'])
                    )
                    ref_wid = cur.fetchone()[0]

                count = 0
                for pid in selected_ids:
                    cur.execute(
                        'SELECT id FROM waybill_items WHERE waybill_id=%s AND package_id=%s',
                        (ref_wid, pid)
                    )
                    if not cur.fetchone():
                        cur.execute(
                            '''INSERT INTO waybill_items (waybill_id, package_id, sort_order)
                               VALUES (%s, %s,
                                 (SELECT COALESCE(MAX(sort_order),0)+1 FROM waybill_items WHERE waybill_id=%s))''',
                            (ref_wid, pid, ref_wid)
                        )
                    cur.execute(
                        '''UPDATE packages SET status='returned_to_sender'
                           WHERE id=%s AND status NOT IN ('returned_to_sender','delivered')''',
                        (pid,)
                    )
                    cur.execute(
                        '''INSERT INTO package_history (package_id, old_status, new_status, changed_by, notes)
                           SELECT %s, status, 'returned_to_sender', %s,
                                  'Возврат подтверждён водителем-экспедитором (QR-скан)'
                           FROM packages WHERE id=%s''',
                        (pid, request.session['user_id'], pid)
                    )
                    count += 1

            for key in ('driver_return_scan', 'driver_return_waybill_id', 'driver_scan_errors'):
                request.session.pop(key, None)

            messages.success(request, f'Возврат подтверждён: {count} посылок. Накладная #{ref_wid}.')
            return redirect('driver_view_return_waybill', wid=ref_wid)

    scan_results = request.session.get('driver_return_scan', [])
    scan_errors = request.session.get('driver_scan_errors', [])
    ref_wid = request.session.get('driver_return_waybill_id')

    recent_return = fetchone(
        '''SELECT w.id, w.created_at, u.full_name AS author, COUNT(wi.id) AS item_count
           FROM waybills w LEFT JOIN users u ON w.created_by=u.id
           LEFT JOIN waybill_items wi ON wi.waybill_id=w.id
           WHERE w.waybill_type='return'
           GROUP BY w.id, u.full_name ORDER BY w.created_at DESC LIMIT 1'''
    )

    ok_count = sum(1 for r in scan_results if r.get('match') in ('ok', 'extra', 'new'))
    missing_count = sum(1 for r in scan_results if r.get('match') == 'missing')
    extra_count = sum(1 for r in scan_results if r.get('match') == 'extra')

    return render(request, 'driver/scan_return_qr.html', {
        'scan_results': scan_results,
        'scan_errors': scan_errors,
        'recent_return': recent_return,
        'ref_wid': ref_wid,
        'ok_count': ok_count,
        'missing_count': missing_count,
        'extra_count': extra_count,
    })

def _get_pending_session(request):
    return fetchone(
        '''SELECT ds.id, ds.created_at, COUNT(p.id) AS pkg_count
           FROM delivery_sessions ds
           LEFT JOIN packages p ON p.session_id = ds.id
           WHERE ds.driver_id=%s AND ds.status='pending'
           GROUP BY ds.id ORDER BY ds.created_at DESC LIMIT 1''',
        (request.session['user_id'],)
    )


def _get_waybills(wtype, date_filter):
    if date_filter:
        return fetchall(
            '''SELECT w.*, u.full_name AS author, COUNT(wi.id) AS item_count
               FROM waybills w LEFT JOIN users u ON w.created_by=u.id
               LEFT JOIN waybill_items wi ON wi.waybill_id=w.id
               WHERE w.waybill_type=%s AND w.delivery_date=%s
               GROUP BY w.id, u.full_name ORDER BY w.created_at DESC''',
            (wtype, date_filter)
        )
    return fetchall(
        '''SELECT w.*, u.full_name AS author, COUNT(wi.id) AS item_count
           FROM waybills w LEFT JOIN users u ON w.created_by=u.id
           LEFT JOIN waybill_items wi ON wi.waybill_id=w.id
           WHERE w.waybill_type=%s
           GROUP BY w.id, u.full_name ORDER BY w.created_at DESC LIMIT 30''',
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
