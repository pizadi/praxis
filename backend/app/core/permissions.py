"""Canonical authorization keys and system-role permission sets.

Persian UI labels live in ``permission_labels_fa`` and are not imported by
authorization logic. The catalog stores stable group identifiers so API
presentation can attach translated labels without coupling them to security.
"""

PERMISSION_CATALOG: list[tuple[str, tuple[str, ...]]] = [
    (
        "patients",
        ("patients.read", "patients.create", "patients.update", "patients.delete"),
    ),
    (
        "appointments",
        (
            "appointments.read",
            "appointments.create",
            "appointments.update",
            "appointments.stage",
            "appointments.delete",
        ),
    ),
    ("files", ("files.read", "files.write", "files.delete")),
    (
        "transactions",
        ("transactions.read", "transactions.write", "transactions.delete", "payments.view"),
    ),
    ("medical", ("medical_notes.view",)),
    ("prescriptions", ("prescriptions.read", "prescriptions.write")),
    (
        "questionnaires",
        ("questionnaires.read", "questionnaires.fill", "questionnaires.templates"),
    ),
    ("stats", ("stats.view", "taxonomies.write")),
    ("trash", ("trash.view", "trash.restore", "trash.purge")),
    (
        "admin",
        ("users.manage", "roles.manage", "audit.view", "backup.manage"),
    ),
]

ALL_PERMISSIONS: frozenset[str] = frozenset(
    permission for _, permissions in PERMISSION_CATALOG for permission in permissions
)

# System roles reproduce the legacy hierarchy exactly so existing users keep
# their access. Admin remains the full catalog and is healed by bootstrap.
_ADMIN_PERMS = sorted(ALL_PERMISSIONS)

_DOCTOR_PERMS = [
    "patients.read",
    "patients.create",
    "patients.update",
    "appointments.read",
    "appointments.create",
    "appointments.update",
    "appointments.stage",
    "appointments.delete",
    "files.read",
    "files.write",
    "files.delete",
    "transactions.read",
    "transactions.write",
    "transactions.delete",
    "medical_notes.view",
    "questionnaires.read",
    "questionnaires.fill",
    "payments.view",
    "stats.view",
    "taxonomies.write",
    "trash.view",
    "trash.restore",
    "prescriptions.read",
    "prescriptions.write",
]
_RECEPTIONIST_PERMS = [
    "patients.read",
    "patients.create",
    "patients.update",
    "appointments.read",
    "appointments.create",
    "appointments.stage",
    "files.read",
    "transactions.read",
    "transactions.write",
    "transactions.delete",
    "questionnaires.read",
    "questionnaires.fill",
    "payments.view",
]

SYSTEM_ROLES: dict[str, list[str]] = {
    "admin": _ADMIN_PERMS,
    "doctor": _DOCTOR_PERMS,
    "receptionist": _RECEPTIONIST_PERMS,
}
