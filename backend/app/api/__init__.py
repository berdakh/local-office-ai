from fastapi import APIRouter

from . import ask, audit, health, jobs, library, scripture, settings, transcribe, workflows

router = APIRouter(prefix="/api")
for mod in (health, settings, library, workflows, ask, jobs, audit, transcribe, scripture):
    router.include_router(mod.router)
