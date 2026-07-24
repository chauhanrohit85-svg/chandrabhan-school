from flask import Blueprint

director_bp = Blueprint('director', __name__, url_prefix='/director')

from app.director import routes  # noqa
