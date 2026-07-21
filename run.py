"""
Chandrabhan Singh Public School — Management Ecosystem
Entry point for local and cloud (Render/Gunicorn) deployment.
"""
import os
from app import create_app

app = create_app(os.environ.get('FLASK_ENV', 'development'))

if __name__ == '__main__':
    app.run(
        debug=os.environ.get('FLASK_DEBUG', 'True') == 'True',
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 5000))
    )
