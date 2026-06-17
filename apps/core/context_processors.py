from .models import SystemSetting


def system_settings(request):
    return {"system_setting": SystemSetting.get_solo()}
