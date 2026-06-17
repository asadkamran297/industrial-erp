from .navigation import get_portal_navigation


def portal_navigation(request):
    if not request.user.is_authenticated:
        return {"portal_navigation": []}
    return {"portal_navigation": get_portal_navigation(request)}
