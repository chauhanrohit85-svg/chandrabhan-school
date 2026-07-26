import os
import time
from app import create_app
from app.extensions import db

app = create_app(os.environ.get('FLASK_ENV', 'development'))

# Fail-safe database table initialization on boot with retry mechanism
with app.app_context():
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            db.create_all()
            break
        except Exception as e:
            app.logger.warning(f"Database connection attempt {attempt}/{max_retries} failed: {e}")
            if attempt < max_retries:
                time.sleep(2)
            else:
                app.logger.error("Failed to connect to database after 3 attempts.")
                raise e

# Automatically seed default master accounts & classes if database is empty
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
