"""
Chandrabhan Singh Public School — Management Ecosystem
Entry point for local and cloud (Render/Gunicorn) deployment.
Crash-proof: create_app() is wrapped so Gunicorn always binds to 0.0.0.0:$PORT.
"""
import os
import logging

logger = logging.getLogger(__name__)

try:
    from app import create_app
    app = create_app(os.environ.get('FLASK_ENV', 'development'))
except Exception as e:
    # Emergency fallback — Gunicorn MUST bind to $PORT even if config is broken
    logger.critical(f"CRITICAL: create_app() failed: {e}. Starting emergency app.")
    from flask import Flask, jsonify
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'emergency-fallback'

    @app.route('/health')
    def health():
        return jsonify({'status': 'ok', 'mode': 'emergency'}), 200

    @app.route('/')
    def index():
        return 'Service starting — please retry in 30 seconds.', 503

if __name__ == '__main__':
    app.run(
        debug=os.environ.get('FLASK_DEBUG', 'True') == 'True',
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 5000))
    )
