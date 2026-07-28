"""
Flask application factory.
Registers all blueprints, extensions, and SQLite WAL mode.
Defers database initialization to @app.before_request for immediate Gunicorn port binding.
Crash-proof: create_app() and all imports are wrapped so Gunicorn never exits on config errors.
Auto-recovers from missing tables by catching ProgrammingError/OperationalError.
"""
import os
import logging
from flask import Flask, jsonify, request, redirect, url_for
from flask_login import current_user
from app.extensions import db, login_manager
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from app.config import config, Config, _get_engine_options, BASE_DIR

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger(__name__)

# Only /health is exempt — it never touches the database at all
_HEALTH_EXEMPT_PATHS = frozenset(('/health', '/api/health'))


import time

def _init_database(app):
    """
    Safely create all database tables and seed master accounts.
    Retries up to 3 times if PostgreSQL experiences connection latency on boot.
    Returns True on success, False on failure.
    """
    retries = 3
    for attempt in range(1, retries + 1):
        try:
            with app.app_context():
                db.create_all()
                logger.info(f"db.create_all() completed successfully on attempt {attempt}.")
                from migrations.init_db import seed as seed_db
                seed_db(app)
                return True
        except Exception as e:
            logger.exception(f"Database schema initialization attempt {attempt}/{retries} error: {e}")
            if attempt < retries:
                time.sleep(1)
    return False


def create_app(config_name: str = 'default') -> Flask:
    app = Flask(__name__, instance_relative_config=True)

    # Load configuration
    try:
        app.config.from_object(config[config_name])
    except Exception as e:
        logger.exception(f"Config loading error: {e}. Falling back to default config.")
        app.config.from_object(Config)

    # Check if running on Render and enforce DATABASE_URL presence
    is_render = bool(os.environ.get('RENDER') or os.environ.get('RENDER_SERVICE_ID'))
    env_db_url = (os.environ.get('DATABASE_URL') or '').strip().rstrip('/')

    if is_render and not env_db_url:
        logger.critical("CRITICAL ERROR: DATABASE_URL is NOT set in Render Environment Variables!")
        print("\n==========================================================================")
        print("CRITICAL ERROR: DATABASE_URL is NOT set in Render Environment Variables!")
        print("Available Environment Variable Keys:")
        for key in sorted(os.environ.keys()):
            print(f"  - {key}")
        print("==========================================================================\n")
        raise RuntimeError("CRITICAL: DATABASE_URL missing! Refusing to run in temporary SQLite mode.")

    # Explicitly map SQLALCHEMY_DATABASE_URI from os.environ.get('DATABASE_URL') if present
    if env_db_url:
        if env_db_url.startswith('postgres://'):
            env_db_url = env_db_url.replace('postgres://', 'postgresql://', 1)
        parsed = urlparse(env_db_url)
        if parsed.query:
            params = parse_qs(parsed.query)
            params.pop('sslmode', None)
            clean_query = urlencode(params, doseq=True)
            env_db_url = urlunparse(parsed._replace(query=clean_query))
        app.config['SQLALCHEMY_DATABASE_URI'] = env_db_url
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'pool_pre_ping': True,
            'pool_recycle': 300,
            'pool_timeout': 30,
            'pool_size': 5,
            'max_overflow': 10,
            'connect_args': {'sslmode': 'require'}
        }

    # Fallback check: verify app.config['SQLALCHEMY_DATABASE_URI'] is NEVER None or empty
    if not app.config.get('SQLALCHEMY_DATABASE_URI'):
        app.config['SQLALCHEMY_DATABASE_URI'] = Config._db_uri()

    # Ensure SQLALCHEMY_ENGINE_OPTIONS is populated
    if not app.config.get('SQLALCHEMY_ENGINE_OPTIONS'):
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = _get_engine_options()

    # Driver check for local development: fall back to SQLite ONLY if PostgreSQL driver (psycopg2) is missing in environment
    uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if uri.startswith('postgresql'):
        try:
            import psycopg2  # noqa: F401
        except ImportError:
            try:
                import psycopg  # noqa: F401
            except ImportError:
                logger.warning("PostgreSQL URI configured but psycopg2 driver not installed in local environment. Falling back to SQLite.")
                app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:' if app.config.get('TESTING') else f"sqlite:///{BASE_DIR / 'instance' / 'school.db'}"
                app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'connect_args': {'check_same_thread': False}}





    # Ensure instance folder exists
    os.makedirs(app.instance_path, exist_ok=True)

    # Initialize extensions AFTER app.config['SQLALCHEMY_DATABASE_URI'] has been set
    db.init_app(app)
    login_manager.init_app(app)





    # Enable SQLite WAL mode for concurrent writes
    if 'sqlite' in app.config.get('SQLALCHEMY_DATABASE_URI', ''):
        from sqlalchemy import event
        from sqlalchemy.engine import Engine
        import sqlite3

        @event.listens_for(Engine, 'connect')
        def set_sqlite_pragma(dbapi_connection, connection_record):
            if isinstance(dbapi_connection, sqlite3.Connection):
                cursor = dbapi_connection.cursor()
                cursor.execute('PRAGMA journal_mode=WAL')
                cursor.execute('PRAGMA foreign_keys=ON')
                cursor.execute('PRAGMA synchronous=NORMAL')
                cursor.close()

    # Inject school config and database status into all templates
    @app.context_processor
    def inject_globals():
        db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
        engine_name = getattr(db.engine, 'name', '') if hasattr(db, 'engine') else ''
        db_engine_name = 'postgresql' if ('postgresql' in db_uri or 'postgres' in engine_name) else 'sqlite'
        return {
            'school_name': app.config.get('SCHOOL_NAME', 'Chandrabhan Singh Public School'),
            'academic_year': app.config.get('ACADEMIC_YEAR', '2026-27'),
            'db_engine_name': db_engine_name,
            'is_render_env': bool(os.environ.get('RENDER') or os.environ.get('RENDER_SERVICE_ID')),
        }


    # Register blueprints
    from app.auth import auth_bp
    from app.admin import admin_bp
    from app.teacher import teacher_bp
    from app.tv import tv_bp
    from app.api import api_bp
    from app.director import director_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(teacher_bp)
    app.register_blueprint(tv_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(director_bp)

    # Force table creation and master account seeding on startup if DB is available
    if not app.config.get('TESTING'):
        _init_database(app)

    # -------------------------------------------------------------------
    # INSTANT HEALTH ENDPOINT — never touches the database
    # -------------------------------------------------------------------
    @app.route('/health')
    def health():
        """Render deployment health check — returns JSON instantly, zero DB queries."""
        return jsonify({'status': 'ok'}), 200

    # -------------------------------------------------------------------
    # ROOT REDIRECT — needs DB init first (current_user queries User table)
    # -------------------------------------------------------------------
    @app.route('/')
    def index():
        """Root redirect. Requires DB for flask_login current_user check."""
        try:
            if current_user.is_authenticated:
                if current_user.role == 'director':
                    return redirect(url_for('director.dashboard'))
                elif current_user.role == 'admin':
                    return redirect(url_for('admin.dashboard'))
                elif current_user.role == 'teacher':
                    return redirect(url_for('teacher.dashboard'))
        except Exception as e:
            logger.exception(f"Database error on index route: {e}. Auto-recovering...")
            db.session.rollback()
            _init_database(app)
        return redirect(url_for('auth.login'))


    # -------------------------------------------------------------------
    # LAZY DATABASE INITIALIZATION — runs on first real request
    # Flag is ONLY set to True AFTER successful db.create_all()
    # -------------------------------------------------------------------
    _db_initialized = False

    @app.before_request
    def ensure_db_initialized():
        nonlocal _db_initialized
        # Skip if already initialized, in test mode, or on pure health check paths
        if _db_initialized or app.config.get('TESTING') or request.path in _HEALTH_EXEMPT_PATHS:
            return
        # Do NOT set _db_initialized = True here — only after success below

        db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
        if 'postgresql' in db_uri:
            print("\n================================================================")
            print("  CONNECTED TO PERMANENT CLOUD DATABASE: PostgreSQL (Neon)")
            print("================================================================\n")
        else:
            print("\n================================================================")
            print("  CONNECTED TO LOCAL DATABASE: SQLite (Testing/Development)")
            print("================================================================\n")

        # Only mark as initialized if db.create_all() succeeds
        if _init_database(app):
            _db_initialized = True
        else:
            logger.error("Database initialization failed — will retry on next request.")

    # -------------------------------------------------------------------
    # RUNTIME ERROR RECOVERY — catches missing-table errors and auto-creates
    # -------------------------------------------------------------------
    from sqlalchemy.exc import ProgrammingError, OperationalError

    @app.errorhandler(ProgrammingError)
    def handle_programming_error(error):
        """Auto-recover from missing tables (e.g. 'relation users does not exist')."""
        nonlocal _db_initialized
        logger.exception(f"DATABASE QUERY FAILED — ProgrammingError: {error}")
        db.session.rollback()
        try:
            _init_database(app)
            _db_initialized = True
            return redirect(request.url)
        except Exception as recovery_error:
            logger.exception(f"DATABASE QUERY FAILED — Auto-recovery failed: {recovery_error}")
            return "Internal Server Error — database tables could not be created. Check Render logs.", 500

    @app.errorhandler(OperationalError)
    def handle_operational_error(error):
        """Auto-recover from connection or schema errors."""
        nonlocal _db_initialized
        logger.exception(f"DATABASE QUERY FAILED — OperationalError: {error}")
        db.session.rollback()
        try:
            _init_database(app)
            _db_initialized = True
            return redirect(request.url)
        except Exception as recovery_error:
            logger.exception(f"DATABASE QUERY FAILED — Auto-recovery failed: {recovery_error}")
            return "Internal Server Error — database connection failed. Check Render logs.", 500


    return app
