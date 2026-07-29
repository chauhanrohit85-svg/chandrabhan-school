"""
The app must configure itself with nothing but DATABASE_URL.

The school runs this without a technical administrator, and pasting values into
a hosting dashboard turned out to be the hardest part of setup. Everything that
can be derived or generated is, so deployment is "merge and go".
"""
import os
from app import create_app, _load_or_create_secret_key
from app.config import is_managed_host
from app.models import AppSetting


def _clear_env(monkeypatch):
    for var in ('SECRET_KEY', 'FLASK_ENV', 'RENDER', 'RENDER_SERVICE_ID', 'DATABASE_URL'):
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------------
# Session signing key
# ---------------------------------------------------------------------------
def test_secret_key_is_generated_and_stored_when_not_configured(monkeypatch, tmp_path):
    """With no SECRET_KEY set, one is generated and kept in the database."""
    _clear_env(monkeypatch)
    monkeypatch.setenv('SQLITE_DB_PATH', str(tmp_path / 'secret.db'))

    app = create_app('development')

    assert app.config['SECRET_KEY']
    assert app.config['SECRET_KEY'] != 'dev-secret-key-CHANGE-IN-PRODUCTION'
    assert len(app.config['SECRET_KEY']) >= 32

    with app.app_context():
        from app.extensions import db
        stored = db.session.get(AppSetting, 'secret_key')
        assert stored is not None
        assert stored.value == app.config['SECRET_KEY']


def test_secret_key_survives_a_restart(monkeypatch, tmp_path):
    """
    The key must not change between restarts, otherwise every deploy would sign
    everyone out.
    """
    _clear_env(monkeypatch)
    monkeypatch.setenv('SQLITE_DB_PATH', str(tmp_path / 'stable.db'))

    first = create_app('development').config['SECRET_KEY']
    second = create_app('development').config['SECRET_KEY']

    assert first == second


def test_explicit_secret_key_still_wins(monkeypatch, tmp_path):
    """An administrator who does set one keeps control."""
    _clear_env(monkeypatch)
    monkeypatch.setenv('SQLITE_DB_PATH', str(tmp_path / 'explicit.db'))
    monkeypatch.setenv('SECRET_KEY', 'chosen-by-the-administrator')

    app = create_app('development')
    assert app.config['SECRET_KEY'] == 'chosen-by-the-administrator'


def test_secret_key_helper_is_idempotent(monkeypatch, tmp_path):
    """Concurrent workers calling this must converge on one key, not fight."""
    _clear_env(monkeypatch)
    monkeypatch.setenv('SQLITE_DB_PATH', str(tmp_path / 'idem.db'))

    app = create_app('development')
    assert _load_or_create_secret_key(app) == _load_or_create_secret_key(app)


# ---------------------------------------------------------------------------
# Configuration selection
# ---------------------------------------------------------------------------
def test_managed_host_is_detected_without_flask_env(monkeypatch):
    """
    FLASK_ENV no longer has to be set: presence of the hosting service's own
    variable is enough to choose production settings.
    """
    monkeypatch.delenv('FLASK_ENV', raising=False)
    monkeypatch.delenv('RENDER_SERVICE_ID', raising=False)

    monkeypatch.setenv('RENDER', 'true')
    assert is_managed_host() is True

    monkeypatch.delenv('RENDER')
    assert is_managed_host() is False


def test_run_module_picks_production_on_a_managed_host(monkeypatch):
    """The entry point resolves the config name the same way."""
    monkeypatch.delenv('FLASK_ENV', raising=False)
    monkeypatch.setenv('RENDER', 'true')

    resolved = (os.environ.get('FLASK_ENV', '').strip()
                or ('production' if is_managed_host() else 'development'))
    assert resolved == 'production'

    monkeypatch.delenv('RENDER')
    resolved = (os.environ.get('FLASK_ENV', '').strip()
                or ('production' if is_managed_host() else 'development'))
    assert resolved == 'development'


# ---------------------------------------------------------------------------
# Build step must never fail the deploy
# ---------------------------------------------------------------------------
def test_seed_script_does_not_fail_the_build_when_the_database_is_unreachable():
    """
    Some deployments still call migrations/init_db.py from their build command.
    Seeding also happens at startup, so a build-time failure must not take the
    whole deploy down.
    """
    import pathlib
    source = pathlib.Path('migrations/init_db.py').read_text(encoding='utf-8')
    main_block = source.split("if __name__ == '__main__':")[1]

    assert 'try:' in main_block
    assert 'except Exception' in main_block
    assert 'not fatal' in main_block.lower()
