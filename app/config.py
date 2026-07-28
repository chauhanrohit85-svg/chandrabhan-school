"""
Configuration classes for the school management system.
Auto-detects DATABASE_URL env var for Render PostgreSQL compatibility.
Safely parses sslmode query params to prevent duplicate parameter errors.
"""
import os
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

BASE_DIR = Path(__file__).resolve().parent.parent


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-CHANGE-IN-PRODUCTION')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True
    SCHOOL_NAME = os.environ.get('SCHOOL_NAME', 'Chandrabhan Singh Public School')
    ACADEMIC_YEAR = os.environ.get('ACADEMIC_YEAR', '2026-27')
    ALERT_THRESHOLD = float(os.environ.get('ALERT_THRESHOLD', '2.0'))

    @staticmethod
    def _db_uri():
        """
        Auto-switch to PostgreSQL or custom SQLite path if configured (Render cloud).
        Safely strips sslmode from query string to avoid conflicts with connect_args.
        Hard crashes if running on Render and DATABASE_URL is missing.
        """
        url = (os.environ.get('DATABASE_URL') or '').strip().rstrip('/')
        is_render = bool(os.environ.get('RENDER') or os.environ.get('RENDER_SERVICE_ID'))

        if is_render and not url:
            print("\n==========================================================================")
            print("CRITICAL ERROR: DATABASE_URL is NOT set in Render Environment Variables!")
            print("Available Environment Variable Keys:")
            for key in sorted(os.environ.keys()):
                print(f"  - {key}")
            print("==========================================================================\n")
            raise RuntimeError("DATABASE_URL missing! Refusing to start in temporary SQLite mode on Render.")

        if url:
            # Fix Heroku/Render legacy postgres:// scheme
            if url.startswith('postgres://'):
                url = url.replace('postgres://', 'postgresql://', 1)
            if not url.startswith('postgresql://'):
                raise ValueError(f"Invalid DATABASE_URL scheme: '{url}'. Must start with postgresql://")
            # Strip sslmode from query params — we set it via connect_args to avoid duplicates
            parsed = urlparse(url)
            if parsed.query:
                params = parse_qs(parsed.query)
                params.pop('sslmode', None)
                clean_query = urlencode(params, doseq=True)
                url = urlunparse(parsed._replace(query=clean_query))
            return url
        sqlite_path = os.environ.get('SQLITE_DB_PATH')
        if sqlite_path:
            return f"sqlite:///{sqlite_path}"
        return f"sqlite:///{BASE_DIR / 'instance' / 'school.db'}"



def _get_engine_options(is_dev=False):
    """Build SQLAlchemy engine options. sslmode is ONLY set here to avoid duplicates."""
    try:
        uri = Config._db_uri()
    except Exception:
        # Fallback for broken DATABASE_URL during config class init — don't crash import
        return {'pool_pre_ping': True}

    options = {'pool_pre_ping': True}
    if uri.startswith('sqlite'):
        options['connect_args'] = {'check_same_thread': False}
    else:
        options['pool_recycle'] = 300
        options['pool_timeout'] = 30
        options['pool_size'] = 5
        options['max_overflow'] = 10
        options['connect_args'] = {'sslmode': 'require'}
    return options


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = Config._db_uri()
    SQLALCHEMY_ENGINE_OPTIONS = _get_engine_options(is_dev=True)


class ProductionConfig(Config):
    DEBUG = False
    WTF_CSRF_ENABLED = True
    SQLALCHEMY_DATABASE_URI = Config._db_uri()
    SQLALCHEMY_ENGINE_OPTIONS = _get_engine_options(is_dev=False)


class TestingConfig(Config):
    TESTING = True
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'connect_args': {'check_same_thread': False},
    }


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig,
}
