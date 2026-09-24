# معماری

پراکسیس (Praxis) سامانه مدیریت مطب است: FastAPI + React + PostgreSQL،
بازنویسیِ اپلیکیشن قدیمی Django/SQLite.

## فناوری‌ها

| لایه | فناوری |
| --- | --- |
| API | FastAPI، SQLAlchemy 2 (async)، Alembic، Pydantic v2، JWT + argon2 |
| پایگاه داده | PostgreSQL 16 (SQLite برای تست و توسعه) |
| فرانت‌اند | Vite + React + TS، antd (راست‌چین)، TanStack Query، jalaliday |
| استقرار | docker-compose (web/api/db)، پراکسی معکوس nginx |

**کف پشتیبانی مرورگر: Chrome/Edge ≥ 88** (۲۰۲۱). antd نسخه ۵ استایل
کامپوننت‌ها را در زمان اجرا به‌صورت قواعد `:where(...)`-دار تولید می‌کند؛
موتورهای قدیمی‌تر همهٔ این قواعد را می‌اندازند و صفحه بی‌صدا خراب می‌شود.
اپلیکیشن در بوت این مورد را تشخیص می‌دهد (`src/lib/browserSupport.ts`) و یک
بنر ارتقای مرورگر (DOM ساده) نشان می‌دهد — پلی‌فایلی در کار نیست. هنگام
استفاده از قابلیت‌های جدید CSS/JS به این کف توجه کنید.

## ساختار

```
backend/app
  api/v1/        روترها: auth، users، roles، patients، appointments،
                 attachments، transactions، payments، taxonomies،
                 prescriptions، questionnaires، stats، trash، audit،
                 backup، meta
  api/deps.py    وابستگی‌های احراز هویت، نگهبان دسترسی، امنیت فایل
  core/          پیکربندی، امنیت (JWT/argon2)، خطاها، توکن‌ها،
                 کاتالوگ دسترسی‌ها + نقش‌های سیستمی
  db/session.py  موتور، SessionLocal، APP_TZ (Asia/Tehran)
  models/        domain.py (بیمار/نوبت/... + پرسش‌نامه‌ها)،
                 system.py (کاربر/نقش/احراز هویت/لاگ)
  schemas/       مدل‌های Pydantic v2 ورودی/خروجی
  services/      لاگ اقدامات، اعتبارسنجی قالب پرسش‌نامه، فرمول نمره،
                 واردسازی پشتیبان، پاک‌سازی فایل‌های بی‌صاحب
  alembic/       مهاجرت‌ها (هنگام بوت کانتینر اعمال می‌شوند؛ برای اجرای
                 مجدد روی DB زنده امن — جز حذف‌های مستندِ ستون‌های قدیمی، افزودنی)
frontend/src
  pages/         یک صفحه به ازای هر مسیر (رابط کاربری فارسی/راست‌چین)
  components/    پنل‌های مشترک (AppointmentPanel، FileDetailPane، ...)
  api/           کلاینت axios (تمدید توکن)، تایپ‌های هم‌تراز بک‌اند
  lib/           توابع کمکی: تاریخ جلالی، منطق پرسش‌نامه، دانلود
scripts/         ابزار مهاجرت و راستی‌آزمایی از SQLite قدیمی
deploy/          پیکربندی nginx تولید
docs/، docs_fa/  مستندات ویژگی‌ها (انگلیسی / فارسی)
```

## اصول ثابت

- **دسترسی، نه سلسله‌مراتب نقش**: هر اندپوینت `require_perm(...)` را از
  `app/api/deps.py` چک می‌کند. نقش‌ها داده‌اند (مجموعهٔ دسترسی JSON روی
  جدول `roles`)؛ نقش مدیر قفل است تا سامانه از دسترس خارج نشود.
- **حذف نرم همه‌جا**: حذف یعنی ثبت `deleted_at`؛ یکتایی با ایندکس یکتای
  جزئی روی ردیف‌های زنده تضمین می‌شود. جزئیات: trash-soft-delete.md.
- **لاگ اقدامات**: هر اندپوینت تغییردهنده پیش از بازگشت `log_action` را
  صدا می‌زند. جزئیات: audit.md.
- **بدون اسنپ‌شات برای پرسش‌نامه‌ها**: پاسخ‌ها با قالب *فعلی* ادغام و
  نمایش داده می‌شوند. جزئیات: questionnaires.md.
- **زمان**: داده داخلی و قرارداد API میلادی/UTC است؛ فقط نمایش و ورودی
  جلالی. مرز روز با `APP_TZ` (Asia/Tehran) محاسبه می‌شود.
- **خطاها**: پاکت یکسان `{"error": {"code", "message", "details"}}` در
  `app/core/errors.py` — 409 `ConflictError`، 422 `BusinessRuleError`،
  404 `NotFoundError`.

## نسخه‌گذاری

- `backend/app/__init__.py::__version__` — مرجع یکتای نسخهٔ API؛ در
  `GET /api/v1/health` و داخل مانیفست پشتیبان‌ها منعکس می‌شود.
- `version` در `frontend/package.json` — مرجع یکتای نسخهٔ UI؛ به‌صورت
  `__APP_VERSION__` از vite `define` تزریق و کنار عنوان هدر نمایش داده
  می‌شود.
- هر دو هم‌زمان بالا می‌روند: minor برای ویژگی، patch برای رفع اشکال.
  در طول توسعه از `X.Y.Z.devN` استفاده می‌شود.

## تست‌ها

- **بک‌اند** (pytest، پیش‌فرض SQLite و کل مجموعه روی PostgreSQL هم سبز
  است): `tests/unit/` (توابع خالص)، `tests/api/` (تست‌های یکپارچگی
  به‌ازای هر منبع روی کلاینت httpx ASGI، شامل ماتریس اندپوینت×نقش)،
  `tests/parity/` (ولیدیتور پرسش‌نامه). سازنده‌های مشترک در
  `tests/factories.py`.
- **فرانت‌اند**: vitest (`src/**/*.test.ts(x)`) برای واحدها/کامپوننت‌ها و
  Playwright E2E (`e2e/`) روی یک استک موقتی که کانفیگ بالا می‌آورد
  (uvicorn روی :18001 + `vite preview` روی :18010 با پروکسی `/api`).
- **کورپوس قرارداد**: `testdata/questionnaire_parity.json` — یک کورپوس
  مشترک برای ولیدیتورهای پرسش‌نامه که هم pytest (`tests/parity/`) و هم
  vitest (`src/parity/`) اجرا می‌کنند. مرجع نهایی سرور است؛ قرینهٔ TS باید
  با همهٔ موارد موافق باشد.
- دستورها و نکته‌ها: [development.md](development.md).
