"""
Shared Flask extensions — initialized without the app (app factory pattern).
"""
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()

login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'warning'

# CSRFProtect must be init_app'd to have any effect. Setting WTF_CSRF_ENABLED
# alone does nothing — that config key is only consulted once this extension is
# registered against the app.
csrf = CSRFProtect()
