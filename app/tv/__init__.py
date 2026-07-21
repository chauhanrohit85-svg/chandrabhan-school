from flask import Blueprint
tv_bp = Blueprint('tv', __name__, url_prefix='/tv')
from app.tv import routes  # noqa: F401, E402
