# مهاجرت از سامانهٔ قدیمی (SQLite → PostgreSQL)

ابزارها: `scripts/migrate_sqlite.py`، `scripts/check_files.py`،
`scripts/verify_import.py`، `scripts/make_test_legacy_db.py`.

**اسکریپت را هرگز روی دیتابیس زنده نبرید.** اول اسنپ‌شات بگیرید:

```bash
# روی دستگاه سامانهٔ قدیمی، ساعات آرام:
systemctl stop old-patients   # یا هر طور که اجرا می‌شود
cp /path/to/db.sqlite3  snapshot/db.sqlite3
cp -r /path/to/patient_files  snapshot/patient_files
systemctl start old-patients  # سامانهٔ قدیمی همین‌طور به کار ادامه می‌دهد
```

سپس از این مخزن (پستگرسِ مپ‌شده به پورت ۵۴۳۴):

```bash
# اجرای خشک (بدون نوشتن) — شمارش‌ها، گزارش کیفیت داده، راستی‌آزمایی:
.venv/bin/python scripts/migrate_sqlite.py \
  --source snapshot/db.sqlite3 \
  --files  snapshot/patient_files \
  --database-url postgresql+asyncpg://clinic:PASS@localhost:5434/clinic \
  --upload-dir /var/lib/clinic/uploads

# اجرای واقعی (idempotent؛ تکرارش امن است):
... --apply
```

## رفتار

- **نگاشت ۱:۱** — کلیدهای اصلی و همهٔ مقادیر حفظ می‌شوند؛ جداول واسط بازسازی می‌شوند.
- تاریخ‌های naive محلیِ قدیمی (`Appointment_Date`) با فرض Asia/Tehran
  (+03:30) به‌صورت `timestamptz` ذخیره می‌شوند.
- فایل‌ها با نام UUID کپی می‌شوند؛ دیتابیس `original_filename` را نگه
  می‌دارد؛ فایل‌های غایب با `missing_file=true` وارد می‌شوند (گزارش می‌شوند،
  گم نمی‌شوند).
- **گزارش کیفیت داده** ردیف‌های قدیمیِ ناقض اعتبارسنجی جدید را پرچم می‌زند
  (کد ملی ۱۰ رقمی، سال ۴ رقمی، تلفن فقط-رقم). بازدارنده نیست — بعداً از UI
  اصلاح کنید. کد ملی‌های تکراری `--apply` را **متوقف** می‌کنند تا دستی حل شوند.
- شرح‌های انگلیسی قدیمی پرداخت (`Visit`/`Spiro`/`Other`) به
  ویزیت/اسپیرو/سایر ترجمه می‌شوند (بی‌حس به بزرگی/کوچکی حروف؛ نامترجمه‌ها
  دست‌نخورده).
- راستی‌آزمایی خودکار شمارش جدول‌به‌جدول، جمع‌های POS/نقد، تعداد نوبت
  هر بیمار و FKهای بی‌صاحب را مقایسه می‌کند. کد خروج 0 فقط با PASS.
- پس از قطع‌سوییچ: سامانهٔ قدیمی را دو هفته فقط-خواندنی نگه دارید.

بعد از `--apply`، راستی‌آزمایی مستقل را اجرا کنید (کد مشترکی با اسکریپت
مهاجرت ندارد — SQLite و PostgreSQL را مستقیم مقایسه می‌کند، از جمله
مقایسهٔ فیلدبه‌فیلد بیماران، جمع پول، تبدیل تایم‌زون، بقاِ متن یادداشت‌ها و
حجم فیزیکی فایل‌ها):

```bash
.venv/bin/python scripts/verify_import.py   # ALL CHECKS PASSED = قطع‌سوییچ امن
```

دیتابیس قدیمیِ ساختگی برای تست خودِ مهاجرت:
`python3 scripts/make_test_legacy_db.py /tmp/legacy.db`

`old_database/` در مخزن یک اسنپ‌شات واقعی تولید است — حساس تلقی شود؛
هیچ‌وقت چیزی داخلش commit نکنید.
