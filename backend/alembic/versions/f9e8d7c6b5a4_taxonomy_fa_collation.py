"""taxonomy Persian collation (DB-level alphabetical sort)

Revision ID: f9e8d7c6b5a4
Revises: e5f6a7b8c9d0
Create Date: 2026-09-20

Sets the `name` column collation of `tags`/`diagnoses` (and
`prescription_items` when that table already exists — see below) to an
ICU `fa` collation so `ORDER BY name` returns Persian alphabetical order
directly
from the index — no per-request sort compute, correct order for
ا ب پ ت ث ج چ … (byte order gets پ/چ/گ/ژ wrong).

- PostgreSQL only: SQLite has no ICU collation; the test/dev schema keeps
  BINARY ordering (tests assert order with ASCII names).
- The collation is DETERMINISTIC (PG default), so the partial unique live
  indexes keep byte-exact uniqueness ('VIP' vs 'vip' stay distinct).
- ALTER COLUMN TYPE rewrites the (tiny) tables and rebuilds their indexes
  in one statement — safe to auto-apply at boot.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f9e8d7c6b5a4"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgres():
        return
    op.execute("CREATE COLLATION IF NOT EXISTS fa_sort (provider = icu, locale = 'fa')")
    op.execute("ALTER TABLE tags ALTER COLUMN name TYPE VARCHAR(128) COLLATE fa_sort")
    op.execute(
        "ALTER TABLE diagnoses ALTER COLUMN name TYPE VARCHAR(128) COLLATE fa_sort"
    )
    # prescription_items may already exist on databases where the 1.3
    # migration (b1c2d3e4f5a6) ran BEFORE this one (pre-merge lineage) —
    # give its name column the same collation. On fresh installs the table
    # does not exist yet (b1c2d3e4f5a6 creates the column with the
    # collation directly), so skip.
    has_items = op.get_bind().execute(
        sa.text("SELECT to_regclass('prescription_items') IS NOT NULL")
    ).scalar()
    if has_items:
        op.execute(
            "ALTER TABLE prescription_items ALTER COLUMN name TYPE VARCHAR(128)"
            " COLLATE fa_sort"
        )


def downgrade() -> None:
    if not _is_postgres():
        return
    # revert to the database default collation
    op.execute("ALTER TABLE tags ALTER COLUMN name TYPE VARCHAR(128)")
    op.execute("ALTER TABLE diagnoses ALTER COLUMN name TYPE VARCHAR(128)")
