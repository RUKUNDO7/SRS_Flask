import os
from flask import Flask, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()


def create_app():
    app = Flask(__name__, template_folder='../templates', static_folder='../static')
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
        'DATABASE_URL',
        'postgresql://postgres:postgres@localhost:5432/eduregister'
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SESSION_PERMANENT'] = False
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

    db.init_app(app)
    migrate.init_app(app, db)          # ← Flask-Migrate hooked in
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'warning'

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        user = db.session.get(User, int(user_id))
        if user is None:
            return None
        # Verify the session token matches what's in the DB.
        # If the server restarted, all DB tokens were cleared → mismatch → force logout.
        stored_token = session.get('_token')
        if not stored_token or stored_token != user.session_token:
            return None
        return user

    # Register blueprints
    from app.routes.auth import auth_bp
    from app.routes.admin import admin_bp
    from app.routes.dos import dos_bp
    from app.routes.accountant import accountant_bp
    from app.routes.student import student_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(dos_bp, url_prefix='/dos')
    app.register_blueprint(accountant_bp, url_prefix='/accountant')
    app.register_blueprint(student_bp, url_prefix='/student')

    # Error handlers
    @app.errorhandler(403)
    def forbidden(e):
        from flask import render_template
        return render_template('errors/403.html'), 403

    @app.errorhandler(404)
    def not_found(e):
        from flask import render_template
        return render_template('errors/404.html'), 404

    with app.app_context():
        db.create_all()
        _invalidate_all_sessions()   # clears all tokens → forces everyone to re-login
        _seed_initial_data()

    return app


def _invalidate_all_sessions():
    """
    Called every time the app starts.
    Wipes all session tokens so any browser cookie from a previous run
    is rejected by load_user, effectively logging everyone out.
    """
    from app.models import User
    try:
        db.session.execute(
            db.update(User).values(session_token=None)
        )
        db.session.commit()
    except Exception:
        db.session.rollback()


def _seed_initial_data():
    """Create default admin/staff accounts if they don't exist."""
    from app.models import User
    from werkzeug.security import generate_password_hash

    defaults = [
        {'username': 'admin', 'email': 'admin@school.edu', 'role': 'admin', 'full_name': 'System Admin'},
        {'username': 'dos', 'email': 'dos@school.edu', 'role': 'dos', 'full_name': 'Director of Studies'},
        {'username': 'accountant', 'email': 'accountant@school.edu', 'role': 'accountant', 'full_name': 'School Accountant'},
    ]
    for d in defaults:
        if not User.query.filter_by(username=d['username']).first():
            user = User(
                username=d['username'],
                email=d['email'],
                role=d['role'],
                full_name=d['full_name'],
                password_hash=generate_password_hash('password123'),
            )
            db.session.add(user)
    db.session.commit()
