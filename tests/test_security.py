"""
Regression tests for the security fixes:
  - CSRF protection is actually wired up (not just configured)
  - TV kiosk pages require authentication
  - post-login ?next= cannot redirect off-site
  - the storage badge reflects the live engine, not the config string
"""
import pytest

from app import create_app
from app.extensions import csrf
from app.models import Class, Student


# ---------------------------------------------------------------------------
# CSRF
# ---------------------------------------------------------------------------
def test_csrf_extension_is_registered(app):
    """
    WTF_CSRF_ENABLED does nothing on its own — CSRFProtect must be init_app'd.
    Setting only the config key left every POST route unprotected.
    """
    assert 'csrf' in app.extensions, 'CSRFProtect was never registered on the app'


def test_csrf_rejects_post_without_token(monkeypatch, tmp_path):
    """A POST carrying no CSRF token is rejected once protection is enforced."""
    monkeypatch.delenv('DATABASE_URL', raising=False)
    monkeypatch.delenv('RENDER', raising=False)
    monkeypatch.delenv('RENDER_SERVICE_ID', raising=False)
    monkeypatch.setenv('SQLITE_DB_PATH', str(tmp_path / 'csrf_check.db'))

    application = create_app('testing')
    application.config['WTF_CSRF_ENABLED'] = True
    csrf.init_app(application)

    with application.app_context():
        from app.extensions import db
        db.create_all()

    resp = application.test_client().post('/auth/login',
                                          data={'username': 'x', 'password': 'y'})
    assert resp.status_code == 400, 'POST without a CSRF token should be rejected'


def test_every_post_form_carries_a_csrf_token():
    """Each POST form in the templates must render a csrf_token field."""
    import pathlib
    import re

    form_re = re.compile(r'<form\b[^>]*?>', re.IGNORECASE | re.DOTALL)
    missing = []

    for path in sorted(pathlib.Path('app/templates').rglob('*.html')):
        src = path.read_text(encoding='utf-8')
        for m in form_re.finditer(src):
            tag = m.group(0)
            if 'method=' not in tag.lower() or 'post' not in tag.lower():
                continue
            if 'csrf_token' not in src[m.end():m.end() + 300]:
                missing.append(f'{path.as_posix()}:{src[:m.start()].count(chr(10)) + 1}')

    assert not missing, 'POST forms without a CSRF token: ' + ', '.join(missing)


# ---------------------------------------------------------------------------
# TV kiosk authentication
# ---------------------------------------------------------------------------
def test_tv_class_view_requires_login(client, app):
    """
    /tv/<id> publishes student names, roll numbers and attendance. It used to be
    reachable by anyone who guessed the URL.
    """
    with app.app_context():
        class_id = Class.query.first().id

    resp = client.get(f'/tv/{class_id}')
    assert resp.status_code in (301, 302)
    assert '/auth/login' in resp.headers['Location']


def test_tv_class_list_requires_login(client):
    resp = client.get('/tv/list')
    assert resp.status_code in (301, 302)
    assert '/auth/login' in resp.headers['Location']


def test_tv_page_does_not_leak_student_names_when_anonymous(client, app):
    with app.app_context():
        class_id = Class.query.first().id
        a_student = Student.query.filter_by(class_id=class_id).first().full_name

    body = client.get(f'/tv/{class_id}', follow_redirects=True).get_data(as_text=True)
    assert a_student not in body


def test_staff_can_open_tv_view(teacher_client, app):
    """Signed-in staff still reach the kiosk page normally."""
    with app.app_context():
        class_id = Class.query.first().id

    resp = teacher_client.get(f'/tv/{class_id}')
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Open redirect
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('hostile', [
    'https://evil.example.com/login',
    '//evil.example.com/login',
    'http://evil.example.com',
])
def test_login_next_param_cannot_leave_the_site(client, hostile):
    """
    ?next= went straight into redirect(), so a crafted link could bounce a
    teacher to an external look-alike page immediately after signing in.
    """
    resp = client.post(f'/auth/login?next={hostile}',
                       data={'username': 'test_admin', 'password': 'admin123'})
    assert resp.status_code in (301, 302)
    assert 'evil.example.com' not in resp.headers['Location']


def test_login_next_param_allows_relative_path(client):
    resp = client.post('/auth/login?next=/admin/students',
                       data={'username': 'test_admin', 'password': 'admin123'})
    assert resp.status_code in (301, 302)
    assert resp.headers['Location'].endswith('/admin/students')


# ---------------------------------------------------------------------------
# Storage reporting honesty
# ---------------------------------------------------------------------------
def test_storage_badge_follows_live_engine_not_config(app):
    """
    The badge must not be driven by SQLALCHEMY_DATABASE_URI. Rewriting that
    string after init_app() does not move the engine, so a config-driven badge
    would have claimed "PostgreSQL" while writes went to SQLite.
    """
    from app.director.routes import _describe_storage

    with app.app_context():
        app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://fake:fake@fake/fake'
        backend, _status = _describe_storage()

    assert 'SQLite' in backend, 'storage description trusted the config string'


def test_no_default_passwords_in_source():
    """
    Bootstrap passwords must not be hardcoded. Shipping 'director123' in the
    repository hands a super-admin account to anyone who reads the source.
    """
    import pathlib

    banned = ('director123', 'admin123', 'teacher123')
    offenders = []
    for path in list(pathlib.Path('app').rglob('*.py')) + \
                list(pathlib.Path('app/templates').rglob('*.html')) + \
                [pathlib.Path('migrations/init_db.py')]:
        text = path.read_text(encoding='utf-8')
        for token in banned:
            if token in text:
                offenders.append(f'{path.as_posix()} contains {token!r}')

    assert not offenders, '; '.join(offenders)
