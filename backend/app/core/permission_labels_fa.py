"""Persian labels for the permission catalog.

Presentation text lives outside the authorization module so security decisions
never depend on UI copy. A parity test keeps this map aligned with the keys in
``app.core.permissions``.
"""

PERMISSION_GROUP_LABELS_FA: dict[str, str] = {
    "patients": "بیماران",
    "appointments": "نوبت‌ها",
    "files": "فایل‌ها",
    "transactions": "پرداخت‌ها",
    "medical": "اطلاعات پزشکی",
    "prescriptions": "نسخ‌ها",
    "questionnaires": "پرسش‌نامه‌ها",
    "stats": "آمار و دسته‌بندی‌ها",
    "trash": "سبد بازیافت",
    "admin": "مدیریت سامانه",
}

PERMISSION_LABELS_FA: dict[str, str] = {
    "patients.read": "مشاهده بیماران",
    "patients.create": "ثبت بیمار",
    "patients.update": "ویرایش بیمار",
    "patients.delete": "حذف بیمار",
    "appointments.read": "مشاهده نوبت‌ها",
    "appointments.create": "ثبت نوبت",
    "appointments.update": "ویرایش نوبت",
    "appointments.stage": "تغییر مرحله نوبت",
    "appointments.delete": "حذف نوبت",
    "files.read": "مشاهده و دانلود فایل‌ها",
    "files.write": "افزودن و ویرایش فایل‌ها",
    "files.delete": "حذف فایل‌ها",
    "transactions.read": "مشاهده تراکنش‌ها",
    "transactions.write": "ثبت و ویرایش تراکنش",
    "transactions.delete": "حذف تراکنش",
    "payments.view": "گزارش پرداخت‌های روز",
    "medical_notes.view": "مشاهده یادداشت‌های پزشکی",
    "prescriptions.read": "مشاهده نسخ‌ها",
    "prescriptions.write": "ثبت و ویرایش نسخ‌ها",
    "questionnaires.read": "مشاهده پاسخ‌های پرسش‌نامه",
    "questionnaires.fill": "ثبت و ویرایش پاسخ‌ها",
    "questionnaires.templates": "مدیریت قالب‌های پرسش‌نامه",
    "stats.view": "مشاهده آمار",
    "taxonomies.write": "مدیریت برچسب‌ها و تشخیص‌ها",
    "trash.view": "مشاهده سبد بازیافت",
    "trash.restore": "بازیابی موارد",
    "trash.purge": "حذف قطعی",
    "users.manage": "مدیریت کاربران",
    "roles.manage": "مدیریت نقش‌ها و دسترسی‌ها",
    "audit.view": "مشاهده گزارش اقدامات",
    "backup.manage": "پشتیبان‌گیری",
}
