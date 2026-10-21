from django.utils.functional import SimpleLazyObject

from . import features
from .models import SystemSetting

DEFAULT_COMPANY_NAME = "Industrial ERP"
DEFAULT_TAGLINE = "Official MIS Portal"
PLACEHOLDER_MARKS = ("example.com", "000-0000000")


def _brand(setting):
    from apps.core.constants import STATUS_ACTIVE
    from apps.organizations.models import Organization

    org = Organization.objects.filter(status=STATUS_ACTIVE).order_by("id").first()
    name = setting.company_name
    if (not name or name == DEFAULT_COMPANY_NAME) and org is not None:
        name = org.title
    tagline = "" if setting.company_tagline == DEFAULT_TAGLINE else setting.company_tagline
    logo = setting.company_logo.url if setting.company_logo else (getattr(org, "logo", "") or "")
    contacts = [
        (label, value) for label, value in (
            ("Helpline", setting.mis_helpline_phone or setting.support_phone),
            ("Email", setting.mis_helpline_email or setting.support_email),
        )
        if value and not any(mark in value for mark in PLACEHOLDER_MARKS)
    ]
    return {"name": name or DEFAULT_COMPANY_NAME, "tagline": tagline, "logo": str(logo), "contacts": contacts}


def _org():
    from apps.core.constants import STATUS_ACTIVE
    from apps.organizations.models import Organization

    return Organization.objects.filter(status=STATUS_ACTIVE).order_by("id").first()


def _branch():
    from apps.core.constants import STATUS_ACTIVE
    from apps.organizations.models import Branch

    return Branch.objects.filter(status=STATUS_ACTIVE).select_related("city").order_by("id").first()


def system_settings(request):
    setting = SystemSetting.get_solo()
    return {
        "org": SimpleLazyObject(_org),
        "branch": SimpleLazyObject(_branch),
        "system_setting": setting,
        "brand": SimpleLazyObject(lambda: _brand(setting)),
        "features": SimpleLazyObject(features.current),
    }
