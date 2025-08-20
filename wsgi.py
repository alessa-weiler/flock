import os
import sys

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(__file__))

# Import your Flask application
from app import app

# Initialize the database when the app starts
from app import init_database
init_database()

# Create necessary directories
os.makedirs('data', exist_ok=True)

# This is what gunicorn will look for
application = app

if __name__ == "__main__":
    # For local testing only
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)


if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)