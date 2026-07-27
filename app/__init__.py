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
from app.config import config

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger(__name__)

# Only /health is exempt — it never touches the database at all
_HEALTH_EXEMPT_PATHS = frozenset(('/health', '/api/health'))


def _init_database(app):
    """
    Safely create all database tables and seed master accounts.
    Returns True on success, False on failure.
    """
    try:
        with app.app_context():
            db.create_all()
            logger.info("db.create_all() completed successfully.")
            from migrations.init_db import seed as seed_db
            seed_db(app)
            return True
    except Exception as e:
        logger.exception(f"Database schema initialization / seeding error: {e}")
        return False


def create_app(config_name: str = 'default') -> Flask:
    app = Flask(__name__, instance_relative_config=True)

    # Load configuration — wrapped so bad DATABASE_URL doesn't crash Gunicorn
    try:
        app.config.from_object(config[config_name])
    except Exception as e:
        logger.exception(f"Config loading error: {e}. Falling back to minimal config.")
        app.config['SECRET_KEY'] = 'emergency-fallback-key'
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        app.config['SCHOOL_NAME'] = 'Chandrabhan Singh Public School'
        app.config['ACADEMIC_YEAR'] = '2026-27'

    # Ensure instance folder exists
    os.makedirs(app.instance_path, exist_ok=True)

    # Initialize extensions — never crashes on import
    try:
        db.init_app(app)
    except Exception as e:
        logger.exception(f"SQLAlchemy init error: {e}")
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

    # Inject school config into all templates
    @app.context_processor
    def inject_globals():
        return {
            'school_name': app.config.get('SCHOOL_NAME', 'Chandrabhan Singh Public School'),
            'academic_year': app.config.get('ACADEMIC_YEAR', '2026-27'),
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
        logger.exception(f"ProgrammingError caught — attempting auto-recovery: {error}")
        db.session.rollback()
        try:
            _init_database(app)
            _db_initialized = True
            # Retry the original request by redirecting
            return redirect(request.url)
        except Exception as recovery_error:
            logger.exception(f"Auto-recovery failed: {recovery_error}")
            return "Internal Server Error — database tables could not be created. Check Render logs.", 500

    @app.errorhandler(OperationalError)
    def handle_operational_error(error):
        """Auto-recover from connection or schema errors."""
        nonlocal _db_initialized
        logger.exception(f"OperationalError caught — attempting auto-recovery: {error}")
        db.session.rollback()
        try:
            _init_database(app)
            _db_initialized = True
            return redirect(request.url)
        except Exception as recovery_error:
            logger.exception(f"Auto-recovery failed: {recovery_error}")
            return "Internal Server Error — database connection failed. Check Render logs.", 500

    return app
