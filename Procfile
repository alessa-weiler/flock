web: gunicorn wsgi:application --bind 0.0.0.0:$PORT --timeout 120 --workers 2 --worker-class sync
worker: celery -A tasks worker --loglevel=info --concurrency=4 --max-tasks-per-child=100
