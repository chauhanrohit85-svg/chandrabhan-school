"""
Pytest configuration and shared fixtures for all tests.
Uses an in-memory SQLite database — no file system state between runs.
"""
import pytest
from app import create_app
from app.extensions import db as _db
from app.models import User, Class, Student, TeacherDailyLog, AttendanceRecord, PillarScore


@pytest.fixture(scope='session')
def app():
    """Create application with testing config."""
    application = create_app('testing')
    with application.app_context():
        _db.create_all()
        _seed_test_data()
        yield application
        _db.session.remove()
        _db.drop_all()


@pytest.fixture(scope='session')
def db(app):
    return _db


# ── Client fixtures — function scope so each test gets a fresh session ──
@pytest.fixture()
def client(app):
    """Fresh unauthenticated client per test."""
    return app.test_client()


@pytest.fixture()
def admin_client(app):
    """Fresh authenticated admin client per test."""
    c = app.test_client()
    c.post('/auth/login', data={'username': 'test_admin', 'password': 'admin123'})
    return c


@pytest.fixture()
def teacher_client(app):
    """Fresh authenticated teacher client per test."""
    c = app.test_client()
    c.post('/auth/login', data={'username': 'test_teacher1', 'password': 'teacher123'})
    return c


@pytest.fixture()
def director_client(app):
    """Fresh authenticated director client per test."""
    c = app.test_client()
    c.post('/auth/login', data={'username': 'director', 'password': 'director123'}, follow_redirects=True)
    return c


def _seed_test_data():
    """Seed minimal data for tests."""
    from datetime import date, datetime

    # Admin
    admin = User(username='test_admin', full_name='Test Admin', role='admin')
    admin.set_password('admin123')
    _db.session.add(admin)

    # Director
    director = User(username='director', full_name='Test Director', role='director')
    director.set_password('director123')
    _db.session.add(director)

    # Class
    cls = Class(grade=5, section='A', academic_year='2025-26')
    _db.session.add(cls)
    _db.session.flush()

    # Teacher
    teacher = User(username='test_teacher1', full_name='Test Teacher',
                   role='teacher', assigned_class_id=cls.id)
    teacher.set_password('teacher123')
    _db.session.add(teacher)
    _db.session.flush()

    # Mappings
    from app.models import TeacherClassSubject
    mapping = TeacherClassSubject(teacher_id=teacher.id, class_id=cls.id, subject='General')
    _db.session.add(mapping)
    _db.session.flush()

    # Students
    students = []
    for i in range(1, 6):
        s = Student(roll_number=f'{i:02d}',
                    full_name=f'Test Student {i}',
                    class_id=cls.id,
                    parent_contact=f'+91 9000000{i:03d}')
        _db.session.add(s)
        _db.session.flush()
        students.append(s)

    # Attendance
    today = date.today()
    for s in students:
        _db.session.add(AttendanceRecord(
            student_id=s.id,
            log_date=today,
            status='present',
            marked_by=teacher.id
        ))

    # Pillar scores (including one below-threshold student)
    wk = datetime.now().isocalendar()[1]
    yr = datetime.now().year
    for s in students[:3]:
        for pillar in PillarScore.PILLARS:
            _db.session.add(PillarScore(
                student_id=s.id,
                pillar=pillar,
                subject='General',
                week_number=wk,
                year=yr,
                qualitative=3,
                quantitative_score=60.0,
                recorded_by=teacher.id
            ))

    # Student 4: below threshold for alert tests (qualitative=1 in all pillars)
    for pillar in PillarScore.PILLARS:
        _db.session.add(PillarScore(
            student_id=students[3].id,
            pillar=pillar,
            subject='General',
            week_number=wk,
            year=yr,
            qualitative=1,
            quantitative_score=10.0,
            recorded_by=teacher.id
        ))

    _db.session.commit()
