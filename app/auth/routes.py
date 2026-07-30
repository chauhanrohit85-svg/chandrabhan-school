"""
Authentication routes: login, logout.
Role-based redirect after login.
"""
import logging
from functools import wraps
from urllib.parse import urlparse

from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy import func

from app.auth import auth_bp
from app.extensions import db
from app.models import User

logger = logging.getLogger(__name__)

# Short enough to be memorable for staff who type it on a phone, long enough
# that it is not trivially guessable.
MIN_PASSWORD_LENGTH = 8


def _is_safe_redirect_target(target: str) -> bool:
    """
    Allow only same-site relative paths as a post-login redirect.

    `?next=` previously went straight into redirect(), so a crafted link could
    bounce a teacher to an external look-alike login page after signing in.
    """
    if not target:
        return False
    parsed = urlparse(target)
    return not parsed.scheme and not parsed.netloc and target.startswith('/')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET' and current_user.is_authenticated:
        return _role_redirect(current_user)

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember') == 'on'

        # Match the username without regard to case. Phone keyboards capitalise
        # the first letter by default, so a teacher typing their own username
        # gets "Chandresh" and an exact-match lookup rejects them with "invalid
        # username or password" — which reads as a wrong password, not a
        # capital letter.
        user = User.query.filter(
            func.lower(User.username) == username.lower(),
            User.is_active == 1,
        ).first()

        if user and user.check_password(password):
            login_user(user, remember=remember)
            flash(f'Welcome back, {user.full_name}!', 'success')
            next_page = request.args.get('next')
            if _is_safe_redirect_target(next_page):
                return redirect(next_page)
            return _role_redirect(user)

        flash('Invalid username or password. Please try again.', 'danger')

    return render_template('auth/login.html',
                           school_name=current_app.config['SCHOOL_NAME'])


@auth_bp.route('/password', methods=['GET', 'POST'])
@login_required
def change_password():
    """
    Let any signed-in user change their own password.

    Without this there was no self-service route at all: only an administrator
    could set passwords, and no one could reach the director or principal
    accounts through the interface — so the accounts handed to staff could never
    be rotated away from the values they were created with.
    """
    if request.method == 'POST':
        current = request.form.get('current_password', '')
        new = request.form.get('new_password', '')
        confirm = request.form.get('confirm_password', '')

        if not current_user.check_password(current):
            flash('Your current password is not correct.', 'danger')
        elif len(new) < MIN_PASSWORD_LENGTH:
            flash(f'Your new password must be at least {MIN_PASSWORD_LENGTH} characters long.', 'warning')
        elif new != confirm:
            flash('The two new passwords do not match. Please type them again.', 'warning')
        elif new == current:
            flash('Your new password must be different from your current one.', 'warning')
        else:
            try:
                current_user.set_password(new)
                db.session.commit()
                logger.info(f'Password changed for user {current_user.username}')
                flash('Your password has been changed. Use it the next time you sign in.', 'success')
                return _role_redirect(current_user)
            except Exception as exc:
                db.session.rollback()
                logger.exception('Password change failed')
                flash(f'Could not save the new password: {exc}', 'danger')

    return render_template('auth/change_password.html',
                           min_length=MIN_PASSWORD_LENGTH)


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('auth.login'))


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
