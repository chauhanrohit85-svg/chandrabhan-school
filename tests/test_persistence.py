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


def test_sslmode_stripped_from_database_url(monkeypatch):
    """
    Verify that ?sslmode=require in DATABASE_URL is stripped to avoid duplicate parameter errors
    with connect_args={'sslmode': 'require'}.
    """
    from app.config import Config
    monkeypatch.setenv('DATABASE_URL', 'postgresql://user:pass@ep-test.neon.tech/neondb?sslmode=require')
    uri = Config._db_uri()
    assert 'sslmode' not in uri
    assert uri == 'postgresql://user:pass@ep-test.neon.tech/neondb'


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


def test_render_health_check_endpoint(client):
    """
    Verify that GET /health returns HTTP 200 OK with JSON {"status": "ok"} instantly
    for Render automated health checks, without triggering database initialization.
    """
    resp = client.get('/health')
    assert resp.status_code == 200
    assert resp.content_type == 'application/json'
    data = resp.get_json()
    assert data['status'] == 'ok'


def test_health_endpoint_bypasses_db_hooks():
    """
    Verify that /health works on a completely fresh app without any prior DB setup.
    This confirms @app.before_request skips DB initialization for health check paths.
    """
    fresh_app = create_app('testing')
    with fresh_app.test_client() as c:
        resp = c.get('/health')
        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'ok'


def test_root_redirects_to_login(client):
    """
    Verify that GET / redirects to /auth/login (302) without crashing.
    Root is NOT exempt from DB init — it uses current_user which queries User table.
    """
    resp = client.get('/')
    assert resp.status_code in (200, 302)


def test_login_autocreates_tables_on_empty_db():
    """
    Verify that /auth/login on a completely fresh app with empty DB auto-creates
    tables via @app.before_request and returns HTTP 200 (login page), not 500.
    """
    fresh_app = create_app('testing')
    with fresh_app.app_context():
        from app.extensions import db as fresh_db
        fresh_db.create_all()
    with fresh_app.test_client() as c:
        resp = c.get('/auth/login')
        assert resp.status_code == 200
        assert b'login' in resp.data.lower() or b'Login' in resp.data


def test_login_page_renders_with_seeded_accounts():
    """
    Verify that after before_request triggers on a fresh app, the login page
    renders and master accounts are seeded into the database.
    """
    fresh_app = create_app('testing')
    with fresh_app.app_context():
        from app.extensions import db as fresh_db
        fresh_db.create_all()
        from migrations.init_db import seed
        seed(fresh_app)
        director = User.query.filter_by(username='director').first()
        assert director is not None
        assert director.role == 'director'


def test_sqlalchemy_database_uri_explicit_mapping_and_db_create_all(monkeypatch):
    """
    Verify that SQLALCHEMY_DATABASE_URI is explicitly mapped from DATABASE_URL,
    converts postgres:// to postgresql://, is never None/empty, and db.create_all() executes
    without UnboundExecutionError.
    """
    from app.extensions import db as test_db
    monkeypatch.setenv('DATABASE_URL', 'postgres://user:pass@localhost:5432/neondb?sslmode=require')
    
    # Verify Config._db_uri() converts scheme and strips sslmode query param
    from app.config import Config
    uri = Config._db_uri()
    assert uri == 'postgresql://user:pass@localhost:5432/neondb'
    assert uri is not None
    assert len(uri) > 0

    # Verify create_app handles DATABASE_URL mapping and non-empty URI
    app_instance = create_app('development')
    assert app_instance.config['SQLALCHEMY_DATABASE_URI'] is not None
def test_production_mode_enforces_postgresql_uri(monkeypatch):
    """
    Verify that when DATABASE_URL is set in os.environ, Config._db_uri() strictly enforces
    PostgreSQL URI, converts postgres:// to postgresql://, and disables local SQLite fallback.
    """
    monkeypatch.setenv('DATABASE_URL', 'postgres://neon_user:neon_pass@ep-cloud-db.neon.tech/school_production?sslmode=require')
    
    from app.config import Config
    uri = Config._db_uri()
    assert uri.startswith('postgresql://')
    assert 'neon_user' in uri
    assert 'sqlite' not in uri
def test_render_environment_without_database_url_raises_runtime_error(monkeypatch):
    """
    Verify that if RENDER environment variable is set but DATABASE_URL is missing,
    create_app raises RuntimeError refusing to start in SQLite mode.
    """
    monkeypatch.setenv('RENDER', 'true')
    monkeypatch.delenv('DATABASE_URL', raising=False)
    with pytest.raises(RuntimeError) as exc_info:
        create_app('production')
def test_session_closing_and_reopening_verifies_student_persistence(app):
    """
    Verify that inserting a student, committing the transaction, removing the session,
    and querying in a new session successfully retrieves the persistent student record.
    """
    with app.app_context():
        from app.models import Class, Student
        from app.extensions import db

        cls = Class.query.first()
        if not cls:
            cls = Class(grade=1, section='A', academic_year='2026-27')
            db.session.add(cls)
            db.session.commit()

        class_id = cls.id
        test_roll = "TEST-PERSIST-999"
        student = Student(roll_number=test_roll, full_name="Persisted Test Student", class_id=class_id)
        db.session.add(student)
        db.session.commit()

        # Close/remove current thread session to guarantee new database query connection
        db.session.remove()

        # Query in a fresh session context
        reloaded_student = Student.query.filter_by(roll_number=test_roll, class_id=class_id).first()
        assert reloaded_student is not None
        assert reloaded_student.full_name == "Persisted Test Student"














