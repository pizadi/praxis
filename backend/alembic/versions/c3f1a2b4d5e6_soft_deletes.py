"""soft deletes: deleted_at columns + partial unique indexes

Revision ID: c3f1a2b4d5e6
Revises: b7eee1c1aa98
Create Date: 2026-09-11

- adds `deleted_at TIMESTAMPTZ NULL` to patients, appointments, transactions,
  attachments, tags, diagnoses, users
- converts the unique constraints that would block reuse of deleted values
  (patients.national_id, tags.name, diagnoses.name, users.username,
  attachments.stored_filename) into partial unique indexes
  (WHERE deleted_at IS NULL)
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3f1a2b4d5e6"
down_revision: Union[str, None] = "b7eee1c1aa98"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SOFT_TABLES = [
    "patients",
    "appointments",
    "transactions",
    "attachments",
    "tags",
    "diagnoses",
    "users",
]

# (table, column, old unique constraint/index name, new partial index name)
UNIQUE_SWAPS = [
    ("patients", "national_id", "patients_national_id_key", "uq_patients_national_id_live"),
    ("tags", "name", "tags_name_key", "uq_tags_name_live"),
    ("diagnoses", "name", "diagnoses_name_key", "uq_diagnoses_name_live"),
    ("users", "username", "uq_users_username", "uq_users_username_live"),
    ("attachments", "stored_filename", "attachments_stored_filename_key", "uq_attachments_stored_filename_live"),
]


def _constraint_exists(table: str, name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    for c in insp.get_unique_constraints(table):
        if c["name"] == name:
            return True
    for idx in insp.get_indexes(table):
        if idx["name"] == name and idx.get("unique"):
            return True
    return False


def upgrade() -> None:
    for table in SOFT_TABLES:
        op.add_column(
            table,
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        )

    where = sa.text("deleted_at IS NULL")
    for table, column, old_name, new_name in UNIQUE_SWAPS:
        if _constraint_exists(table, old_name):
            op.drop_constraint(old_name, table, type_="unique")
        op.create_index(
            new_name,
            table,
            [column],
            unique=True,
            postgresql_where=where,
            sqlite_where=where,
        )


def downgrade() -> None:
    where = sa.text("deleted_at IS NULL")
    for table, column, old_name, new_name in reversed(UNIQUE_SWAPS):
        op.drop_index(new_name, table_name=table)
        op.create_unique_constraint(old_name, table, [column])
    for table in reversed(SOFT_TABLES):
        op.drop_column(table, "deleted_at")
