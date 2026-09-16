"""roles table + users.role_id (permission-based access control)

Revision ID: d4e5f6a7b8c9
Revises: a8d2c4e6f7b1
Create Date: 2026-09-14

- creates `roles` (id, name, is_system, permissions JSON text, deleted_at,
  created_at) with a partial unique index on live names
- seeds the three system roles (admin / doctor / receptionist) with the
  permission sets that reproduce the legacy hierarchy exactly
- adds `users.role_id`, backfills it from the legacy `users.role` string,
  then drops the legacy column

Safe to auto-apply on a live database: additive except for the legacy
`role` column, which is dropped only after every user row has been
reassigned to its system role.
"""

from typing import Sequence, Union

import json

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "a8d2c4e6f7b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Mirrors app.core.permissions.SYSTEM_ROLES (kept inline so the migration
# never imports app code that may drift).
SYSTEM_ROLES: dict[str, list[str]] = {
    "admin": [
        "appointments.create", "appointments.delete", "appointments.read",
        "appointments.update", "audit.view", "backup.manage", "files.delete",
        "files.read", "files.write", "medical_notes.view", "patients.create",
        "patients.delete", "patients.read", "patients.update", "payments.view",
        "questionnaires.fill", "questionnaires.read", "questionnaires.templates",
        "roles.manage", "stats.view", "taxonomies.write", "transactions.delete",
        "transactions.read", "transactions.write", "trash.purge", "trash.restore",
        "trash.view", "users.manage",
    ],
    "doctor": [
        "appointments.create", "appointments.delete", "appointments.read",
        "appointments.update", "files.delete", "files.read", "files.write",
        "medical_notes.view", "patients.create", "patients.read",
        "patients.update", "payments.view", "questionnaires.fill",
        "questionnaires.read", "stats.view", "taxonomies.write",
        "transactions.delete", "transactions.read", "transactions.write",
        "trash.restore", "trash.view",
    ],
    "receptionist": [
        "appointments.create", "appointments.read", "files.read",
        "patients.create", "patients.read", "patients.update", "payments.view",
        "questionnaires.fill", "questionnaires.read", "transactions.delete",
        "transactions.read", "transactions.write",
    ],
}


def upgrade() -> None:
    roles = sa.table(
        "roles",
        sa.column("name", sa.String),
        sa.column("is_system", sa.Boolean),
        sa.column("permissions_json", sa.Text),
    )
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("permissions_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_roles_name_live",
        "roles",
        ["name"],
        unique=True,
        sqlite_where=sa.text("deleted_at IS NULL"),
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.bulk_insert(
        roles,
        [
            {
                "name": name,
                "is_system": True,
                "permissions_json": json.dumps(perms, ensure_ascii=False),
            }
            for name, perms in SYSTEM_ROLES.items()
        ],
    )

    op.add_column("users", sa.Column("role_id", sa.Integer(), nullable=True))
    op.execute(
        "UPDATE users SET role_id = (SELECT id FROM roles WHERE roles.name = users.role)"
    )
    # rows that referenced an unknown role string cannot be auto-mapped
    op.execute(
        "UPDATE users SET role_id = (SELECT id FROM roles WHERE roles.name = 'receptionist')"
        " WHERE role_id IS NULL"
    )
    op.alter_column("users", "role_id", nullable=False, existing_type=sa.Integer())
    with op.batch_alter_table("users") as batch:
        batch.drop_column("role")
    op.create_foreign_key(None, "users", "roles", ["role_id"], ["id"])


def downgrade() -> None:
    raise NotImplementedError("roles migration is not reversible")
