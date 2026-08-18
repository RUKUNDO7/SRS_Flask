from functools import wraps
from flask import abort, redirect, url_for
from flask_login import current_user


def role_required(*roles):
    """Restrict a view to specific roles.

    If the user is not authenticated at all, redirect to login (avoids a
    401 loop when flask-login's login_required is stacked on top).
    If authenticated but wrong role, return 403.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
            if current_user.role not in roles:
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator
