"""Canonical permission catalog.

Permissions are grouped for the roles UI; the API validates requested
permission keys against ALL_PERMISSIONS. System roles map 1:1 onto the
pre-permission behavior (admin > doctor > receptionist).
"""

# group label (Persian) -> [(permission key, Persian label)]
PERMISSION_CATALOG: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "بیماران",
        [
            ("patients.read", "مشاهده بیماران"),
            ("patients.create", "ثبت بیمار"),
            ("patients.update", "ویرایش بیمار"),
            ("patients.delete", "حذف بیمار"),
        ],
    ),
    (
        "نوبت‌ها",
        [
            ("appointments.read", "مشاهده نوبت‌ها"),
            ("appointments.create", "ثبت نوبت"),
            ("appointments.update", "ویرایش نوبت"),
            ("appointments.stage", "تغییر مرحله نوبت"),
            ("appointments.delete", "حذف نوبت"),
        ],
    ),
    (
        "فایل‌ها",
        [
            ("files.read", "مشاهده و دانلود فایل‌ها"),
            ("files.write", "افزودن و ویرایش فایل‌ها"),
            ("files.delete", "حذف فایل‌ها"),
        ],
    ),
    (
        "پرداخت‌ها",
        [
            ("transactions.read", "مشاهده تراکنش‌ها"),
            ("transactions.write", "ثبت و ویرایش تراکنش"),
            ("transactions.delete", "حذف تراکنش"),
            ("payments.view", "گزارش پرداخت‌های روز"),
        ],
    ),
    (
        "اطلاعات پزشکی",
        [
            ("medical_notes.view", "مشاهده یادداشت‌های پزشکی"),
        ],
    ),
    (
        "نسخ‌ها",
        [
            ("prescriptions.read", "مشاهده نسخ‌ها"),
            ("prescriptions.write", "ثبت و ویرایش نسخ‌ها"),
        ],
    ),
    (
        "پرسش‌نامه‌ها",
        [
            ("questionnaires.read", "مشاهده پاسخ‌های پرسش‌نامه"),
            ("questionnaires.fill", "ثبت و ویرایش پاسخ‌ها"),
            ("questionnaires.templates", "مدیریت قالب‌های پرسش‌نامه"),
        ],
    ),
    (
        "آمار و دسته‌بندی‌ها",
        [
            ("stats.view", "مشاهده آمار"),
            ("taxonomies.write", "مدیریت برچسب‌ها و تشخیص‌ها"),
        ],
    ),
    (
        "سبد بازیافت",
        [
            ("trash.view", "مشاهده سبد بازیافت"),
            ("trash.restore", "بازیابی موارد"),
            ("trash.purge", "حذف قطعی"),
        ],
    ),
    (
        "مدیریت سامانه",
        [
            ("users.manage", "مدیریت کاربران"),
            ("roles.manage", "مدیریت نقش‌ها و دسترسی‌ها"),
            ("audit.view", "مشاهده گزارش اقدامات"),
            ("backup.manage", "پشتیبان‌گیری"),
        ],
    ),
]

ALL_PERMISSIONS: frozenset[str] = frozenset(
    perm for _, perms in PERMISSION_CATALOG for perm, _ in perms
)

PERMISSION_LABELS: dict[str, str] = {
    perm: label for _, perms in PERMISSION_CATALOG for perm, label in perms
}

# System roles: permission sets reproduce the legacy hierarchy exactly
# (admin > doctor > receptionist) so existing users keep their access.
_ADMIN_PERMS = sorted(ALL_PERMISSIONS)

_DOCTOR_PERMS = [
    "patients.read",
    "patients.create",
    "patients.update",
    "appointments.read",
    "appointments.create",
    "appointments.update",
    "appointments.stage",
    "appointments.delete",
    "files.read",
    "files.write",
    "files.delete",
    "transactions.read",
    "transactions.write",
    "transactions.delete",
    "medical_notes.view",
    "questionnaires.read",
    "questionnaires.fill",
    "payments.view",
    "stats.view",
    "taxonomies.write",
    "trash.view",
    "trash.restore",
    "prescriptions.read",
    "prescriptions.write",
]
_RECEPTIONIST_PERMS = [
    "patients.read",
    "patients.create",
    "patients.update",
    "appointments.read",
    "appointments.create",
    "appointments.stage",
    "files.read",
    "transactions.read",
    "transactions.write",
    "transactions.delete",
    "questionnaires.read",
    "questionnaires.fill",
    "payments.view",
]

SYSTEM_ROLES: dict[str, list[str]] = {
    "admin": _ADMIN_PERMS,
    "doctor": _DOCTOR_PERMS,
    "receptionist": _RECEPTIONIST_PERMS,
}
