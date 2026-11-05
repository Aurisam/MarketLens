"""Komanda atskiram akcijų fundamentinių rodiklių atnaujinimui."""

from django.core.management.base import BaseCommand

from dashboard.fundamentals import refresh_stock_fundamentals


class Command(BaseCommand):
    """Leidžia paleisti kasdienį tikrinimą arba priverstinai atnaujinti su --force."""
    help = "Update saved stock fundamentals from Yahoo Finance."

    def add_arguments(self, parser):
        """Registruoja parinktį, leidžiančią nelaukti paros nuo ankstesnės sėkmės."""
        parser.add_argument("--force", action="store_true")

    def handle(self, *args, **options):
        """Atnaujina rodiklius ir išveda sėkmingų bei nesėkmingų gavimų skaičius."""
        result = refresh_stock_fundamentals(force=options["force"])
        self.stdout.write(f"Fundamentals: {result['updated']} updated, {result['failed']} unavailable.")
