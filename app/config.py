"""
Configuration classes for the school management system.
Auto-detects DATABASE_URL env var for Render PostgreSQL compatibility.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-CHANGE-IN-PRODUCTION')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True
    SCHOOL_NAME = os.environ.get('SCHOOL_NAME', 'Chandrabhan Singh Public School')
    ACADEMIC_YEAR = os.environ.get('ACADEMIC_YEAR', '2025-26')
    ALERT_THRESHOLD = float(os.environ.get('ALERT_THRESHOLD', '2.0'))

    @staticmethod
    def _db_uri():
        """Auto-switch to PostgreSQL or custom SQLite path if configured (Render cloud)."""
        url = os.environ.get('DATABASE_URL')
        if url:
            if url.startswith('postgres://'):
                url = url.replace('postgres://', 'postgresql://', 1)
            return url
        sqlite_path = os.environ.get('SQLITE_DB_PATH')
        if sqlite_path:
            return f"sqlite:///{sqlite_path}"
        return f"sqlite:///{BASE_DIR / 'instance' / 'school.db'}"


def _get_engine_options(is_dev=False):
    uri = Config._db_uri()
    options = {'pool_pre_ping': True}
    if uri.startswith('sqlite'):
        options['connect_args'] = {'check_same_thread': False}
    elif not is_dev:
        options['pool_recycle'] = 300
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
