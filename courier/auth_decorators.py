from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages


def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(request, *args, **kwargs):
            if 'user_id' not in request.session:
                messages.warning(request, 'Необходима авторизация')
                return redirect('login')
            if request.session.get('role') not in roles:
                messages.error(request, 'Доступ запрещён')
                return redirect('login')
            return f(request, *args, **kwargs)
        return decorated
    return decorator
