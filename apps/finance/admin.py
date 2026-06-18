from django.contrib import admin

from .models import AccountConfiguration, AccountVoucher, AccountVoucherLine, FiscalPeriod, FiscalYear


for model in (FiscalYear, FiscalPeriod, AccountConfiguration, AccountVoucher, AccountVoucherLine):
    admin.site.register(model)
