from .navigation import get_portal_navigation


def portal_navigation(request):
    if not request.user.is_authenticated:
        return {"portal_navigation": [], "portal_favourites": []}
    navigation = get_portal_navigation(request)
    return {"portal_navigation": navigation, "portal_favourites": getattr(request, "portal_favourites", [])}
