"""
Flask application factory.
Registers all blueprints, extensions, and SQLite WAL mode.
"""
import os
from flask import Flask
from app.extensions import db, login_manager
from app.config import config


def create_app(config_name: str = 'default') -> Flask:
    app = Flask(__name__, instance_relative_config=True)

    # Load configuration
    app.config.from_object(config[config_name])

    # Ensure instance folder exists
    os.makedirs(app.instance_path, exist_ok=True)

    # Initialize extensions
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

    # Inject school config into all templates
    @app.context_processor
    def inject_globals():
        return {
            'school_name': app.config['SCHOOL_NAME'],
            'academic_year': app.config['ACADEMIC_YEAR'],
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

    # Root redirect
    from flask import redirect, url_for
    from flask_login import current_user

    @app.route('/')
    def index():
        if current_user.is_authenticated:
            if current_user.role == 'director':
                return redirect(url_for('director.dashboard'))
            elif current_user.role == 'admin':
                return redirect(url_for('admin.dashboard'))
            elif current_user.role == 'teacher':
                return redirect(url_for('teacher.dashboard'))
        return redirect(url_for('auth.login'))

    # Create tables on first run
    with app.app_context():
        db.create_all()

    return app
