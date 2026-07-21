"""
Tests for teacher module routes.
Covers: dashboard, daily log UPSERT, attendance marking, pillar entry.
"""
import pytest
from datetime import date, datetime


class TestTeacherDashboard:

    def test_dashboard_loads(self, app):
        c = app.test_client()
        c.post('/auth/login', data={'username': 'test_teacher1', 'password': 'teacher123'})
        resp = c.get('/teacher/dashboard', follow_redirects=True)
        assert resp.status_code == 200

    def test_dashboard_shows_class(self, app):
        c = app.test_client()
        c.post('/auth/login', data={'username': 'test_teacher1', 'password': 'teacher123'})
        resp = c.get('/teacher/dashboard', follow_redirects=True)
        assert resp.status_code == 200
        assert b'Class 5' in resp.data or b'class' in resp.data.lower() or b'Dashboard' in resp.data


class TestDailyLog:

    def test_daily_log_form_loads(self, app):
        c = app.test_client()
        c.post('/auth/login', data={'username': 'test_teacher1', 'password': 'teacher123'})
        resp = c.get('/teacher/log/daily', follow_redirects=True)
        assert resp.status_code == 200
        assert b'log' in resp.data.lower() or b'lesson' in resp.data.lower()

    def test_submit_daily_log(self, db, app):
        """Submitting a daily log creates a DB record."""
        c = app.test_client()
        c.post('/auth/login', data={'username': 'test_teacher1', 'password': 'teacher123'})
        resp = c.post('/teacher/log/daily', data={
            'lesson_completed': 'on',
            'syllabus_topic': 'Test Fractions Chapter',
            'syllabus_status': 'on_track',
            'homework_assigned': 'on',
            'remarks': 'Good session.',
        }, follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            from app.models import TeacherDailyLog, User
            teacher = User.query.filter_by(username='test_teacher1').first()
            log = TeacherDailyLog.query.filter_by(
                teacher_id=teacher.id, log_date=date.today()
            ).first()
            assert log is not None
            assert log.lesson_completed == 1

    def test_update_daily_log(self, db, app):
        """Submitting again UPSERTS the log (one record per teacher per day)."""
        c = app.test_client()
        c.post('/auth/login', data={'username': 'test_teacher1', 'password': 'teacher123'})
        # Submit once
        c.post('/teacher/log/daily', data={
            'lesson_completed': 'on',
            'syllabus_topic': 'Initial Topic',
            'syllabus_status': 'on_track',
        }, follow_redirects=True)
        # Submit again (update)
        c.post('/teacher/log/daily', data={
            'lesson_completed': 'on',
            'syllabus_topic': 'Updated Topic UPSERT',
            'syllabus_status': 'ahead',
        }, follow_redirects=True)

        with app.app_context():
            from app.models import TeacherDailyLog, User
            teacher = User.query.filter_by(username='test_teacher1').first()
            logs = TeacherDailyLog.query.filter_by(
                teacher_id=teacher.id, log_date=date.today()
            ).all()
            # Must be exactly one log per teacher per day
            assert len(logs) == 1


class TestAttendance:

    def test_attendance_form_loads(self, app):
        c = app.test_client()
        c.post('/auth/login', data={'username': 'test_teacher1', 'password': 'teacher123'})
        resp = c.get('/teacher/attendance', follow_redirects=True)
        assert resp.status_code == 200
        assert b'Attendance' in resp.data or b'attendance' in resp.data.lower()

    def test_mark_attendance(self, db, app):
        """Teacher can mark attendance for all students."""
        with app.app_context():
            from app.models import Student, User
            teacher = User.query.filter_by(username='test_teacher1').first()
            cls = teacher.assigned_class
            students = Student.query.filter_by(class_id=cls.id, is_active=1).all()
            student_ids = [s.id for s in students]

        c = app.test_client()
        c.post('/auth/login', data={'username': 'test_teacher1', 'password': 'teacher123'})
        form_data = {}
        for sid in student_ids:
            form_data[f'status_{sid}'] = 'present'
        resp = c.post('/teacher/attendance', data=form_data, follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            from app.models import AttendanceRecord
            record = AttendanceRecord.query.filter_by(
                student_id=student_ids[0], log_date=date.today()
            ).first()
            assert record is not None
            assert record.status in ('present', 'late', 'absent')

    def test_rectify_attendance_audit(self, db, app):
        """Editing an attendance status flags it as is_edited=1 and sets edited_at."""
        c = app.test_client()
        c.post('/auth/login', data={'username': 'test_teacher1', 'password': 'teacher123'})

        with app.app_context():
            from app.models import Student, User
            teacher = User.query.filter_by(username='test_teacher1').first()
            student = Student.query.filter_by(class_id=teacher.assigned_class_id).first()
            student_id = student.id

        # First, ensure record exists for today with 'present' status
        c.post('/teacher/attendance', data={f'status_{student_id}': 'present'}, follow_redirects=True)

        # Now change status to 'absent' to trigger rectification
        resp = c.post('/teacher/attendance', data={f'status_{student_id}': 'absent'}, follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            from app.models import AttendanceRecord
            record = AttendanceRecord.query.filter_by(
                student_id=student_id, log_date=date.today()
            ).first()
            assert record is not None
            assert record.status == 'absent'
            assert record.is_edited == 1
            assert record.edited_at is not None


class TestMediaUploads:

    def test_log_media_attachment(self, db, app):
        """Submitting a daily log with photo base64 saves it in database."""
        c = app.test_client()
        c.post('/auth/login', data={'username': 'test_teacher1', 'password': 'teacher123'})
        
        mock_photo = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD..."
        resp = c.post('/teacher/log/daily', data={
            'lesson_completed': 'on',
            'syllabus_topic': 'Syllabus Topic with Photo',
            'syllabus_status': 'on_track',
            'photo_base64': mock_photo
        }, follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            from app.models import TeacherDailyLog, User
            teacher = User.query.filter_by(username='test_teacher1').first()
            log = TeacherDailyLog.query.filter_by(
                teacher_id=teacher.id, log_date=date.today()
            ).first()
            assert log is not None
            assert log.photo_base64 == mock_photo
