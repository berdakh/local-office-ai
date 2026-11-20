"""Scripture reference detection and verification against the local Bible text."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.transcribe import Bible, check_text
from app.transcribe.lookup import lookup

from .deps import get_bible

router = APIRouter(prefix="/scripture", tags=["scripture"])


@router.get("/lookup")
def find_passages(
    q: str = Query(min_length=1, max_length=260), bible: Bible | None = Depends(get_bible)
):
    if bible is None:
        raise HTTPException(503, "The local Bible is unavailable. Check Settings.")
    return {"version": bible.version, "passages": lookup(bible, q, topics=True)}


class CheckRequest(BaseModel):
    text: str


@router.post("/check")
async def check(req: CheckRequest, bible=Depends(get_bible)):
    checks = check_text(req.text, bible)
    return {
        "verified_against": bible.version if bible else None,
        "refs": [c.to_dict() for c in checks],
    }
