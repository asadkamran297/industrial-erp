from django.contrib import admin

from .models import Godown


@admin.register(Godown)
class GodownAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "godown_type", "status")
    list_filter = ("godown_type", "status")
    search_fields = ("code", "name", "location", "incharge")
