from collections.abc import Iterable

from apps.configurations import models
from apps.core.constants import ALLOWANCE, DEDUCTION, SCOPE_GLOBAL, SCOPE_LOCAL, STATUS_ACTIVE


LookupRows = Iterable[tuple[str, str]]


def seed_lookup(model, rows: LookupRows) -> int:
    created_count = 0
    for code, title in rows:
        _, created = model.objects.update_or_create(
            code=code,
            defaults={"title": title, "status": STATUS_ACTIVE},
        )
        created_count += int(created)
    return created_count


def seed_configurations() -> int:
    created_count = 0

    created_count += seed_lookup(
        models.Gender,
        [
            ("MALE", "Male"),
            ("FEMALE", "Female"),
            ("OTHER", "Other"),
        ],
    )
    created_count += seed_lookup(
        models.Salutation,
        [
            ("MR", "Mr."),
            ("MRS", "Mrs."),
            ("MS", "Ms."),
            ("DR", "Dr."),
            ("ENGR", "Engr."),
        ],
    )
    created_count += seed_lookup(
        models.BloodGroup,
        [
            ("A_POS", "A+"),
            ("A_NEG", "A-"),
            ("B_POS", "B+"),
            ("B_NEG", "B-"),
            ("AB_POS", "AB+"),
            ("AB_NEG", "AB-"),
            ("O_POS", "O+"),
            ("O_NEG", "O-"),
        ],
    )
    created_count += seed_lookup(
        models.Religion,
        [
            ("ISLAM", "Islam"),
            ("CHRISTIANITY", "Christianity"),
            ("HINDUISM", "Hinduism"),
            ("OTHER", "Other"),
        ],
    )
    created_count += seed_lookup(
        models.MaritalStatus,
        [
            ("SINGLE", "Single"),
            ("MARRIED", "Married"),
            ("DIVORCED", "Divorced"),
            ("WIDOWED", "Widowed"),
        ],
    )
    created_count += seed_lookup(
        models.JobType,
        [
            ("PERMANENT", "Permanent"),
            ("CONTRACT", "Contract"),
            ("DAILY_WAGES", "Daily Wages"),
            ("INTERNSHIP", "Internship"),
            ("PROBATION", "Probation"),
        ],
    )
    created_count += seed_lookup(
        models.Department,
        [
            ("ADMIN", "Administration"),
            ("HR", "Human Resources"),
            ("FIN", "Finance"),
            ("PROC", "Procurement"),
            ("STORE", "Stores"),
            ("INV", "Inventory"),
            ("PROD", "Production"),
            ("QA", "Quality Assurance"),
            ("QC", "Quality Control"),
            ("MAINT", "Maintenance"),
            ("SALES", "Sales"),
            ("IT", "Information Technology"),
            ("SEC", "Security"),
            ("HSE", "Health, Safety and Environment"),
        ],
    )
    created_count += seed_lookup(
        models.Designation,
        [
            ("MD", "Managing Director"),
            ("GM", "General Manager"),
            ("MANAGER", "Manager"),
            ("ASSISTANT_MANAGER", "Assistant Manager"),
            ("SUPERVISOR", "Supervisor"),
            ("OFFICER", "Officer"),
            ("ASSISTANT", "Assistant"),
            ("OPERATOR", "Operator"),
            ("TECHNICIAN", "Technician"),
            ("HELPER", "Helper"),
            ("ACCOUNTANT", "Accountant"),
            ("STORE_KEEPER", "Store Keeper"),
            ("SECURITY_GUARD", "Security Guard"),
        ],
    )
    created_count += seed_lookup(
        models.Qualification,
        [
            ("MATRIC", "Matric"),
            ("INTERMEDIATE", "Intermediate"),
            ("DAE", "Diploma of Associate Engineering"),
            ("BACHELOR", "Bachelor"),
            ("MASTER", "Master"),
            ("MBA", "MBA"),
            ("MS", "MS/MPhil"),
            ("PHD", "PhD"),
            ("CERT", "Professional Certificate"),
        ],
    )
    created_count += seed_lookup(
        models.Specialization,
        [
            ("MECHANICAL", "Mechanical"),
            ("ELECTRICAL", "Electrical"),
            ("CIVIL", "Civil"),
            ("CHEMICAL", "Chemical"),
            ("INDUSTRIAL", "Industrial"),
            ("FINANCE", "Finance"),
            ("HR", "Human Resources"),
            ("IT", "Information Technology"),
            ("SUPPLY_CHAIN", "Supply Chain"),
        ],
    )
    created_count += seed_lookup(
        models.City,
        [
            ("KHI", "Karachi"),
            ("LHE", "Lahore"),
            ("ISB", "Islamabad"),
            ("RWP", "Rawalpindi"),
            ("FSD", "Faisalabad"),
            ("MUX", "Multan"),
            ("PEW", "Peshawar"),
            ("QTA", "Quetta"),
            ("SKT", "Sialkot"),
            ("GJW", "Gujranwala"),
            ("HYD", "Hyderabad"),
            ("SGD", "Sargodha"),
        ],
    )
    created_count += seed_lookup(
        models.ExpenseType,
        [
            ("TRAVEL", "Travel"),
            ("FUEL", "Fuel"),
            ("MEAL", "Meal"),
            ("OFFICE_SUPPLIES", "Office Supplies"),
            ("REPAIR", "Repair and Maintenance"),
            ("UTILITY", "Utility"),
            ("MEDICAL", "Medical"),
            ("MISC", "Miscellaneous"),
        ],
    )
    created_count += seed_lookup(
        models.PaymentMethod,
        [
            ("CASH", "Cash"),
            ("BANK_TRANSFER", "Bank Transfer"),
            ("CHEQUE", "Cheque"),
            ("ONLINE", "Online"),
            ("MOBILE_WALLET", "Mobile Wallet"),
        ],
    )
    created_count += seed_lookup(
        models.Bank,
        [
            ("HBL", "Habib Bank Limited"),
            ("UBL", "United Bank Limited"),
            ("MCB", "MCB Bank"),
            ("ABL", "Allied Bank Limited"),
            ("ASKARI", "Askari Bank"),
            ("MEEZAN", "Meezan Bank"),
            ("BANK_ALFALAH", "Bank Alfalah"),
            ("FAYSAL", "Faysal Bank"),
        ],
    )
    created_count += seed_lookup(
        models.ImageType,
        [
            ("PROFILE", "Profile"),
            ("CNIC_FRONT", "CNIC Front"),
            ("CNIC_BACK", "CNIC Back"),
            ("DOCUMENT", "Document"),
            ("CERTIFICATE", "Certificate"),
            ("PRODUCT", "Product"),
            ("BRANDING", "Branding"),
        ],
    )

    for code, title, scope in [
        ("LOCAL_SUPPLIER", "Local Supplier", SCOPE_LOCAL),
        ("GLOBAL_SUPPLIER", "Global Supplier", SCOPE_GLOBAL),
        ("LOCAL_MANUFACTURER", "Local Manufacturer", SCOPE_LOCAL),
        ("GLOBAL_MANUFACTURER", "Global Manufacturer", SCOPE_GLOBAL),
    ]:
        _, created = models.Manufacturer.objects.update_or_create(
            code=code,
            defaults={"title": title, "local_global": scope, "status": STATUS_ACTIVE},
        )
        created_count += int(created)

    for code, title, item_type in [
        ("BASE_SALARY", "Base Salary", ALLOWANCE),
        ("HOUSE_RENT", "House Rent Allowance", ALLOWANCE),
        ("MEDICAL_ALLOWANCE", "Medical Allowance", ALLOWANCE),
        ("CONVEYANCE", "Conveyance Allowance", ALLOWANCE),
        ("OVERTIME", "Overtime", ALLOWANCE),
        ("BONUS", "Bonus", ALLOWANCE),
        ("INCREMENT", "Increment", ALLOWANCE),
        ("TAX", "Income Tax", DEDUCTION),
        ("EOBI", "EOBI", DEDUCTION),
        ("PROVIDENT_FUND", "Provident Fund", DEDUCTION),
        ("LOAN", "Loan Deduction", DEDUCTION),
        ("ABSENCE", "Absence Deduction", DEDUCTION),
        ("LATE", "Late Deduction", DEDUCTION),
    ]:
        _, created = models.AllowanceDeduction.objects.update_or_create(
            code=code,
            defaults={"title": title, "type": item_type, "status": STATUS_ACTIVE},
        )
        created_count += int(created)

    for key, value in [
        ("theme", {"default": "light", "primary_color": "#2563eb"}),
        ("attendance", {"grace_minutes": 10, "working_hours": 8}),
        ("payroll", {"currency": "PKR", "salary_month_day": 1}),
        ("security", {"password_expiry_days": 90, "session_timeout_minutes": 60}),
    ]:
        _, created = models.SystemConfiguration.objects.update_or_create(
            key=key,
            defaults={"value": value, "status": STATUS_ACTIVE},
        )
        created_count += int(created)

    return created_count
