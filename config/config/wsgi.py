"""WSGI serverio įėjimo taškas; Render aplinkoje šį application objektą paleidžia Gunicorn."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_wsgi_application()
