from fastapi import APIRouter

from . import (
    ask,
    audit,
    chat,
    correspondence,
    generated,
    hardware,
    health,
    jobs,
    library,
    scripture,
    settings,
    transcribe,
    workbench,
    workflows,
)

router = APIRouter(prefix="/api")
for mod in (
    health,
    settings,
    library,
    workflows,
    ask,
    jobs,
    audit,
    transcribe,
    scripture,
    chat,
    correspondence,
    generated,
    hardware,
    workbench,
):
    router.include_router(mod.router)
