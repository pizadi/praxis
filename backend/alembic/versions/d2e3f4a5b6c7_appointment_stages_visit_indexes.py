"""appointment stages + same-day visit indexes

Revision ID: d2e3f4a5b6c7
Revises: b1c2d3e4f5a6
Create Date: 2026-09-21

1.4 schema migration:

- `appointments.stage` (SMALLINT, values mirror app.models.domain
  .AppointmentStage: 0=reserved, 1=checked-in, 2=referred, 3=finished).
  Existing rows: appointments already in the past are finalized to 3
  (پایان یافته); future appointments keep the reserved default.
- Composite indexes for the same-day "associated items" lookups (files /
  prescriptions / questionnaire responses the patient has on an
  appointment's day): (patient_id, created_at) on attachments and
  questionnaire_responses, (patient_id, prescribed_at) on prescriptions.
  The plain patient_id indexes they supersede are dropped (leftmost
  prefix covers them). attachments had its single-column index created
  out-of-model by b1c2d3e4f5a6 — dropped here too.
- The admin/doctor/receptionist system roles gain appointments.stage
  (additive merge into permissions_json — removals never happen here;
  the admin role is UI-locked, so this migration is the only automatic
  path; bootstrap_admin only heals the admin role, other roles are pure
  data).

Safe to auto-apply on a live database: the whole upgrade runs in one
transaction (PostgreSQL DDL is transactional); any error rolls everything
back.
"""

import json
import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Mirrors app.core.permissions (kept inline so the migration never depends
# on app code that may drift — same pattern as d4e5f6a7b8c9/b1c2d3e4f5a6).
NEW_PERMS = ["appointments.stage"]
# which system roles receive the new permission (check-in is a front-desk
# task — receptionist included, unlike the medical-data perms)
ROLES_GETTING_PERMS = ("admin", "doctor", "receptionist")


def upgrade() -> None:
    # --- 1. appointments.stage -------------------------------------------------
    op.add_column(
        "appointments",
        sa.Column(
            "stage", sa.SmallInteger(), nullable=False, server_default=sa.text("0")
        ),
    )
    # backfill: visits already in the past are finished
    op.execute(
        "UPDATE appointments SET stage = 3 WHERE scheduled_at < CURRENT_TIMESTAMP"
    )
    # the model keeps no server default (ORM supplies 0 on insert)
    with op.batch_alter_table("appointments") as batch:
        batch.alter_column(
            "stage", existing_type=sa.SmallInteger(), server_default=None
        )

    # --- 2. same-day composite indexes (replace plain patient_id ones) ---------
    op.create_index(
        "ix_attachments_patient_created_at",
        "attachments",
        ["patient_id", "created_at"],
    )
    op.drop_index("ix_attachments_patient_id", table_name="attachments")
    op.create_index(
        "ix_questionnaire_responses_patient_created_at",
        "questionnaire_responses",
        ["patient_id", "created_at"],
    )
    op.drop_index(
        "ix_questionnaire_responses_patient_id", table_name="questionnaire_responses"
    )
    op.create_index(
        "ix_prescriptions_patient_prescribed_at",
        "prescriptions",
        ["patient_id", "prescribed_at"],
    )
    op.drop_index("ix_prescriptions_patient_id", table_name="prescriptions")

    # --- 3. grant appointments.stage to the system roles -----------------------
    _grant_system_role_perms(op.get_bind())


def _grant_system_role_perms(bind) -> None:
    """Additive merge of appointments.stage into the system roles' perms.

    Never removes anything (a customized role keeps its edits) and never
    touches custom roles. Unknown/missing roles are skipped.
    """
    for name in ROLES_GETTING_PERMS:
        row = bind.execute(
            sa.text(
                "SELECT id, permissions_json FROM roles "
                "WHERE is_system = TRUE AND deleted_at IS NULL AND name = :name"
            ),
            {"name": name},
        ).fetchone()
        if row is None:
            continue
        try:
            perms = json.loads(row.permissions_json or "[]")
            if not isinstance(perms, list):
                perms = []
        except (TypeError, ValueError):
            perms = []
        merged = sorted(set(perms) | set(NEW_PERMS))
        if merged != sorted(perms):
            bind.execute(
                sa.text("UPDATE roles SET permissions_json = :json WHERE id = :id"),
                {"json": json.dumps(merged, ensure_ascii=False), "id": int(row.id)},
            )
    logging.getLogger("alembic").info(
        "granted appointments.stage to system roles: %s", ", ".join(ROLES_GETTING_PERMS)
    )


def downgrade() -> None:
    """Structural rollback only: the permission merge stays (additive)."""
    op.drop_index("ix_prescriptions_patient_prescribed_at", table_name="prescriptions")
    op.create_index("ix_prescriptions_patient_id", "prescriptions", ["patient_id"])
    op.drop_index(
        "ix_questionnaire_responses_patient_created_at",
        table_name="questionnaire_responses",
    )
    op.create_index(
        "ix_questionnaire_responses_patient_id", "questionnaire_responses", ["patient_id"]
    )
    op.drop_index(
        "ix_attachments_patient_created_at", table_name="attachments"
    )
    op.create_index("ix_attachments_patient_id", "attachments", ["patient_id"])
    with op.batch_alter_table("appointments") as batch:
        batch.drop_column("stage")
