from typing import Final

StatusChoices = tuple[tuple[str, str], ...]

STATUS_DRAFT: Final = "draft"
STATUS_PENDING: Final = "pending"
STATUS_APPROVED: Final = "approved"
STATUS_REJECTED: Final = "rejected"
STATUS_ACTIVE: Final = "active"
STATUS_INACTIVE: Final = "inactive"
STATUS_ARCHIVED: Final = "archived"
STATUS_COMPLETED: Final = "completed"
STATUS_ONGOING: Final = "ongoing"

ALLOWANCE: Final = "allowance"
DEDUCTION: Final = "deduction"

QUALIFICATION_DEGREE: Final = "degree"
QUALIFICATION_DIPLOMA: Final = "diploma"
QUALIFICATION_CERTIFICATE: Final = "certificate"

SCOPE_LOCAL: Final = "local"
SCOPE_GLOBAL: Final = "global"

WORKFLOW_STATUS_CHOICES: Final[StatusChoices] = (
    (STATUS_DRAFT, "Draft"),
    (STATUS_PENDING, "Pending"),
    (STATUS_APPROVED, "Approved"),
    (STATUS_REJECTED, "Rejected"),
)

RECORD_STATUS_CHOICES: Final[StatusChoices] = (
    (STATUS_ACTIVE, "Active"),
    (STATUS_INACTIVE, "Inactive"),
    (STATUS_ARCHIVED, "Archived"),
)

COMPLETION_STATUS_CHOICES: Final[StatusChoices] = (
    (STATUS_COMPLETED, "Completed"),
    (STATUS_ONGOING, "Ongoing"),
)

ALLOWANCE_DEDUCTION_TYPE_CHOICES: Final[StatusChoices] = (
    (ALLOWANCE, "Allowance"),
    (DEDUCTION, "Deduction"),
)

QUALIFICATION_TYPE_CHOICES: Final[StatusChoices] = (
    (QUALIFICATION_DEGREE, "Degree"),
    (QUALIFICATION_DIPLOMA, "Diploma"),
    (QUALIFICATION_CERTIFICATE, "Certificate"),
)

SCOPE_CHOICES: Final[StatusChoices] = (
    (SCOPE_LOCAL, "Local"),
    (SCOPE_GLOBAL, "Global"),
)

COMMON_STATUS_LABELS: Final[dict[str, str]] = {
    value: label
    for value, label in WORKFLOW_STATUS_CHOICES + RECORD_STATUS_CHOICES + COMPLETION_STATUS_CHOICES
}
