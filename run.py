import os
from app import create_app
from app.extensions import db

app = create_app(os.environ.get('FLASK_ENV', 'development'))

# Auto-create missing tables on boot without dropping existing data
with app.app_context():
    db.create_all()

# Automatically seed default accounts & classes if database is empty
try:
    from migrations.init_db import seed as seed_db
    seed_db(app)
except Exception as e:
    app.logger.error(f"Error seeding database on startup: {e}")

if __name__ == '__main__':
    app.run(
        debug=os.environ.get('FLASK_DEBUG', 'True') == 'True',
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 5000))
    )
