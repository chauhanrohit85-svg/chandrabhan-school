"""
Flask application factory.

Database binding order matters and is not negotiable:

    1. resolve_database_uri()  -> decide the URI and engine options
    2. app.config[...] = ...   -> write them into config
    3. db.init_app(app)        -> Flask-SQLAlchemy BUILDS THE ENGINE HERE

Anything that changes SQLALCHEMY_DATABASE_URI after step 3 does not affect the
live engine. Flask-SQLAlchemy 3.x creates and caches engines inside init_app().
A previous version of this file tried to re-bind PostgreSQL from a
@before_request hook; that could never have worked, and it is why production
kept writing to SQLite while the config claimed otherwise.

There is no SQLite fallback in production. If PostgreSQL cannot be reached the
app refuses to start, because accepting writes into ephemeral storage loses
school records silently.
"""
import os
import time
import secrets
import logging

from flask import Flask, jsonify, redirect, url_for, render_template, render_template_string
from flask_login import current_user
from sqlalchemy import text

from app.extensions import db, login_manager, csrf
from app.config import config, resolve_database_uri, DatabaseConfigError, is_managed_host

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger(__name__)

CONNECT_RETRIES = 5
CONNECT_BACKOFF_SECONDS = 3


def _verify_connection(app):
    """
    Open a real connection and run SELECT 1.

    Neon's serverless PostgreSQL can be cold, so transient failures are retried
    with a bounded backoff. Returns the live engine name (e.g. 'postgresql').
    Raises the final exception if every attempt fails.
    """
    last_error = None
    for attempt in range(1, CONNECT_RETRIES + 1):
        try:
            with app.app_context():
                with db.engine.connect() as conn:
                    conn.execute(text('SELECT 1'))
                engine_name = db.engine.name
            logger.info(f'Database reachable on attempt {attempt}: engine={engine_name}')
            return engine_name
        except Exception as exc:
            last_error = exc
            logger.warning(f'Database connection attempt {attempt}/{CONNECT_RETRIES} failed: {exc}')
            if attempt < CONNECT_RETRIES:
                time.sleep(CONNECT_BACKOFF_SECONDS)
    raise last_error


def _init_schema(app):
    """Create any missing tables and seed master accounts. Never drops data."""
    with app.app_context():
        db.create_all()
        from migrations.init_db import seed as seed_db
        seed_db(app)


def _load_or_create_secret_key(app):
    """
    Return a stable session signing key, generating one on first run.

    A predictable key would let anyone forge a login cookie, but requiring the
    school to paste a random string into a hosting dashboard turned out to be
    the hardest step of setup. So the key is generated once and kept in the
    database: unpredictable, unchanged across restarts, and nothing to
    configure. SECRET_KEY in the environment still wins if it is set.
    """
    from app.models import AppSetting

    with app.app_context():
        existing = db.session.get(AppSetting, 'secret_key')
        if existing and existing.value:
            return existing.value

        generated = secrets.token_urlsafe(48)
        try:
            db.session.add(AppSetting(key='secret_key', value=generated))
            db.session.commit()
            logger.info('Generated a new session signing key and stored it in the database.')
            return generated
        except Exception:
            # Another worker booting at the same moment may have inserted it first.
            db.session.rollback()
            racer = db.session.get(AppSetting, 'secret_key')
            if racer and racer.value:
                return racer.value
            raise


def create_app(config_name: str = 'default') -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config.get(config_name, config['default']))

    # ── Secret key ────────────────────────────────────────────────────────
    # Read the environment directly rather than trusting the config class
    # attribute, which is evaluated once at import time and so would miss a
    # value set afterwards. If it is not set, one is generated and stored in the
    # database further down, once the connection is up.
    env_secret = os.environ.get('SECRET_KEY', '').strip()
    if env_secret:
        app.config['SECRET_KEY'] = env_secret

    # ── Database binding (must happen before db.init_app) ─────────────────
    uri, engine_options = resolve_database_uri(config_name)
    app.config['SQLALCHEMY_DATABASE_URI'] = uri
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = engine_options

    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    # SQLite (local development) concurrency pragmas.
    if uri.startswith('sqlite'):
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

    # ── Blueprints ────────────────────────────────────────────────────────
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

    # ── Connect and build the schema, once, at startup ────────────────────
    # Gunicorn's master process binds the listening socket before forking
    # workers, so doing this at import time does not delay port binding.
    app.config['DB_ENGINE_NAME'] = 'unavailable'
    app.config['DB_ERROR'] = None

    if not app.config.get('TESTING'):
        try:
            app.config['DB_ENGINE_NAME'] = _verify_connection(app)
            _init_schema(app)

            # Needs the schema to exist, so it happens after _init_schema.
            if not env_secret:
                app.config['SECRET_KEY'] = _load_or_create_secret_key(app)

            logger.info(f"Database ready: {app.config['DB_ENGINE_NAME']}")
        except Exception as exc:
            app.config['DB_ERROR'] = f'{type(exc).__name__}: {exc}'
            logger.exception('Database initialisation failed.')
            # On a managed host a broken database means every write would be
            # lost. Fail the deploy rather than serve a portal that silently
            # discards attendance and student records.
            if is_managed_host():
                raise DatabaseConfigError(
                    f'Could not establish the PostgreSQL connection required in production.\n'
                    f'  {app.config["DB_ERROR"]}'
                ) from exc

    # ── Template globals ──────────────────────────────────────────────────
    @app.context_processor
    def inject_globals():
        # Report the LIVE engine, never the config string. The config string can
        # disagree with the engine, and a badge that reads the config would have
        # shown a reassuring green "PostgreSQL" while writes went to SQLite.
        try:
            engine_name = db.engine.name
        except Exception:
            engine_name = app.config.get('DB_ENGINE_NAME', 'unavailable')

        return {
            'school_name': app.config.get('SCHOOL_NAME', 'Chandrabhan Singh Public School'),
            'academic_year': app.config.get('ACADEMIC_YEAR', '2026-27'),
            'db_engine_name': engine_name,
            'db_is_permanent': engine_name == 'postgresql',
            'is_render_env': is_managed_host(),
            'db_error': app.config.get('DB_ERROR'),
        }

    # ── Health endpoints ──────────────────────────────────────────────────
    @app.route('/health')
    def health():
        """Deployment health check. Touches no database."""
        return jsonify({'status': 'ok'}), 200

    @app.route('/health/db')
    def health_db():
        """
        Live database probe. Reports the real engine and whether a query
        succeeds. Deliberately returns no connection string or error detail —
        full diagnostics live on the director-only page.
        """
        try:
            with db.engine.connect() as conn:
                conn.execute(text('SELECT 1'))
            engine_name = db.engine.name
        except Exception:
            return jsonify({'status': 'error', 'engine': 'unavailable', 'permanent': False}), 503

        return jsonify({
            'status': 'ok',
            'engine': engine_name,
            'permanent': engine_name == 'postgresql',
        }), 200

    @app.route('/')
    def index():
        if current_user.is_authenticated:
            if current_user.role == 'director':
                return redirect(url_for('director.dashboard'))
            if current_user.role == 'admin':
                return redirect(url_for('admin.dashboard'))
            if current_user.role == 'teacher':
                return redirect(url_for('teacher.dashboard'))
        return redirect(url_for('auth.login'))

    # ── Expired / rejected form submissions ───────────────────────────────
    from flask_wtf.csrf import CSRFError

    @app.errorhandler(CSRFError)
    def handle_csrf_error(error):
        """
        Explain an expired form in words a teacher can act on.

        The default is a bare "400 Bad Request — The CSRF token is missing",
        which reads as a broken site rather than "your page went stale, open it
        again". The usual causes are a page left open for hours or one restored
        from the browser cache after a deploy.
        """
        logger.info(f'Rejected a stale form submission: {error.description}')
        return render_template('errors/session_expired.html',
                               reason=error.description), 400

    # ── Database error handling ───────────────────────────────────────────
    from sqlalchemy.exc import SQLAlchemyError

    @app.errorhandler(SQLAlchemyError)
    def handle_database_error(error):
        """
        Surface database failures instead of redirecting.

        The previous handler returned redirect(request.url). On a POST that
        turns into a GET and throws away the submitted form, so a failed write
        looked to the user like data that "disappeared" with no error shown.
        """
        logger.exception(f'Database error while handling request: {error}')
        db.session.rollback()
        return render_template_string(
            '{% extends "base.html" %}{% block title %}Database Error{% endblock %}'
            '{% block content %}<div style="padding:32px;">'
            '<h1 style="font-size:22px;font-weight:700;color:#991b1b;">Could not reach the database</h1>'
            '<p style="margin-top:12px;color:#475569;">Your last action was <strong>not saved</strong>. '
            'Please use your browser Back button and try again in a moment.</p>'
            '<p style="margin-top:12px;color:#475569;">If this keeps happening, ask the Director to open '
            '<code>/director/diagnostics</code> and send the details to support.</p>'
            '</div>{% endblock %}'
        ), 500

    return app
