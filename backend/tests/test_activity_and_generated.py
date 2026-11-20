import asyncio
from threading import Event
from time import monotonic, sleep


def test_background_work_reports_stage_and_saves_each_output(client, stub_llm, monkeypatch):
    entered = Event()
    release = Event()

    async def generate(prompt, **kwargs):
        entered.set()
        await asyncio.to_thread(release.wait, 5)
        return "A draft for the bulletin."

    monkeypatch.setattr(stub_llm, "generate", generate)
    started = client.post(
        "/api/workflows/sermon_studio/jobs",
        json={
            "inputs": {"transcript": "We read John 3:16."},
            "selected_outputs": ["summary"],
            "resume": {"transcript_id": 7},
        },
    )
    assert started.status_code == 202
    job_id = started.json()["job_id"]
    try:
        assert entered.wait(3)
        activity = client.get("/api/jobs").raise_for_status().json()
        assert activity[0]["id"] == job_id
        assert activity[0]["status"] == "running"
        assert activity[0]["detail"] == "Writing summary"
        assert 0 < activity[0]["progress"] < 1
        assert activity[0]["route"] == "/sermon"
        assert "context" not in activity[0]
        detail = client.get(f"/api/jobs/{job_id}").raise_for_status().json()
        assert detail["context"]["workflow"] == "sermon_studio"
        assert detail["context"]["inputs"] == {"transcript": "We read John 3:16."}
        assert detail["context"]["selected_outputs"] == ["summary"]
        assert detail["context"]["transcript_id"] == 7
        assert client.get(f"/api/transcription-jobs/{job_id}/audio").status_code == 404
        assert client.get("/api/generated").json()["total"] == 0
    finally:
        release.set()

    deadline = monotonic() + 5
    while monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").raise_for_status().json()
        if job["status"] in {"done", "error"}:
            break
        sleep(0.03)
    assert job["status"] == "done", job
    assert job["progress"] == 1
    assert job["context"] == detail["context"]
    texts = (
        client.get("/api/generated", params={"run_id": job["result"]["run_id"]})
        .raise_for_status()
        .json()
    )
    assert texts["total"] == 1
    row = texts["items"][0]
    assert row["status"] == "draft" and row["output_key"] == "summary"
    assert row["created_at"].endswith("Z") and row["model"]
    record_id = row["id"]
    changes = {
        "title": "Sunday summary",
        "body": "Edited text",
        "status": "reviewed",
        "tags": ["bulletin", "bulletin"],
    }
    saved = client.put(f"/api/generated/{record_id}", json=changes).raise_for_status().json()
    assert saved["tags"] == ["bulletin"] and saved["created_at"] == row["created_at"]
    assert client.get(f"/api/generated/{record_id}").json()["body"] == "Edited text"
    filtered = client.get("/api/generated", params={"q": "bulletin", "status": "reviewed"}).json()
    assert filtered["total"] == 1


def test_office_answers_are_archived(client, stub_llm, monkeypatch):
    async def quote(prompt, **kwargs):
        return "A"

    monkeypatch.setattr(stub_llm, "generate", quote)
    client.post(
        "/api/library",
        files={"file": ("policy.md", b"Alex handles room reservations.", "text/markdown")},
    ).raise_for_status()
    answer = (
        client.post("/api/ask", json={"question": "Who handles room reservations?"})
        .raise_for_status()
        .json()
    )
    assert answer["answer"] == "Alex handles room reservations. [1]"
    assert [hit["title"] for hit in answer["citations"]] == ["policy"]
    response = client.get("/api/generated", params={"workflow": "ask"}).raise_for_status().json()
    assert response["total"] == 1
    assert response["items"][0]["title"] == "Who handles room reservations?"


def test_empty_office_library_skips_model_and_archive(client, stub_llm):
    reply = client.post("/api/ask", json={"question": "Who handles room reservations?"})
    assert reply.status_code == 200
    assert not reply.json()["citations"]
    assert "find relevant passages" in reply.json()["answer"]
    assert stub_llm.calls == []
    assert client.get("/api/generated").json()["total"] == 0


def test_office_discards_unverified_quotes_and_citations(client, stub_llm, monkeypatch):
    client.post(
        "/api/library",
        files={"file": ("policy.md", b"The facility deposit is $250.", "text/markdown")},
    ).raise_for_status()

    for reply in (
        "A The facility deposit is $500.",
        "Z",
        "X",
    ):

        async def generate(prompt, _reply=reply, **kwargs):
            return _reply

        monkeypatch.setattr(stub_llm, "generate", generate)
        result = (
            client.post(
                "/api/ask", json={"question": "What is the interest rate on the facility deposit?"}
            )
            .raise_for_status()
            .json()
        )
        assert "couldn’t find an answer" in result["answer"]
        assert result["citations"] == []
    assert client.get("/api/generated").json()["total"] == 0
