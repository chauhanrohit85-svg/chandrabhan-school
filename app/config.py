"""
Configuration for the school management system.

Database URI resolution lives in `resolve_database_uri()` and is the SINGLE
source of truth. It is called exactly once, by create_app(), BEFORE
db.init_app(app) — because Flask-SQLAlchemy 3.x builds the engine during
init_app(). Mutating SQLALCHEMY_DATABASE_URI after that point has no effect
on the live engine.
"""
import os
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

BASE_DIR = Path(__file__).resolve().parent.parent


class DatabaseConfigError(RuntimeError):
    """Raised when the database cannot be configured safely for this environment."""


def is_managed_host() -> bool:
    """True when running on Render (or any host that sets RENDER_SERVICE_ID)."""
    return bool(os.environ.get('RENDER') or os.environ.get('RENDER_SERVICE_ID'))


def normalise_postgres_url(url: str) -> str:
    """
    Convert legacy `postgres://` to `postgresql://` and strip `sslmode` from the
    query string. sslmode is supplied via connect_args instead, and having it in
    both places raises a duplicate-parameter error with psycopg2.
    """
    url = url.strip().rstrip('/')
    if url.startswith('postgres://'):
        url = url.replace('postgres://', 'postgresql://', 1)

    parsed = urlparse(url)
    if parsed.query:
        params = parse_qs(parsed.query)
        params.pop('sslmode', None)
        url = urlunparse(parsed._replace(query=urlencode(params, doseq=True)))
    return url


def postgres_driver_available() -> tuple[bool, str]:
    """
    Check that a PostgreSQL driver can actually be imported.

    Returns (available, detail). `detail` carries the underlying import error so
    it can be surfaced in logs instead of being swallowed — a silent ImportError
    here was the original cause of production falling back to SQLite.
    """
    try:
        import psycopg2  # noqa: F401
        return True, 'psycopg2'
    except Exception as exc:  # ImportError, or a broken/mismatched binary wheel
        psycopg2_error = f'{type(exc).__name__}: {exc}'

    try:
        import psycopg  # noqa: F401  (psycopg 3)
        return True, 'psycopg'
    except Exception as exc:
        psycopg3_error = f'{type(exc).__name__}: {exc}'

    return False, (
        f'No PostgreSQL driver importable. '
        f'psycopg2 -> {psycopg2_error}; psycopg -> {psycopg3_error}'
    )


def resolve_database_uri(config_name: str) -> tuple[str, dict]:
    """
    Resolve the database URI and engine options for this environment.

    Rules:
      - testing                      -> in-memory SQLite, always.
      - DATABASE_URL set             -> PostgreSQL, hard requirement. Never falls back.
      - managed host, no DATABASE_URL-> fatal. Ephemeral SQLite would silently lose data.
      - local dev, no DATABASE_URL   -> file-backed SQLite.

    Raises DatabaseConfigError rather than degrading to SQLite, so the failure is
    loud and specific instead of appearing later as vanishing records.
    """
    if config_name == 'testing':
        return 'sqlite:///:memory:', {'connect_args': {'check_same_thread': False}}

    raw_url = (os.environ.get('DATABASE_URL') or '').strip()

    if raw_url:
        url = normalise_postgres_url(raw_url)
        if not url.startswith('postgresql'):
            raise DatabaseConfigError(
                f"DATABASE_URL must be a PostgreSQL URL, got scheme "
                f"'{urlparse(url).scheme or url[:20]}'."
            )

        available, detail = postgres_driver_available()
        if not available:
            raise DatabaseConfigError(
                'DATABASE_URL is set but no PostgreSQL driver could be imported, so the '
                'application cannot reach the database.\n'
                f'  {detail}\n'
                '  Fix: ensure psycopg2-binary (or psycopg[binary]) installs for the '
                'Python version running the web process. psycopg2-binary ships no wheels '
                'for Python 3.13 — pin Python via a .python-version file.'
            )

        return url, {
            'pool_pre_ping': True,
            'pool_recycle': 300,
            'pool_timeout': 30,
            'pool_size': 5,
            'max_overflow': 10,
            'connect_args': {'sslmode': 'require', 'connect_timeout': 10},
        }

    if is_managed_host():
        raise DatabaseConfigError(
            'DATABASE_URL is not set. This host uses ephemeral storage, so a local '
            'SQLite file would be erased on every restart and all school records '
            'entered since the last deploy would be lost.\n'
            '  Fix: add DATABASE_URL (your Neon connection string) to the service '
            'environment variables and redeploy.'
        )

    # Local development only.
    sqlite_path = os.environ.get('SQLITE_DB_PATH') or (BASE_DIR / 'instance' / 'school.db')
    return f'sqlite:///{sqlite_path}', {'connect_args': {'check_same_thread': False}}


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-CHANGE-IN-PRODUCTION')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True

    # Over HTTPS, Flask-WTF additionally demands a Referer header and rejects the
    # request with "The referrer header is missing." if it is absent. Plenty of
    # ordinary setups strip that header — privacy settings, browser extensions,
    # school or office proxies — and the result is a teacher who simply cannot
    # sign in, with an error nobody outside software could interpret.
    # The CSRF token itself is unaffected and still required on every POST, and
    # session cookies remain SameSite=Lax, so cross-site form posts stay blocked.
    WTF_CSRF_SSL_STRICT = False
    SCHOOL_NAME = os.environ.get('SCHOOL_NAME', 'Chandrabhan Singh Public School')
    ACADEMIC_YEAR = os.environ.get('ACADEMIC_YEAR', '2026-27')
    ALERT_THRESHOLD = float(os.environ.get('ALERT_THRESHOLD', '2.0'))

    # Session cookie hardening. SECURE is enabled for real deployments only, so
    # local http:// development still works.
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = False


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True


class TestingConfig(Config):
    TESTING = True
    DEBUG = True
    WTF_CSRF_ENABLED = False


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig,
}
