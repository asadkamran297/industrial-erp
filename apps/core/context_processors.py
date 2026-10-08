from django.utils.functional import SimpleLazyObject

from . import features
from .models import SystemSetting


def system_settings(request):
    return {
        "system_setting": SystemSetting.get_solo(),
        "features": SimpleLazyObject(features.current),
    }
