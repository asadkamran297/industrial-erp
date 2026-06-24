from django.core.management.base import BaseCommand, CommandError

from apps.access_control.seeders.permissions import seed_permissions
from apps.access_control.seeders.roles import seed_roles
from apps.configurations.seeders.configurations import seed_configurations
from apps.core.seeders import seed_system_settings
from apps.inventory.seeders.uoms import seed_uoms
from apps.organizations.seeders.organizations import seed_organizations


SEEDERS = {
    "core": [("system settings", seed_system_settings)],
    "configurations": [("configuration masters", seed_configurations)],
    "access_control": [
        ("permissions", seed_permissions),
        ("roles", seed_roles),
    ],
    "organizations": [("organizations", seed_organizations)],
    "inventory": [("units of measure", seed_uoms)],
}

DEFAULT_ORDER = ["core", "configurations", "access_control", "organizations", "inventory"]


class Command(BaseCommand):
    help = "Seed initial ERP master data."

    def add_arguments(self, parser):
        parser.add_argument(
            "modules",
            nargs="*",
            help="Optional module names: core, configurations, access_control, organizations, all.",
        )

    def handle(self, *args, **options):
        requested_modules = options["modules"] or ["all"]
        module_names = DEFAULT_ORDER if "all" in requested_modules else requested_modules

        unknown_modules = [module for module in module_names if module not in SEEDERS]
        if unknown_modules:
            available = ", ".join([*DEFAULT_ORDER, "all"])
            raise CommandError(f"Unknown seed module(s): {', '.join(unknown_modules)}. Available: {available}")

        total_created = 0
        for module_name in module_names:
            self.stdout.write(self.style.MIGRATE_HEADING(f"Seeding {module_name}"))
            for label, seeder in SEEDERS[module_name]:
                created_count = seeder()
                total_created += created_count
                self.stdout.write(self.style.SUCCESS(f"  {label}: {created_count} created"))

        self.stdout.write(self.style.SUCCESS(f"Seed complete. {total_created} new records created."))
