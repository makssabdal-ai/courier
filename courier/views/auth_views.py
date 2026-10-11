import os
from django.conf import settings
from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.contrib import messages
from django.contrib.auth.hashers import check_password
from courier.db_utils import fetchone

ROLE_REDIRECT = {
    'driver':  'driver_dashboard',
    'manager': 'manager_dashboard',
    'courier': 'courier_dashboard',
}


def index(request):
    if 'user_id' in request.session:
        return redirect(ROLE_REDIRECT.get(request.session['role'], 'login'))
    return redirect('login')


def login_view(request):
    if 'user_id' in request.session:
        return redirect('index')

    error = None
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = fetchone('SELECT * FROM users WHERE username = %s', (username,))

        if user and check_password(password, user['password_hash']):
            request.session.flush()
            request.session['user_id']   = user['id']
            request.session['username']  = user['username']
            request.session['role']      = user['role']
            request.session['full_name'] = user['full_name']
            return redirect(ROLE_REDIRECT[user['role']])
        else:
            error = 'Неверный логин или пароль'

    return render(request, 'auth/login.html', {'error': error})


def logout_view(request):
    request.session.flush()
    return redirect('login')


def offline_view(request):
    return render(request, 'offline.html')


def sw_view(request):
    sw_path = os.path.join(settings.BASE_DIR, 'static', 'js', 'sw.js')
    with open(sw_path, 'r', encoding='utf-8') as f:
        content = f.read()
    response = HttpResponse(content, content_type='application/javascript')
    response['Service-Worker-Allowed'] = '/'
    return response
