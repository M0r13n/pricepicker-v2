web: python wsgi.py
worker: celery worker -A project.server.celery_app:app --loglevel=info
# Always run DB migrations and check for new SVG's
postdeploy: python manage.py dev-db
