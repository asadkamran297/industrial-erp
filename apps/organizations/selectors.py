from django.db.models import QuerySet

from .models import Branch, Organization


def get_organizations() -> QuerySet[Organization]:
    return Organization.objects.select_related("parent").order_by("title")


def get_branches() -> QuerySet[Branch]:
    return Branch.objects.select_related("organization", "city", "parent").order_by("organization__title", "title")
