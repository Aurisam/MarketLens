#!/usr/bin/env python
"""Django valdymo komandų įėjimo taškas: runserver, migrate ir update_market_data."""
import os
import sys


def main():
    """Parenka nustatymus bei migracijų ryšį ir perduoda terminalo argumentus Django komandų vykdyklei."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    # Migracijoms, jei pateiktas, naudojamas tiesioginis DB ryšys vietoje ryšių telkinio.
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
