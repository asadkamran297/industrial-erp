from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


class ActiveManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class BaseModel(models.Model):
    is_active = models.BooleanField(default=True)
    # Indexed on the abstract base so every table inherits them: created_at
    # drives the default "newest first" listing, and deleted_at is in the WHERE
    # clause of every query that goes through ActiveManager.
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="created_%(class)s_records",
        on_delete=models.SET_NULL,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="updated_%(class)s_records",
        on_delete=models.SET_NULL,
    )

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def soft_delete(self, user=None) -> None:
        self.is_active = False
        self.deleted_at = timezone.now()
        if user and getattr(user, "is_authenticated", False):
            self.updated_by = user
        self.save(update_fields=["is_active", "deleted_at", "updated_by", "updated_at"])


class SystemSetting(BaseModel):
    company_name = models.CharField(max_length=160, default="Industrial ERP")
    company_logo = models.ImageField(upload_to="branding/logos/", blank=True)
    company_tagline = models.CharField(max_length=220, blank=True, default="Official MIS Portal")
    md_name = models.CharField("Managing Director name", max_length=120, blank=True)
    md_picture = models.ImageField(upload_to="branding/md/", blank=True)
    md_message = models.TextField(blank=True, default="Please use this system responsibly for official work only.")
    mis_helpline_phone = models.CharField(max_length=40, blank=True)
    mis_helpline_email = models.EmailField(blank=True)
    support_phone = models.CharField(max_length=40, blank=True)
    support_email = models.EmailField(blank=True)
    primary_color = models.CharField(max_length=20, default="#2563eb")
    secondary_color = models.CharField(max_length=20, default="#0f172a")
    default_theme = models.CharField(
        max_length=10,
        choices=[("light", "Light"), ("dark", "Dark"), ("system", "System")],
        default="light",
    )
    login_background_image = models.ImageField(upload_to="branding/login/", blank=True)
    footer_text = models.CharField(max_length=220, blank=True, default="Authorized users only.")

    # -- Mill purchase defaults ---------------------------------------------
    # The two rates the gate quotes against weight rather than against money.
    # They change with the season and with the government's notification, so
    # they are settings the office edits, not constants a release has to carry.
    # The clerk still overrides either one on an individual purchase.
    wheat_withholding_rate_per_40kg = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    wheat_brokerage_rate_per_100kg = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        verbose_name = "System setting"
        verbose_name_plural = "System settings"

    def __str__(self) -> str:
        return self.company_name

    @classmethod
    def get_solo(cls):
        return cls.objects.order_by("pk").first() or cls(pk=1)
