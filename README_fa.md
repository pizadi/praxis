# پراکسیس — Praxis | سامانه مدیریت مطب

سامانه مدیریت مطب: FastAPI + React + PostgreSQL (بازنویسی اپلیکیشن قدیمی
Django/SQLite). رابط کاربری فارسی (راست‌چین) با تقویم جلالی و کنترل دسترسی
مبتنی بر permission.

* [English documentation](README.md)

## فناوری‌ها

| لایه | فناوری |
| --- | --- |
| API | FastAPI، SQLAlchemy 2 (async)، Alembic، Pydantic v2، JWT + argon2 |
| پایگاه داده | PostgreSQL 16 (SQLite برای تست/توسعه) |
| فرانت‌اند | Vite + React + TS، antd (راست‌چین)، TanStack Query، jalaliday |
| استقرار | docker-compose (web/api/db)، پراکسی معکوس nginx |

## راه‌اندازی سریع (توسعه)

```bash
# ۱. بک‌اند
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt -r backend/requirements-dev.txt
cd backend
DATABASE_URL=sqlite+aiosqlite:///data/clinic-dev.db ../.venv/bin/python -m alembic -c alembic.ini upgrade head
DATABASE_URL=sqlite+aiosqlite:///data/clinic-dev.db ../.venv/bin/uvicorn app.main:app --reload

# ۲. فرانت‌اند (ترمینال جدا؛ /api به پورت ۸۰۰۰ پروکسی می‌شود)
cd frontend
npm install
npm run dev     # http://localhost:5173

# ۳. ورود با مدیر اولیه (مقادیر .env / .env.example)
```

## راه‌اندازی سریع (docker)

```bash
cp .env.example .env      # رمزها را ویرایش کنید!
docker compose up -d --build
```

جزئیات بهره‌برداری: [docs_fa/deployment.md](docs_fa/deployment.md)

## ویژگی‌ها

| بخش | مستندات |
| --- | --- |
| بیماران، نوبت‌ها، یادداشت‌های پزشکی (CM/HX/PX/RX) | [docs_fa/patients-appointments.md](docs_fa/patients-appointments.md) |
| فایل‌های پیوست: پیش‌نمایش، بزرگ‌نمایی، پیوست/جایگزینی | [docs_fa/files.md](docs_fa/files.md) |
| پرداخت‌ها (کارت‌خوان/نقدی) + نمای روزانه | [docs_fa/payments.md](docs_fa/payments.md) |
| آمار و گزارش‌ها | [docs_fa/reports.md](docs_fa/reports.md) |
| پرسش‌نامه‌ها: سازهٔ گرافیکی، فرمول نمره، گزارش پاسخ‌ها + خروجی CSV | [docs_fa/questionnaires.md](docs_fa/questionnaires.md) |
| کنترل دسترسی مبتنی بر permission (نقش‌های سفارشی) | [docs_fa/permissions.md](docs_fa/permissions.md) |
| حذف نرم + سبد بازیافت (بازیابی/پاک‌سازی) | [docs_fa/trash-soft-delete.md](docs_fa/trash-soft-delete.md) |
| لاگ اقدامات | [docs_fa/audit.md](docs_fa/audit.md) |
| پشتیبان tarball: خروجی، واردسازی نسخه‌دار با بازگشت، پاک‌سازی خودکار فایل‌های بی‌صاحب | [docs_fa/backup-import.md](docs_fa/backup-import.md) |
| معماری و نسخه‌گذاری | [docs_fa/architecture.md](docs_fa/architecture.md) |
| توسعه (تست/لینت/تایپ‌چک) | [docs_fa/development.md](docs_fa/development.md) |
| مهاجرت از سامانهٔ قدیمی (SQLite → PostgreSQL) | [docs_fa/migration.md](docs_fa/migration.md) |

## تست‌ها

```bash
cd backend
DATABASE_URL="sqlite+aiosqlite:///data/clinic-dev.db" ../.venv/bin/python -m pytest tests -q
../.venv/bin/ruff check app tests ../scripts
../.venv/bin/mypy app

cd ../frontend
npm run lint
npm run build
```
