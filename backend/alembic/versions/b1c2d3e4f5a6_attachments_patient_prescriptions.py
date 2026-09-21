"""attachments → patient-level; structured prescriptions from legacy rx text

Revision ID: b1c2d3e4f5a6
Revises: f9e8d7c6b5a4
Create Date: 2026-09-19

1.3 schema + data migration:

- `attachments.appointment_id` → `attachments.patient_id`: files now belong
  to the PATIENT (they survive appointment deletion). Backfilled from the
  parent appointment; a dangling appointment_id fails the migration loudly
  instead of guessing.
- New tables: `prescription_items` (tag-like dictionary), `prescriptions`
  (patient-level, replaces the legacy free-text `appointments.rx`) and
  `prescription_item_links` (items + quantities).
- Data conversion for every appointment with non-empty `rx`: one
  prescription per appointment (prescribed_at = the appointment's
  scheduled_at, provenance in source_appointment_id); items are parsed by
  app.services.rx_migration (shared with scripts/migrate_sqlite.py — split
  on comma/newline, trailing integer = quantity); only names seen ≥
  RX_MIN_FREQUENCY times across the whole corpus enter the dictionary,
  everything rarer is preserved VERBATIM in the prescription's notes. The
  deprecated `rx` column is kept as a lossless archive and is no longer
  written by the app.
- The admin/doctor system roles gain prescriptions.read / prescriptions.write
  (additive merge into permissions_json — removals never happen here; the
  admin role is UI-locked, so this migration is the only automatic path).

Safe to auto-apply on a live database: the whole upgrade runs in one
transaction (PostgreSQL DDL is transactional); any error rolls everything
back. The rx column is NOT dropped.
"""

import json
import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "f9e8d7c6b5a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Mirrors app.core.permissions (kept inline so the migration never depends
# on app code that may drift — same pattern as d4e5f6a7b8c9).
NEW_PERMS = ["prescriptions.read", "prescriptions.write"]
# which system roles receive the new permissions (receptionist: none —
# prescriptions are medical data, consistent with medical_notes.view)
ROLES_GETTING_PERMS = ("admin", "doctor")


def upgrade() -> None:
    # --- 1. attachments: appointment → patient ---------------------------------
    op.add_column(
        "attachments",
        sa.Column("patient_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_attachments_patient_id",
        "attachments",
        "patients",
        ["patient_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.execute(
        "UPDATE attachments SET patient_id = appointments.patient_id "
        "FROM appointments WHERE attachments.appointment_id = appointments.id"
    )
    orphaned = op.get_bind().execute(
        sa.text("SELECT id FROM attachments WHERE patient_id IS NULL")
    ).fetchall()
    if orphaned:
        raise RuntimeError(
            f"attachments with a dangling appointment_id: {[r[0] for r in orphaned]}; "
            "resolve them manually before migrating"
        )
    op.create_index("ix_attachments_patient_id", "attachments", ["patient_id"])
    with op.batch_alter_table("attachments") as batch:
        batch.alter_column("patient_id", existing_type=sa.Integer(), nullable=False)
        batch.drop_column("appointment_id")

    # --- 2. prescription tables ------------------------------------------------
    # Persian alphabetical order at the DB level, matching tags/diagnoses
    # (f9e8d7c6b5a4 precedes this revision in the merged chain, so the
    # fa_sort collation exists whenever this runs on PostgreSQL; SQLite
    # keeps BINARY — no ICU there).
    item_name: sa.String = sa.String(length=128)
    if op.get_bind().dialect.name == "postgresql":
        item_name = sa.String(length=128, collation="fa_sort")
    op.create_table(
        "prescription_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", item_name, nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_prescription_items_name_live",
        "prescription_items",
        ["name"],
        unique=True,
        sqlite_where=sa.text("deleted_at IS NULL"),
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "prescriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column(
            "prescribed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("source_appointment_id", sa.Integer(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_prescriptions_patient_id", "prescriptions", ["patient_id"])
    op.create_index(
        "ix_prescriptions_source_appointment_id",
        "prescriptions",
        ["source_appointment_id"],
    )
    op.create_table(
        "prescription_item_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("prescription_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["prescription_id"], ["prescriptions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["item_id"], ["prescription_items.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_prescription_item_links_pair",
        "prescription_item_links",
        ["prescription_id", "item_id"],
        unique=True,
    )

    # --- 3. convert legacy rx free text ----------------------------------------
    _convert_rx(op.get_bind())

    # --- 4. grant the new permissions to admin/doctor system roles -------------
    _grant_system_role_perms(op.get_bind())


def _convert_rx(bind) -> None:
    """Convert appointments.rx free text into structured prescriptions.

    Imports app.services.rx_migration — the frozen v1.3 parser shared with
    scripts/migrate_sqlite.py. Both callers MUST keep the exact same
    semantics; the unit tests pin them down.
    """
    from app.services.rx_migration import (
        RX_MIN_FREQUENCY,
        overflow_notes,
        plan_rx_migration,
    )

    rows = bind.execute(
        sa.text(
            "SELECT id, patient_id, scheduled_at, rx FROM appointments "
            "WHERE rx IS NOT NULL AND rx <> ''"
        )
    ).fetchall()
    if not rows:
        return

    planned, dictionary = plan_rx_migration(
        [(int(r.id), int(r.patient_id), r.scheduled_at, r.rx) for r in rows],
        min_frequency=RX_MIN_FREQUENCY,
    )

    # dictionary items (fresh table — nothing to dedupe against)
    item_ids: dict[str, int] = {}
    for key, display in sorted(dictionary.items()):
        item_id = bind.execute(
            sa.text(
                "INSERT INTO prescription_items (name) VALUES (:name) RETURNING id"
            ),
            {"name": display[:128]},
        ).scalar_one()
        item_ids[key] = item_id

    # prescriptions (executemany); source_appointment_id is 1:1 per
    # prescription, so re-selecting it rebuilds the id map without
    # per-row RETURNING round trips
    payload = [
        {
            "patient_id": p.patient_id,
            "prescribed_at": p.prescribed_at,
            "notes": overflow_notes(p.notes_overflow)[:10000],
            "source_appointment_id": p.appointment_id,
        }
        for p in planned
    ]
    n_links = 0
    if payload:
        bind.execute(
            sa.text(
                "INSERT INTO prescriptions "
                "(patient_id, prescribed_at, notes, source_appointment_id) "
                "VALUES (:patient_id, :prescribed_at, :notes, :source_appointment_id)"
            ),
            payload,
        )
        rx_ids = bind.execute(
            sa.text(
                "SELECT id, source_appointment_id FROM prescriptions "
                "WHERE source_appointment_id IS NOT NULL"
            )
        ).fetchall()
        rx_id_by_appt = {int(r.source_appointment_id): int(r.id) for r in rx_ids}

        # displays are unique per normalized key → safe reverse map
        key_of = {display: key for key, display in dictionary.items()}
        link_payload = [
            {
                "prescription_id": rx_id_by_appt[p.appointment_id],
                "item_id": item_ids[key_of[link.name]],
                "quantity": link.quantity,
            }
            for p in planned
            for link in p.links
        ]
        if link_payload:
            bind.execute(
                sa.text(
                    "INSERT INTO prescription_item_links "
                    "(prescription_id, item_id, quantity) "
                    "VALUES (:prescription_id, :item_id, :quantity)"
                ),
                link_payload,
            )
        n_links = len(link_payload)

    logging.getLogger("alembic").info(
        "rx migration: %d appointments → %d prescriptions, "
        "%d dictionary items, %d links",
        len(rows),
        len(payload),
        len(dictionary),
        n_links,
    )


def _grant_system_role_perms(bind) -> None:
    """Additive merge of the new permissions into admin/doctor permissions.

    Never removes anything (a customized doctor role keeps its edits) and
    never touches custom roles. Unknown/missing roles are skipped.
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


def downgrade() -> None:
    raise NotImplementedError(
        "the 1.3 migration is not reversible (legacy rx → prescriptions "
        "conversion is one-way; the deprecated rx column is preserved)"
    )
