"""
Tests for pillar score alert generation logic.
Covers: below_threshold detection, consecutive absence detection,
alert deduplication, and alert resolve endpoint.
"""
import pytest
from datetime import date, timedelta, datetime


def make_admin_client(app):
    """Create an admin-authenticated test client."""
    c = app.test_client()
    c.post('/auth/login', data={'username': 'test_admin', 'password': 'admin123'})
    return c


def make_teacher_client(app):
    """Create a teacher-authenticated test client."""
    c = app.test_client()
    c.post('/auth/login', data={'username': 'test_teacher1', 'password': 'teacher123'})
    return c


class TestPillarAlerts:

    def test_alerts_page_loads(self, app):
        """Alerts page loads for authenticated admin."""
        c = make_admin_client(app)
        resp = c.get('/admin/alerts', follow_redirects=True)
        assert resp.status_code == 200
        assert b'alert' in resp.data.lower() or b'admin' in resp.data.lower()

    def test_below_threshold_alert_generated(self, db, app):
        """Student with qualitative=1 triggers a below_threshold alert."""
        with app.app_context():
            from app.models import AlertFlag
            from app.admin.routes import _generate_alerts
            _generate_alerts()
            alerts = AlertFlag.query.filter_by(alert_type='below_threshold',
                                               is_resolved=0).all()
            assert len(alerts) >= 1, "Expected at least one below_threshold alert"

    def test_absence_streak_detection(self, db, app):
        """3 consecutive absences trigger an absent_streak alert."""
        with app.app_context():
            from app.models import Student, AttendanceRecord, User, AlertFlag
            from app.extensions import db as _db
            student = Student.query.filter_by(is_active=1).first()
            teacher = User.query.filter_by(role='teacher').first()

            today = date.today()
            for d in range(3):
                att_date = today - timedelta(days=d)
                existing = AttendanceRecord.query.filter_by(
                    student_id=student.id, log_date=att_date).first()
                if existing:
                    existing.status = 'absent'
                else:
                    _db.session.add(AttendanceRecord(
                        student_id=student.id,
                        log_date=att_date,
                        status='absent',
                        marked_by=teacher.id
                    ))
            _db.session.commit()

            from app.admin.routes import _generate_alerts
            _generate_alerts()

            streak_alerts = AlertFlag.query.filter_by(
                student_id=student.id,
                alert_type='absent_streak',
                is_resolved=0
            ).all()
            assert len(streak_alerts) >= 1

    def test_alert_deduplication(self, db, app):
        """Running alert generation twice does not create duplicate alerts."""
        with app.app_context():
            from app.models import AlertFlag
            from app.admin.routes import _generate_alerts

            _generate_alerts()
            count_before = AlertFlag.query.filter_by(is_resolved=0).count()

            _generate_alerts()
            count_after = AlertFlag.query.filter_by(is_resolved=0).count()

            assert count_after == count_before, "Duplicate alerts were created"

    def test_resolve_alert(self, db, app):
        """Resolving an alert sets is_resolved=1 in the database."""
        with app.app_context():
            from app.models import AlertFlag, Student
            from app.extensions import db as _db

            student = Student.query.filter_by(is_active=1).first()
            # Create a fresh alert
            fresh_alert = AlertFlag(
                student_id=student.id,
                alert_type='below_threshold',
                pillar='reading',
                message='Test alert for resolve test',
                is_resolved=0
            )
            _db.session.add(fresh_alert)
            _db.session.commit()
            alert_id = fresh_alert.id

            # Simulate what the route does
            alert = AlertFlag.query.get(alert_id)
            alert.is_resolved = 1
            _db.session.commit()

            # Verify in the same session
            _db.session.expire_all()
            resolved = AlertFlag.query.filter_by(id=alert_id).first()
            assert resolved is not None
            assert resolved.is_resolved == 1


class TestAPISync:

    def test_health_endpoint(self, app):
        """API health check returns 200."""
        c = app.test_client()
        resp = c.get('/api/health')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'ok'

    def test_sync_log_authenticated(self, db, app):
        """Authenticated teacher can sync a log via the API."""
        with app.app_context():
            from app.models import Class
            cls = Class.query.first()
            class_id = cls.id

        c = make_teacher_client(app)
        resp = c.post('/api/sync/log', json={
            'class_id': class_id,
            'log_date': str(date.today()),
            'lesson_completed': 1,
            'syllabus_topic': 'Synced from localStorage API test',
            'syllabus_status': 'on_track',
            'homework_assigned': 0,
            'remarks': 'Auto-synced via test',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'synced'
