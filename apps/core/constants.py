from typing import Final

StatusChoices = tuple[tuple[str, str], ...]

STATUS_DRAFT: Final = "draft"
STATUS_PENDING: Final = "pending"
STATUS_APPROVED: Final = "approved"
STATUS_REJECTED: Final = "rejected"
STATUS_ACTIVE: Final = "active"
STATUS_INACTIVE: Final = "inactive"
STATUS_ARCHIVED: Final = "archived"

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

COMMON_STATUS_LABELS: Final[dict[str, str]] = {
    value: label for value, label in WORKFLOW_STATUS_CHOICES + RECORD_STATUS_CHOICES
}
