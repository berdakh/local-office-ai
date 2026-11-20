"""Local address book, saved drafts, and email export."""

from __future__ import annotations

from email import policy
from email.headerregistry import Address
from email.message import EmailMessage

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator

from .deps import get_conn

router = APIRouter(prefix="/correspondence", tags=["correspondence"])


class Contact(BaseModel):
    name: str = Field(min_length=1, max_length=140)
    email: str = Field(min_length=3, max_length=254)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        if not value.strip() or "\r" in value or "\n" in value:
            raise ValueError("Enter a name on one line.")
        return value.strip()

    @field_validator("email")
    @classmethod
    def clean_email(cls, value: str) -> str:
        return email_address(value)


def email_address(value: str) -> str:
    address = Address(addr_spec=value.strip())
    if not address.username or not address.domain:
        raise ValueError("Enter an email address.")
    return address.addr_spec


class Draft(BaseModel):
    recipient: str = Field(default="", max_length=140)
    email: str = Field(default="", max_length=254)
    subject: str = Field(default="", max_length=250)
    body: str = Field(default="", max_length=30_000)
    template: str = Field(default="", max_length=100)
    notes: str = Field(default="", max_length=5000)

    @field_validator("recipient", "subject")
    @classmethod
    def single_line(cls, value: str) -> str:
        if "\r" in value or "\n" in value:
            raise ValueError("Use a single line.")
        return value.strip()

    @field_validator("email")
    @classmethod
    def clean_email(cls, value: str) -> str:
        return email_address(value) if value.strip() else ""


@router.get("/contacts")
async def contacts(conn=Depends(get_conn)):
    return [
        dict(row) for row in conn.execute("SELECT * FROM contacts ORDER BY name COLLATE NOCASE")
    ]


@router.post("/contacts")
async def save_contact(contact: Contact, conn=Depends(get_conn)):
    row = conn.execute(
        "INSERT INTO contacts(name, email) VALUES (?, ?) "
        "ON CONFLICT(email) DO UPDATE SET name = excluded.name RETURNING *",
        (contact.name, contact.email.casefold()),
    ).fetchone()
    conn.commit()
    return dict(row)


@router.get("/drafts")
async def drafts(conn=Depends(get_conn)):
    return [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM correspondence_drafts ORDER BY updated_at DESC, id DESC"
        )
    ]


@router.post("/drafts")
async def save_new_draft(draft: Draft, conn=Depends(get_conn)):
    row = conn.execute(
        "INSERT INTO correspondence_drafts(recipient,email,subject,body,template,notes) "
        "VALUES (:recipient,:email,:subject,:body,:template,:notes) RETURNING *",
        draft.model_dump(),
    ).fetchone()
    conn.commit()
    return dict(row)


@router.put("/drafts/{draft_id}")
async def update_draft(draft_id: int, draft: Draft, conn=Depends(get_conn)):
    row = conn.execute(
        "UPDATE correspondence_drafts SET recipient=:recipient,email=:email,subject=:subject,"
        "body=:body,template=:template,notes=:notes,updated_at=datetime('now') "
        "WHERE id=:id RETURNING *",
        {**draft.model_dump(), "id": draft_id},
    ).fetchone()
    conn.commit()
    if row is None:
        raise HTTPException(404, "This draft is no longer available.")
    return dict(row)


@router.post("/export")
def export_email(draft: Draft):
    message = EmailMessage(policy=policy.SMTP)
    if draft.email:
        address = Address(addr_spec=draft.email)
        message["To"] = Address(
            display_name=draft.recipient, username=address.username, domain=address.domain
        )
    message["Subject"] = draft.subject
    message["X-Unsent"] = "1"
    message.set_content(draft.body)
    return Response(
        message.as_bytes(),
        media_type="message/rfc822",
        headers={"Content-Disposition": 'attachment; filename="office-draft.eml"'},
    )
