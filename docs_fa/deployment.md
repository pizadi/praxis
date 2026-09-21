# استقرار و بهره‌برداری

## docker compose

```bash
cp .env.example .env    # رمزها را ویرایش کنید!
docker compose up -d --build
```

- سه سرویس: `web` (nginx + UI ساخته‌شده + پراکسی معکوس)، `api` (FastAPI)،
  `db` (PostgreSQL 16). کانتینر api هنگام بوت `alembic upgrade head` را اجرا
  می‌کند — مهاجرت‌ها باید برای اعمال خودکار امن باشند.
- **برای اعمال تغییرات**: `docker compose up -d --build api web` — تغییرات
  کد تا بازسازی ایمیج زنده نمی‌شوند (ویژگی «غایب» در UI زنده معمولاً
  کانتینر کهنه است، نه باگ کد).
- Postgres پشت compose به پورت ۵۴۳۴ میزبان مپ است (درون شبکه `db:5432`)؛
  یک کانتینر تستِ جاافتاده روی 5432 می‌تواند خودش را دیتابیس اصلی جا بزند —
  اول `docker ps` را ببینید.
- api پورت 8000 و web پورت ۸۰ میزبان را می‌گیرند.

## رمزها

- `.env` (gitignored) شامل `BOOTSTRAP_ADMIN_*`، `SECRET_KEY` و اطلاعات
  دیتابیس است. pydantic فایل `env_file=".env"` را **نسبت به CWD** می‌خواند —
  اجرای بک‌اند از ریشهٔ مخزن یا از `backend/` تفاوت دارد؛ در تست‌ها متغیرهای
  محیطی conftest این را می‌پوشاند.
- راه‌اندازی تولیدی با `SECRET_KEY`/گذرواژهٔ مدیرِ پیش‌فرض می‌ایستد
  (`CLINIC_ENV=production`).

## کرون خارجی (روی دستگاه)

```bash
# pg_dump شبانه با نگه‌داری ۱۴ روزه + فایل‌های بارگذاری‌شده
0 2 * * *  docker exec new-patients-db-1 pg_dump -U clinic clinic | gzip > /ssd/backups/db-$(date +\%F).sql.gz && find /ssd/backups -name 'db-*.sql.gz' -mtime +14 -delete
30 2 * * * rsync -a /ssd/clinic-data/uploads/ /ssd/backups/uploads/
```

ماهانه تمرین بازیابی انجام دهید. مسیر UI برای همین کار، واردسازی/خروجی
tarball درون‌برنامه‌ای است (backup-import.md).

## نکته‌های محیط توسعه (این مخزن)

- ممکن است شبکهٔ bridge داکر در سندباکس توسعه شکسته باشد
  (`operation not supported` روی veth): برای کانتینرهای تست از
  `--network host` و برای build از
  `DOCKER_BUILDKIT=0 docker build --network=host` استفاده کنید. compose خودِ
  کاربر جای دیگر درست کار می‌کند — به‌خاطر شکست یک تست محلی، شبکهٔ compose
  را «درست» نکنید.
- رجیستری‌ها ناپایدارند؛ میرورهای PyPI/npm پیکربندی شده‌اند
  (`frontend/.npmrc`). اگر npm خطای 504 داد، با
  `--registry=https://mirror-npm.runflare.com` دوباره تلاش کنید.
- `data/` ممکن است متعلق به root باشد (مونت حجم) — برای فایل‌های موقت از
  `work/` استفاده کنید.
- برای دیباگ UI: کرومیوم سیستمی + playwright-core از
  `frontend/node_modules` (`NODE_PATH=frontend/node_modules node script.cjs`
  با `--no-sandbox`). سرورهای توسعهٔ بلندمدت را با
  `setsid nohup … < /dev/null & disown` جدا کنید.
