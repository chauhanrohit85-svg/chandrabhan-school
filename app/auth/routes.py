"""
Authentication routes: login, logout.
Role-based redirect after login.
"""
from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from app.auth import auth_bp
from app.models import User
from app.extensions import db


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return _role_redirect(current_user)

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember') == 'on'

        user = User.query.filter_by(username=username, is_active=1).first()

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


def _role_redirect(user):
    if user.role == 'admin':
        return redirect(url_for('admin.dashboard'))
    elif user.role == 'teacher':
        return redirect(url_for('teacher.dashboard'))
    elif user.role == 'tv':
        # TV users go to their assigned class view
        if user.assigned_class_id:
            return redirect(url_for('tv.class_view', class_id=user.assigned_class_id))
    return redirect(url_for('auth.login'))
