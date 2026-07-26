"""
Flask application factory.
Registers all blueprints, extensions, and SQLite WAL mode.
Defers database initialization to @app.before_request for immediate Gunicorn port binding.
Crash-proof: create_app() and all imports are wrapped so Gunicorn never exits on config errors.
"""
import os
import logging
from flask import Flask, jsonify, request, redirect, url_for
from flask_login import current_user
from app.extensions import db, login_manager
from app.config import config

logger = logging.getLogger(__name__)

# Paths that are exempt from database initialization — served instantly
_HEALTH_EXEMPT_PATHS = frozenset(('/', '/health', '/api/health'))


def create_app(config_name: str = 'default') -> Flask:
    app = Flask(__name__, instance_relative_config=True)

    # Load configuration — wrapped so bad DATABASE_URL doesn't crash Gunicorn
    try:
        app.config.from_object(config[config_name])
    except Exception as e:
        logger.error(f"Config loading error: {e}. Falling back to minimal config.")
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
        logger.error(f"SQLAlchemy init error: {e}")
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

    # -------------------------------------------------------------------
    # INSTANT ENDPOINTS — These NEVER touch the database
    # -------------------------------------------------------------------

    @app.route('/')
    def index():
        """Root redirect. Returns immediately for unauthenticated users."""
        if current_user.is_authenticated:
            if current_user.role == 'director':
                return redirect(url_for('director.dashboard'))
            elif current_user.role == 'admin':
                return redirect(url_for('admin.dashboard'))
            elif current_user.role == 'teacher':
                return redirect(url_for('teacher.dashboard'))
        return redirect(url_for('auth.login'))

    @app.route('/health')
    def health():
        """Render deployment health check — returns JSON instantly, zero DB queries."""
        return jsonify({'status': 'ok'}), 200

    # -------------------------------------------------------------------
    # LAZY DATABASE INITIALIZATION — only on real user routes
    # -------------------------------------------------------------------
    _db_initialized = False

    @app.before_request
    def ensure_db_initialized():
        nonlocal _db_initialized
        if _db_initialized or app.config.get('TESTING') or request.path in _HEALTH_EXEMPT_PATHS:
            return
        _db_initialized = True

        db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
        if 'postgresql' in db_uri:
            print("\n================================================================")
            print("  CONNECTED TO PERMANENT CLOUD DATABASE: PostgreSQL (Neon)")
            print("================================================================\n")
        else:
            print("\n================================================================")
            print("  CONNECTED TO LOCAL DATABASE: SQLite (Testing/Development)")
            print("================================================================\n")

        try:
            db.create_all()
            from migrations.init_db import seed as seed_db
            seed_db(app)
        except Exception as e:
            logger.error(f"Deferred database initialization error: {e}")

    return app
