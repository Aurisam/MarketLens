#!/usr/bin/env python
import os
import sys


def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    # Use the direct database connection for migrations when available.
    if len(sys.argv) > 1 and sys.argv[1] == 'migrate':
        if os.getenv('DATABASE_URL_UNPOOLED'):
            os.environ['DATABASE_URL'] = os.environ['DATABASE_URL_UNPOOLED']
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
