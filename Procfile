web: gunicorn flask_runner:app
worker: celery worker -A Parsing_Task.cel -l INFO --max-memory-per-child=62500