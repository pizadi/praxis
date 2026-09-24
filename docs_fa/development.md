# توسعه

## دستورها

venv پایتون در **ریشهٔ مخزن** است (`.venv`)، نه داخل `backend/`.

```bash
# تست‌های بک‌اند (از backend/ — pyproject.toml آنجاست)
cd backend && DATABASE_URL="sqlite+aiosqlite:///data/clinic-dev.db" ../.venv/bin/python -m pytest tests -q
# یک تست خاص
../.venv/bin/python -m pytest tests/api/test_patients.py::test_patient_crud -q

# لینت + تایپ‌چک
.venv/bin/ruff check backend/app backend/tests scripts
(cd backend && ../.venv/bin/mypy app)

# فرانت‌اند (از frontend/)
npm run lint        # eslint، بدون هیچ هشدار
npm test            # vitest: واحد + parity
npm run test:e2e    # playwright: بک‌اند موقت + preview

# ولیدیتور پرسش‌نامه (اعتبارسنجی سرور + کورپوس ارزیابی مشترک)
../.venv/bin/python -m pytest backend/tests/parity -q
npx vitest run src/parity

# محافظ جفت‌مستندات
python scripts/check_doc_pairs.py --base-ref origin/dev

# استقرار روی compose
docker compose up -d --build api web
```

ترتیب راستی‌آزمایی: ruff → mypy → pytest → npm lint/test/build → e2e.

## نکته‌های تست

- `backend/tests/conftest.py` متغیرهای `DATABASE_URL`/`UPLOAD_DIR`/`SECRET_KEY`
  را هنگام import ماژول، **پیش از هر import از `app.*`** ست می‌کند —
  pydantic-settings در اولین import کش می‌کند.
- تست‌ها جدول‌ها را با `Base.metadata.create_all` می‌سازند، **نه** Alembic؛
  درستی مهاجرت‌ها جداگانه روی پستگرس واقعی بررسی می‌شود.
- فیکسچر `client` هر تست همهٔ جدول‌ها را drop/create و `bootstrap_admin()`
  را دستی صدا می‌زند.
- `pytest-asyncio` در حالت `asyncio_mode = "auto"`.
- `login()` زوج `(access_token, مقدار کوکی refresh)` برمی‌گرداند —
  `recep, _ = await login(...)`، **نه** `recep[0]`. کوکی مرورگر `HttpOnly`
  است؛ تست‌های API مقدار خام را از jar دریافت می‌کنند.
- مقادیر ذخیره‌شده را روی **پاسخِ create** ادعا کنید (نه فقط پس از PATCH).
- تست‌ها «امروز» را از `APP_TZ` بگیرند (payments.md را ببینید).
- ستون‌های `Enum` در SQLAlchemy **نامِ** عضو را ذخیره می‌کنند — مهاجرت/اسکریپت‌هایی
  که ستون‌های enum قدیمی را می‌خوانند باید بی‌حس به بزرگی/کوچکی حروف مقایسه
  کنند و روی مقدار غیرمنتظره با صدایی بلند بشکنند، نه سکوتاً مقدار پیش‌فرض
  بگذارند.

## قراردادها (خلاصه)

- UI فارسی/راست‌چین؛ فقط نمایش جلالی — API/حالت داخلی میلادی ISO/UTC.
- مودال‌ها `maskClosable={false}` دارند؛ `destroyOnHidden` را ترجیح دهید.
- antd Select ها `showSearch` + `optionFilterProp="label"` می‌خواهند.
- خطاها: پاکت یکسان با کد ماشین‌خوان؛ پیام‌های فارسی سمت کلاینت.
- ruff line-length 100؛ `B008` بی‌اثر؛ mypy باید تمیز بماند.
- نسخه‌گذاری: `backend/app/__init__.py::__version__` و
  `frontend/package.json` را هم‌زمان بالا ببرید.
