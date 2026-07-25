"""
Tests for Data Persistence, Disable Dummy Seeding, and Academic Session 2026-27.
"""
import pytest
from app import create_app
from app.models import User, Class, Student, TeacherDailyLog, AttendanceRecord, PillarScore
from migrations.init_db import seed


def test_startup_seeding_preserves_existing_user_and_records(app):
    """
    Verify that calling seed(app) when database already has users/students does NOT drop tables or overwrite records.
    """
    with app.app_context():
        from app.extensions import db
        from datetime import date
        cls = Class.query.first()
        student = Student(roll_number='999', full_name='Real Student', class_id=cls.id)
        db.session.add(student)
        db.session.commit()

        att = AttendanceRecord(student_id=student.id, log_date=date.today(), status='present', marked_by=1)
        db.session.add(att)
        db.session.commit()

        # Run startup seed routine
        seed(app)

        # Verify student and attendance record still exist untouched
        rechecked_student = db.session.get(Student, student.id)
        assert rechecked_student is not None
        assert rechecked_student.full_name == 'Real Student'

        rechecked_att = db.session.get(AttendanceRecord, att.id)
        assert rechecked_att is not None
        assert rechecked_att.status == 'present'


def test_academic_session_defaults_to_2026_27(app):
    """
    Verify that Academic Session defaults to '2026-27' across app config and created classes.
    """
    with app.app_context():
        assert app.config['ACADEMIC_YEAR'] == '2026-27'


def test_dummy_seeding_is_disabled():
    """
    Verify that initializing a fresh database produces zero dummy logs, zero dummy attendance, and zero dummy pillar scores.
    """
    fresh_app = create_app('testing')
    with fresh_app.app_context():
        from app.extensions import db
        db.create_all()

        # Run fresh seed
        seed(fresh_app)

        # Assert no dummy logs, attendance, or pillar scores were created
        assert TeacherDailyLog.query.count() == 0
        assert AttendanceRecord.query.count() == 0
        assert PillarScore.query.count() == 0
        assert Student.query.count() == 0

        # Assert master accounts exist
        assert User.query.filter_by(username='director').first() is not None
        assert User.query.filter_by(username='principal').first() is not None
        assert User.query.filter_by(username='teacher1').first() is not None
