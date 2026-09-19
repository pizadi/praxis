from fastapi import APIRouter

from app.api.v1 import (
    appointments,
    attachments,
    audit,
    auth,
    backup,
    meta,
    patients,
    payments,
    questionnaires,
    roles,
    stats,
    taxonomies,
    transactions,
    trash,
    users,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(roles.router)
api_router.include_router(questionnaires.router)
api_router.include_router(patients.router)
api_router.include_router(appointments.router)
api_router.include_router(attachments.router)
api_router.include_router(transactions.router)
api_router.include_router(payments.router)
api_router.include_router(taxonomies.router)
api_router.include_router(stats.router)
api_router.include_router(trash.router)
api_router.include_router(audit.router)
api_router.include_router(backup.router)
api_router.include_router(meta.router)
