"""Regression coverage for local media, knowledge, and correspondence."""

import json
from email import policy
from email.parser import BytesParser

from app.transcribe import Bible


def test_recall_bible_verse_and_chapter(client):
    client.app.state.bible = Bible(
        {"John": {"3": {"16": "God loved the world.", "17": "God sent his Son."}}}
    )
    for query in ("John 3:16", "loved the world"):
        data = client.get("/api/scripture/lookup", params={"q": query}).json()
        assert data["passages"][0] == {"ref": "John 3:16", "text": "God loved the world."}
    chapter = client.get("/api/scripture/lookup", params={"q": "John 3"}).json()["passages"]
    assert chapter[0]["text"] == "16 God loved the world.\n17 God sent his Son."


def test_bible_chat_provides_local_text_and_history(client, stub_llm, monkeypatch):
    client.app.state.bible = Bible({"John": {"3": {"16": "God loved the world."}}})

    async def stream(messages, *, model, options):
        assert "God loved the world." in messages[0]["content"]
        assert messages[-2]["content"] == "It is a verse."
        yield "Look at [1]."

    monkeypatch.setattr(stub_llm, "chat_stream", stream, raising=False)
    response = client.post(
        "/api/chat",
        json={
            "mode": "bible",
            "messages": [
                {"role": "user", "content": "John 3:16"},
                {"role": "assistant", "content": "It is a verse."},
                {"role": "user", "content": "Why?"},
            ],
        },
    )
    response.raise_for_status()
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[0]["value"][0]["ref"] == "John 3:16"
    assert events[1]["value"] == "Look at [1]."
    assert events[-1]["type"] == "done"


def test_incomplete_chat_answer_is_not_archived(client, stub_llm, monkeypatch):
    async def interrupted(*args, **kwargs):
        yield "Partial answer."
        raise ValueError("Ollama stopped before confirming the answer was complete.")

    monkeypatch.setattr(stub_llm, "chat_stream", interrupted, raising=False)
    response = client.post(
        "/api/chat", json={"mode": "general", "messages": [{"role": "user", "content": "Hello"}]}
    ).raise_for_status()
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[-1]["type"] == "error"
    assert client.get("/api/generated").json()["total"] == 0


def test_correspondence_draft_persists_and_exports(client):
    person = (
        client.post(
            "/api/correspondence/contacts",
            json={
                "name": "Alex Friend",
                "email": "alex@example.org",
            },
        )
        .raise_for_status()
        .json()
    )
    data = {
        "recipient": person["name"],
        "email": person["email"],
        "subject": "Thank you",
        "body": "Thank you for helping.",
    }
    created = client.post("/api/correspondence/drafts", json=data).raise_for_status().json()
    saved = client.get("/api/correspondence/drafts").raise_for_status().json()
    assert saved[0]["id"] == created["id"]
    response = client.post("/api/correspondence/export", json=data).raise_for_status()
    mail = BytesParser(policy=policy.default).parsebytes(response.content)
    assert str(mail["To"]) == "Alex Friend <alex@example.org>"
    assert str(mail["X-Unsent"]) == "1"
    assert mail.get_content().strip() == "Thank you for helping."


def test_model_download_uses_recommended_tag_and_a_background_job(client, stub_llm, monkeypatch):
    import time

    monkeypatch.setattr(
        "app.api.hardware.inspect_hardware",
        lambda _: {"models": [{"tag": "qwen2.5:1.5b", "download_gb": 1.0}], "free_gb": 20},
    )

    async def connected():
        return True

    async def pull(name, progress):
        assert name == "qwen2.5:1.5b"
        progress(0.5)

    monkeypatch.setattr(stub_llm, "is_available", connected)
    monkeypatch.setattr(stub_llm, "pull_model", pull, raising=False)
    endpoint = "/api/settings/hardware/download"
    assert client.post(endpoint, json={"model": "other-model"}).status_code == 400
    started = client.post(endpoint, json={"model": "qwen2.5:1.5b"}).raise_for_status().json()
    for _ in range(20):
        job = client.get(f"/api/jobs/{started['job_id']}").raise_for_status().json()
        if job["status"] == "done":
            break
        time.sleep(0.02)
    assert job["status"] == "done"
    assert job["result"]["model"] == "qwen2.5:1.5b"
