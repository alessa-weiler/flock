"""
WSGI Entry Point for Flock Application

This file serves as the entry point for WSGI servers (gunicorn, uWSGI, etc.)
and production deployments.

Usage:
    gunicorn wsgi:app --bind 0.0.0.0:8080 --workers 4
"""

import os
import sys

# Add src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Import Flask application from package
from app import app, init_database

# Initialize the database when the app starts
init_database()

# Create necessary directories
os.makedirs('data', exist_ok=True)
os.makedirs('logs', exist_ok=True)

# Gunicorn will use the 'app' object
application = app

# For local testing only (use gunicorn in production)
if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)