from flask import Blueprint
api_bp = Blueprint('api', __name__, url_prefix='/api')
from app.api import routes  # noqa: F401, E402
