from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from plat.gmail_service import authorize_gmail


class Command(BaseCommand):
    help = "Gmail API uchun bir martalik OAuth 2.0 avtorizatsiyasini bajaradi."
    # OAuth setup does not need Django URL/system checks. This lets the command
    # run even before the rest of the project is fully configured.
    requires_system_checks = []

    def handle(self, *args, **options):
        self.stdout.write("Gmail OAuth avtorizatsiyasi boshlanmoqda...")
        self.stdout.write(f"Credentials: {settings.GMAIL_CREDENTIALS_FILE}")
        self.stdout.write("Brauzer oynasida Gmail akkauntingizni tanlab, ruxsat bering.")
        try:
            authorize_gmail()
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS("Gmail OAuth muvaffaqiyatli ulandi. token.json yaratildi."))
