from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
import secrets
from app.models import User, Student
from app import db

auth_bp = Blueprint('auth', __name__)

ROLE_DASHBOARDS = {
    'admin': 'admin.dashboard',
    'dos': 'dos.dashboard',
    'accountant': 'accountant.dashboard',
    'student': 'student.dashboard',
}


@auth_bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for(ROLE_DASHBOARDS.get(current_user.role, 'auth.login')))
    return redirect(url_for('auth.login'))


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for(ROLE_DASHBOARDS.get(current_user.role, 'auth.login')))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password) and user.is_active:
            token = secrets.token_hex(32)
            user.session_token = token
            db.session.commit()
            login_user(user)
            session['_token'] = token
            flash(f'Welcome back, {user.full_name}!', 'success')
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            return redirect(url_for(ROLE_DASHBOARDS.get(user.role, 'auth.login')))
        flash('Invalid username or password.', 'danger')

    return render_template('auth/login.html')


@auth_bp.route('/student-portal', methods=['GET', 'POST'])
def student_login():
    """
    Public student lookup — no password required.
    A student enters their full name to see their assigned class.
    """
    student = None
    not_found = False

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        if full_name:
            # Case-insensitive name match via the User join
            from app.models import User as UserModel
            user = UserModel.query.filter(
                UserModel.full_name.ilike(full_name),
                UserModel.role == 'student'
            ).first()
            if user and user.student_profile:
                student = user.student_profile
            else:
                not_found = True

    return render_template('auth/student_portal.html',
                           student=student, not_found=not_found)


@auth_bp.route('/logout')
@login_required
def logout():
    current_user.session_token = None
    db.session.commit()
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))
