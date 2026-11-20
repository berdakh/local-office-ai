from io import BytesIO
from pathlib import Path

import docx

from app.rag import get_document
from app.render.letterhead import build_letterhead


def test_health_without_ollama(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["pack"] == "church"
    assert body["ollama"]["available"] is False


def test_workflows_listed(client):
    ids = {w["id"] for w in client.get("/api/workflows").json()}
    assert "sermon_studio" in ids


def test_model_preferences_and_sermon_run_overrides(client, conn, stub_llm):
    original = client.get("/api/settings").json()["chat_model"]
    assert client.get("/api/settings/models").json() == ["example:small", "example:large"]
    assert client.put("/api/settings/models", json={"chat_model": "missing"}).status_code == 400
    updated = client.put("/api/settings/models", json={"chat_model": "example:small"})
    assert updated.status_code == 200
    assert conn.execute("SELECT value FROM app_preferences").fetchone()["value"] == "example:small"

    response = client.post(
        "/api/workflows/sermon_studio/run",
        json={
            "inputs": {"transcript": "Today we turn to John 3:16."},
            "selected_outputs": ["summary"],
            "chat_model": "example:large",
        },
    )
    assert response.status_code == 200
    assert list(response.json()["outputs"]) == ["summary"]
    assert stub_llm.calls[-1]["model"] == "example:large"
    assert len(stub_llm.calls) == 1

    client.post(
        "/api/library", files={"file": ("hours.md", b"The office opens at 9 a.m.", "text/markdown")}
    ).raise_for_status()
    client.post("/api/ask", json={"question": "When does the office open?"}).raise_for_status()
    assert stub_llm.calls[-1]["model"] == "example:small"
    assert client.get("/api/health").json()["chat_model"] == "example:small"
    reset = client.put("/api/settings/models", json={"chat_model": None})
    assert reset.json()["chat_model"] == original


def test_upload_ask_and_audit(client, stub_llm, monkeypatch):
    async def quote(prompt, **kwargs):
        return "A"

    monkeypatch.setattr(stub_llm, "generate", quote)
    r = client.post(
        "/api/library",
        files={"file": ("policy.md", b"The fellowship hall seats 120 people.", "text/markdown")},
    )
    assert r.status_code == 200, r.text
    assert client.get("/api/library").json()[0]["title"] == "policy"

    r = client.post("/api/ask", json={"question": "How many seats in the fellowship hall?"})
    assert r.status_code == 200, r.text
    assert r.json()["citations"][0]["title"] == "policy"

    actions = [e["action"] for e in client.get("/api/audit").json()]
    assert "ask" in actions and "library.upload" in actions


def test_rejects_unknown_file_type(client):
    r = client.post("/api/library", files={"file": ("x.exe", b"nope", "application/octet-stream")})
    assert r.status_code == 400


def test_same_filename_documents_keep_both_original_files(client, conn):
    uploads = [b"The church opens at nine.", b"The church opens at ten."]
    documents = []
    for data in uploads:
        response = client.post("/api/library", files={"file": ("hours.md", data, "text/markdown")})
        assert response.status_code == 200
        documents.append(get_document(conn, response.json()["document_id"]))

    assert [doc["title"] for doc in documents] == ["hours", "hours"]
    assert [Path(doc["path"]).read_bytes() for doc in documents] == uploads


def test_root_without_frontend_build(client):
    assert "backend is running" in client.get("/").json()["message"]


def test_letter_exports_use_edited_text_and_letterhead(client, tmp_path):
    # The export path needs the output definition and template, but no live model.
    templates = tmp_path / "templates"
    build_letterhead(templates / "letterhead.docx", "Grace Community Church")
    client.app.state.pack.root = tmp_path
    edited = "Dear Alex,\n\nThank you for helping with Sunday's service."
    path = "/api/workflows/letter/outputs/letter/export"
    markdown = client.post(path, json={"text": edited, "format": "md"})
    word = client.post(path, json={"text": edited, "format": "docx"})

    assert markdown.status_code == word.status_code == 200
    assert markdown.text == edited
    assert markdown.headers["content-disposition"].endswith("letter.md")
    assert word.headers["content-disposition"].endswith("letter.docx")
    doc = docx.Document(BytesIO(word.content))
    assert [p.text for p in doc.paragraphs] == [
        "Dear Alex,",
        "Thank you for helping with Sunday's service.",
    ]
    assert doc.sections[0].header.paragraphs[0].text == "Grace Community Church"


def test_workflow_runs_preserve_previous_files(client):
    payload = {"inputs": {"letter_type": "Thank-you", "fields": {"recipient": "Alex"}}}
    first = client.post("/api/workflows/letter/run", json=payload)
    second = client.post("/api/workflows/letter/run", json=payload)

    assert first.status_code == second.status_code == 200
    assert first.json()["run_id"] != second.json()["run_id"]
    first_file = Path(first.json()["files"][0])
    second_file = Path(second.json()["files"][0])
    assert first_file != second_file
    assert first_file.is_file() and second_file.is_file()
