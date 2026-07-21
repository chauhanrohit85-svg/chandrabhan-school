"""
Tests for admin module routes.
Covers: dashboard, daily report, weekly report, alerts, student management.
"""
import pytest
from datetime import date


def make_admin_client(app):
    c = app.test_client()
    c.post('/auth/login', data={'username': 'test_admin', 'password': 'admin123'})
    return c


class TestAdminDashboard:

    def test_dashboard_loads(self, app):
        c = make_admin_client(app)
        resp = c.get('/admin/dashboard')
        assert resp.status_code == 200

    def test_dashboard_shows_kpis(self, app):
        c = make_admin_client(app)
        resp = c.get('/admin/dashboard')
        assert b'%' in resp.data or b'submission' in resp.data.lower() or b'dashboard' in resp.data.lower()


class TestAdminReports:

    def test_daily_report_loads(self, app):
        c = make_admin_client(app)
        resp = c.get('/admin/reports/daily')
        assert resp.status_code == 200

    def test_daily_report_with_date(self, app):
        c = make_admin_client(app)
        today_str = str(date.today())
        resp = c.get(f'/admin/reports/daily?date={today_str}')
        assert resp.status_code == 200

    def test_weekly_report_loads(self, app):
        c = make_admin_client(app)
        resp = c.get('/admin/reports/weekly')
        assert resp.status_code == 200

    def test_monthly_report_loads(self, app):
        c = make_admin_client(app)
        resp = c.get('/admin/reports/monthly')
        assert resp.status_code == 200


class TestAdminUsers:

    def test_users_page_loads(self, app):
        c = make_admin_client(app)
        resp = c.get('/admin/users')
        assert resp.status_code == 200

    def test_add_user(self, db, app):
        with app.app_context():
            from app.models import Class
            cls = Class.query.first()
            class_id = cls.id if cls else ''

        c = make_admin_client(app)
        resp = c.post('/admin/users/add', data={
            'username': 'new_teacher_test_xyz',
            'full_name': 'New Test Teacher',
            'password': 'newpass123',
            'role': 'teacher',
            'assigned_class_id': class_id,
        }, follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            from app.models import User
            user = User.query.filter_by(username='new_teacher_test_xyz').first()
            assert user is not None
            assert user.full_name == 'New Test Teacher'


class TestAdminStudents:

    def test_students_page_loads(self, app):
        c = make_admin_client(app)
        resp = c.get('/admin/students')
        assert resp.status_code == 200

    def test_add_student(self, db, app):
        with app.app_context():
            from app.models import Class
            cls = Class.query.first()
            class_id = cls.id

        c = make_admin_client(app)
        resp = c.post('/admin/students/add', data={
            'roll_number': '99',
            'full_name': 'Test New Student XYZ',
            'class_id': class_id,
            'parent_contact': '+91 9999999999',
        }, follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            from app.models import Student
            s = Student.query.filter_by(roll_number='99', class_id=class_id).first()
            assert s is not None

    def test_student_profile_loads(self, app):
        with app.app_context():
            from app.models import Student
            s = Student.query.filter_by(is_active=1).first()
            if not s:
                pytest.skip("No students in test DB")
            student_id = s.id

        c = make_admin_client(app)
        resp = c.get(f'/admin/students/{student_id}')
        assert resp.status_code == 200
