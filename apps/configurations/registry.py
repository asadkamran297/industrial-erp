from dataclasses import dataclass

from . import models


@dataclass(frozen=True)
class MasterConfig:
    slug: str
    label: str
    model: type
    extra_fields: tuple[str, ...] = ()


MASTER_CONFIGS: tuple[MasterConfig, ...] = (
    MasterConfig("departments", "Departments", models.Department),
    MasterConfig("designations", "Designations", models.Designation),
    MasterConfig("cities", "Cities", models.City),
    MasterConfig("genders", "Genders", models.Gender),
    MasterConfig("qualifications", "Qualifications", models.Qualification),
    MasterConfig("specializations", "Specializations", models.Specialization),
    MasterConfig("salutations", "Salutations", models.Salutation),
    MasterConfig("blood-groups", "Blood Groups", models.BloodGroup),
    MasterConfig("religions", "Religions", models.Religion),
    MasterConfig("marital-statuses", "Marital Statuses", models.MaritalStatus),
    MasterConfig("job-types", "Job Types", models.JobType),
    MasterConfig("expense-types", "Expense Types", models.ExpenseType),
    MasterConfig("payment-methods", "Payment Methods", models.PaymentMethod),
    MasterConfig("banks", "Banks", models.Bank),
    MasterConfig("manufacturers", "Manufacturers", models.Manufacturer, ("local_global",)),
    MasterConfig("image-types", "Image Types", models.ImageType),
    MasterConfig("allowance-deductions", "Allowance & Deduction Types", models.AllowanceDeduction, ("type",)),
)

MASTER_CONFIG_MAP = {config.slug: config for config in MASTER_CONFIGS}
