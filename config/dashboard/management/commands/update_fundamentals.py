from django.core.management.base import BaseCommand

from dashboard.fundamentals import refresh_stock_fundamentals


class Command(BaseCommand):
    help = "Update saved stock fundamentals from Yahoo Finance."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true")

    def handle(self, *args, **options):
        result = refresh_stock_fundamentals(force=options["force"])
        self.stdout.write(f"Fundamentals: {result['updated']} updated, {result['failed']} unavailable.")
