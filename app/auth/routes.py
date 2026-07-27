"""
Authentication routes: login, logout.
Role-based redirect after login.
"""
from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from app.auth import auth_bp
from app.models import User
from app.extensions import db


import logging
from sqlalchemy.exc import ProgrammingError, OperationalError

logger = logging.getLogger(__name__)


def _ensure_tables_and_master_accounts():
    """Fail-safe table creation and master account seeding check before User queries."""
    try:
        db.create_all()
        from migrations.init_db import seed as seed_db
        seed_db(current_app)
    except Exception:
        logger.exception("DATABASE QUERY FAILED during table check:")


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    # Execute light health check before running User queries
    _ensure_tables_and_master_accounts()

    try:
        if request.method == 'GET' and current_user.is_authenticated:
            return _role_redirect(current_user)
    except Exception:
        logger.exception("DATABASE QUERY FAILED on GET /login:")
        db.session.rollback()

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember') == 'on'

        user = None
        try:
            user = User.query.filter_by(username=username, is_active=1).first()
        except Exception:
            logger.exception("DATABASE QUERY FAILED on POST /login User lookup:")
            db.session.rollback()
            _ensure_tables_and_master_accounts()
            try:
                user = User.query.filter_by(username=username, is_active=1).first()
            except Exception:
                logger.exception("DATABASE QUERY FAILED after recovery retry:")
                flash('Database connection issue. Please try again in a few moments.', 'danger')
                return render_template('auth/login.html',
                                       school_name=current_app.config['SCHOOL_NAME'])

        if user and user.check_password(password):
            login_user(user, remember=remember)
            flash(f'Welcome back, {user.full_name}!', 'success')
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            return _role_redirect(user)
        else:
            flash('Invalid username or password. Please try again.', 'danger')

    return render_template('auth/login.html',
                           school_name=current_app.config['SCHOOL_NAME'])




@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('auth.login'))


from functools import wraps

def director_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'director':
            flash('Access Denied: Director / Super-Admin privileges required.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


def _role_redirect(user):
    if user.role == 'director':
        return redirect(url_for('director.dashboard'))
    elif user.role == 'admin':
        return redirect(url_for('admin.dashboard'))
    elif user.role == 'teacher':
        return redirect(url_for('teacher.dashboard'))
    elif user.role == 'tv':
        # TV users go to their assigned class view
        if user.assigned_class_id:
            return redirect(url_for('tv.class_view', class_id=user.assigned_class_id))
    return redirect(url_for('auth.login'))
