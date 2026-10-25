"""Scripture reference detection and verification against the local Bible text."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.transcribe import check_text

from .deps import get_bible

router = APIRouter(prefix="/scripture", tags=["scripture"])


class CheckRequest(BaseModel):
    text: str


@router.post("/check")
async def check(req: CheckRequest, bible=Depends(get_bible)):
    checks = check_text(req.text, bible)
    return {
        "verified_against": bible.version if bible else None,
        "refs": [c.to_dict() for c in checks],
    }
