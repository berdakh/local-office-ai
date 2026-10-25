import io
import time
import wave

from app.transcribe import Bible
from app.transcribe.whisper import Segment


class FakeTranscriber:
    last_duration = 42.0

    def transcribe(self, path, progress=None):
        if progress:
            progress(0.5)
            progress(1.0)
        return [
            Segment(0.0, 5.0, "Welcome everyone."),
            Segment(5.0, 12.0, "Today we read John 3:16 and Psalm 23."),
        ]


def _wav_bytes() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * 8000)
    return buf.getvalue()


def _wait(client, job_id, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in {"done", "error"}:
            return job
        time.sleep(0.1)
    raise AssertionError("job did not finish")


def test_transcribe_creates_transcript_with_scripture(client, monkeypatch):
    monkeypatch.setattr("app.api.transcribe.transcription_available", lambda: True)
    client.app.state.transcriber = FakeTranscriber()
    client.app.state.bible = Bible(
        {"John": {"3": {"16": "For God so loved the world."}}, "Psalms": {"23": {"1": "x"}}}
    )

    r = client.post("/api/transcribe", files={"file": ("sunday.wav", _wav_bytes(), "audio/wav")})
    assert r.status_code == 200, r.text
    job = _wait(client, r.json()["job_id"])
    assert job["status"] == "done", job["error"]
    res = job["result"]
    assert "John 3:16" in res["text"] and res["segments"] == 2 and res["duration"] == 42.0
    statuses = {s["ref"]: s["status"] for s in res["scripture"]}
    assert statuses == {"John 3:16": "verified", "Psalms 23": "verified"}
    assert res["embedded"] is True  # stub LLM embeds

    lst = client.get("/api/transcripts").json()
    assert lst[0]["title"] == "sunday" and lst[0]["duration"] == 42.0
    full = client.get(f"/api/transcripts/{res['document_id']}").json()
    assert full["text"].startswith("Welcome everyone.")
    assert full["meta"]["segments"] == 2

    # The transcript is searchable like any other document
    ask = client.post("/api/ask", json={"question": "What did we read today?"}).json()
    assert any(c["title"] == "sunday" for c in ask["citations"])


def test_transcribe_rejects_non_audio(client, monkeypatch):
    monkeypatch.setattr("app.api.transcribe.transcription_available", lambda: True)
    r = client.post("/api/transcribe", files={"file": ("notes.txt", b"hi", "text/plain")})
    assert r.status_code == 400


def test_transcribe_without_faster_whisper_is_503(client, monkeypatch):
    monkeypatch.setattr("app.api.transcribe.transcription_available", lambda: False)
    r = client.post("/api/transcribe", files={"file": ("a.mp3", b"x", "audio/mpeg")})
    assert r.status_code == 503


def test_scripture_check_endpoint(client):
    client.app.state.bible = Bible({"John": {"3": {"16": "For God so loved the world."}}})
    r = client.post("/api/scripture/check", json={"text": "See John 3:16 and John 9:99."}).json()
    assert r["verified_against"] == "WEB"
    assert [x["status"] for x in r["refs"]] == ["verified", "not_found"]
