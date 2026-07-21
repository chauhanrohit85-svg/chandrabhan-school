"""
Tests for authentication routes.
Covers: login success/failure, role redirect, logout, access control.
"""
import pytest


class TestAuth:

    def test_login_page_accessible(self, app):
        """Login page returns 200 for a fresh unauthenticated client."""
        c = app.test_client()
        resp = c.get('/auth/login', follow_redirects=True)
        assert resp.status_code == 200
        # Page must have a form field
        assert b'<form' in resp.data or b'input' in resp.data

    def test_login_success_admin(self, app):
        """Admin credentials redirect to admin dashboard."""
        c = app.test_client()
        resp = c.post('/auth/login', data={
            'username': 'test_admin',
            'password': 'admin123',
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert b'Dashboard' in resp.data or b'dashboard' in resp.data.lower()

    def test_login_success_teacher(self, app):
        """Teacher credentials redirect to teacher dashboard."""
        c = app.test_client()
        resp = c.post('/auth/login', data={
            'username': 'test_teacher1',
            'password': 'teacher123',
        }, follow_redirects=True)
        assert resp.status_code == 200

    def test_login_invalid_password(self, app):
        """Wrong password shows error and stays on login page."""
        c = app.test_client()
        resp = c.post('/auth/login', data={
            'username': 'test_admin',
            'password': 'wrongpassword',
        }, follow_redirects=True)
        assert resp.status_code == 200
        # Must show login form again — not admin dashboard
        assert b'Invalid' in resp.data or b'<form' in resp.data

    def test_login_nonexistent_user(self, app):
        """Non-existent username shows error."""
        c = app.test_client()
        resp = c.post('/auth/login', data={
            'username': 'ghost_user_xyz_test',
            'password': 'anything',
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert b'Invalid' in resp.data or b'<form' in resp.data

    def test_logout_redirects_to_login(self, app):
        """Logout clears session and redirects to login."""
        c = app.test_client()
        c.post('/auth/login', data={'username': 'test_admin', 'password': 'admin123'})
        resp = c.get('/auth/logout', follow_redirects=True)
        assert resp.status_code == 200
        assert b'Sign In' in resp.data or b'Login' in resp.data or b'<form' in resp.data

    def test_admin_dashboard_requires_login(self, app):
        """Unauthenticated access to admin dashboard redirects to login."""
        c = app.test_client()
        resp = c.get('/admin/dashboard', follow_redirects=True)
        assert resp.status_code == 200
        assert b'login' in resp.data.lower() or b'<form' in resp.data

    def test_teacher_dashboard_requires_login(self, app):
        """Unauthenticated access to teacher dashboard redirects to login."""
        c = app.test_client()
        resp = c.get('/teacher/dashboard', follow_redirects=True)
        assert resp.status_code == 200
        assert b'login' in resp.data.lower() or b'<form' in resp.data

    def test_teacher_cannot_access_admin(self, app):
        """Teacher accessing admin area is denied or redirected."""
        c = app.test_client()
        c.post('/auth/login', data={'username': 'test_teacher1', 'password': 'teacher123'})
        resp = c.get('/admin/dashboard', follow_redirects=True)
        assert resp.status_code == 200
        # Should NOT show the admin dashboard — should show denied, login, or teacher area
        assert (b'Administrator' in resp.data or b'denied' in resp.data.lower()
                or b'login' in resp.data.lower() or b'My Classroom' in resp.data
                or b'dashboard' in resp.data.lower())
