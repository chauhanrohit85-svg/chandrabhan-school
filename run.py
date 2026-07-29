"""
Chandrabhan Singh Public School — Management Ecosystem
Entry point for local and cloud (Render/Gunicorn) deployment.

Startup failures are NOT swallowed here. A previous version caught every
exception and served a stub app, which hid fatal misconfiguration behind a
generic "service starting" page — including the database errors that caused
records to be written to ephemeral storage. A failed deploy that reports why is
far better than a running portal that loses school data.
"""
import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger(__name__)

from app import create_app  # noqa: E402

try:
    app = create_app(os.environ.get('FLASK_ENV', 'development'))
except Exception as exc:
    logger.critical('=' * 74)
    logger.critical('STARTUP FAILED — the application will not serve requests.')
    logger.critical(f'{type(exc).__name__}: {exc}')
    logger.critical('=' * 74)
    sys.exit(1)

if __name__ == '__main__':
    app.run(
        debug=os.environ.get('FLASK_DEBUG', 'True') == 'True',
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 5000))
    )
