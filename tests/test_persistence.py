"""
Tests for Data Persistence, Disable Dummy Seeding, Academic Session 2026-27, and Strict PostgreSQL Enforcement.
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


def test_strict_postgresql_uri_enforcement(monkeypatch):
    """
    Verify that setting an invalid DATABASE_URL scheme raises ValueError rather than falling back silently to SQLite.
    """
    from app.config import Config
    monkeypatch.setenv('DATABASE_URL', 'invalid_scheme://host/db')
    with pytest.raises(ValueError) as exc_info:
        Config._db_uri()
    assert 'Invalid DATABASE_URL scheme' in str(exc_info.value)


def test_post_route_commits_permanently(teacher_client, app):
    """
    Verify that POST requests to teacher add_student permanently commit student entries to the database.
    """
    resp = teacher_client.post('/teacher/students/add', data={
        'roll_number': '7788',
        'full_name': 'Permanent Test Student',
        'parent_contact': '+91 9999888877'
    }, follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        s = Student.query.filter_by(roll_number='7788').first()
        assert s is not None
        assert s.full_name == 'Permanent Test Student'


def test_multi_reboot_persistence(app):
    """
    Verify that records survive across multiple app context reboots and seed calls.
    """
    with app.app_context():
        from app.extensions import db
        cls = Class.query.first()
        s = Student(roll_number='6677', full_name='Reboot Student', class_id=cls.id)
        db.session.add(s)
        db.session.commit()
        s_id = s.id

    # Simulated Reboot 1
    with app.app_context():
        seed(app)
        rechecked_s1 = db.session.get(Student, s_id)
        assert rechecked_s1 is not None

    # Simulated Reboot 2
    with app.app_context():
        seed(app)
        rechecked_s2 = db.session.get(Student, s_id)
        assert rechecked_s2 is not None
        assert rechecked_s2.full_name == 'Reboot Student'


def test_postgresql_engine_sslmode_options(monkeypatch):
    """
    Verify that _get_engine_options includes sslmode=require and strips trailing slashes for PostgreSQL connections.
    """
    from app.config import Config, _get_engine_options
    monkeypatch.setenv('DATABASE_URL', 'postgresql://user:pass@ep-test.neon.tech/neondb/')
    uri = Config._db_uri()
    assert uri == 'postgresql://user:pass@ep-test.neon.tech/neondb'
    options = _get_engine_options()
    assert options['connect_args']['sslmode'] == 'require'
    assert options['pool_pre_ping'] is True


def test_deferred_app_initialization_instant_import():
    """
    Verify that create_app() instantiates instantly without making synchronous database calls.
    """
    import time
    start_time = time.time()
    application = create_app('development')
    elapsed = time.time() - start_time
    assert elapsed < 1.0  # Must instantiate in under 1 second
    assert application is not None


