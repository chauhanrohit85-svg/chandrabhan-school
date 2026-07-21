"""
Chandrabhan Singh Public School — Management Ecosystem
Entry point for local and cloud (Render/Gunicorn) deployment.
"""
import os
from app import create_app

app = create_app(os.environ.get('FLASK_ENV', 'development'))

# Automatically initialize and seed database on startup if empty
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
