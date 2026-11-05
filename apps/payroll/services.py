from calendar import monthrange
from datetime import date
from decimal import Decimal

from django.db import transaction

from apps.core.constants import (
    GL_SALARIES_EXPENSE_PATH,
    GL_SALARIES_PAYABLE_PATH,
    GL_SALARY_DEDUCTIONS_PATH,
    PAYROLL_GL_PREFIX,
    PAYROLL_GL_REVERSAL_PREFIX,
    STATUS_APPROVED,
    VOUCHER_TYPE_JOURNAL,
)
from apps.finance.models import AccountVoucher

TWO_DP = Decimal("0.01")


def payroll_date(payroll):
    return date(payroll.year, payroll.month, monthrange(payroll.year, payroll.month)[1])


def _amounts(payroll):
    net = (payroll.net_salary or Decimal("0")).quantize(TWO_DP)
    deductions = (payroll.total_deductions or Decimal("0")).quantize(TWO_DP)
    return net + deductions, deductions, net


def active_payroll_voucher(payroll):
    """``(voucher, number)`` of the payroll's voucher still standing in the books."""
    refs = set(
        AccountVoucher.objects.filter(source_ref__startswith=f"{PAYROLL_GL_REVERSAL_PREFIX}{payroll.pk}:")
        .values_list("source_ref", flat=True)
    )
    vouchers = AccountVoucher.objects.filter(source_ref__startswith=f"{PAYROLL_GL_PREFIX}{payroll.pk}:")
    latest, count = None, 0
    for voucher in vouchers:
        number = int(voucher.source_ref.rsplit(":", 1)[1])
        count = max(count, number)
        if f"{PAYROLL_GL_REVERSAL_PREFIX}{payroll.pk}:{number}" not in refs:
            latest = (voucher, number)
    return latest, count


@transaction.atomic
def sync_payroll_gl(payroll, *, user=None):
    """Keep an approved payroll in the books: Dr Salaries & Wages / Cr Salaries Payable and Deductions.

    Changing or un-approving it reverses the earlier voucher; nothing is edited in place.
    """
    from apps.finance.services import _post_voucher, gl_account, reverse_gl_posting

    zero = Decimal("0.00")
    wanted = payroll.status == STATUS_APPROVED and payroll.deleted_at is None
    gross, deductions, net = _amounts(payroll)
    current, count = active_payroll_voucher(payroll)
    expense = gl_account(GL_SALARIES_EXPENSE_PATH, user=user)
    when = payroll_date(payroll)

    if current is not None:
        voucher, number = current
        if wanted and voucher.debit_amount == gross and voucher.voucher_date == when:
            return voucher
        reverse_gl_posting(
            source_ref=voucher.source_ref,
            reversal_ref=f"{PAYROLL_GL_REVERSAL_PREFIX}{payroll.pk}:{number}",
            voucher_date=when,
            remarks=f"Payroll {payroll} changed",
            user=user,
        )
    if not wanted or not gross:
        return None

    label = f"Salary {payroll.employee} {payroll.month:02d}/{payroll.year}"
    return _post_voucher(
        source_ref=f"{PAYROLL_GL_PREFIX}{payroll.pk}:{count + 1}",
        voucher_type=VOUCHER_TYPE_JOURNAL,
        voucher_date=when,
        account_no=expense.code,
        remarks=label,
        entries=[
            (expense.code, gross, zero, label),
            (gl_account(GL_SALARY_DEDUCTIONS_PATH, user=user).code, zero, deductions, f"Deductions, {label}"),
            (gl_account(GL_SALARIES_PAYABLE_PATH, user=user).code, zero, net, f"Payable, {label}"),
        ],
        user=user,
    )
