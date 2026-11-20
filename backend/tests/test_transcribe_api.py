import io
import time
import wave
from pathlib import Path

import pytest

from app.transcribe import Bible
from app.transcribe.whisper import Segment, Transcription


class FakeTranscriber:
    def transcribe(self, path, progress=None):
        if progress:
            progress(0.5)
            progress(1.0)
        opening = "Welcome back." if path.read_bytes().endswith(b"second") else "Welcome everyone."
        return Transcription(
            [
                Segment(0.0, 5.0, opening),
                Segment(5.0, 12.0, "Today we read John 3:16 and Psalm 23."),
            ],
            42.0,
        )


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


def test_whisper_can_decode_supported_audio_with_locked_dependencies():
    audio = pytest.importorskip("faster_whisper.audio")
    decoded = audio.decode_audio(io.BytesIO(_wav_bytes()), sampling_rate=8000)
    assert len(decoded) == 8000


def test_transcribe_creates_transcript_with_scripture(client, stub_llm, monkeypatch):
    monkeypatch.setattr("app.api.transcribe.transcription_available", lambda _: True)
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

    async def quote(prompt, **kwargs):
        assert "John 3:16 and Psalm 23" in prompt
        return "A"

    monkeypatch.setattr(stub_llm, "generate", quote)
    # The transcript is searchable like any other document
    ask = client.post("/api/ask", json={"question": "What did we read today?"}).json()
    assert any(c["title"] == "sunday" for c in ask["citations"])


def test_transcribe_rejects_non_audio(client, monkeypatch):
    monkeypatch.setattr("app.api.transcribe.transcription_available", lambda _: True)
    r = client.post("/api/transcribe", files={"file": ("notes.txt", b"hi", "text/plain")})
    assert r.status_code == 400


def test_transcribe_without_faster_whisper_is_503(client, monkeypatch):
    monkeypatch.setattr("app.api.transcribe.transcription_available", lambda _: False)
    r = client.post("/api/transcribe", files={"file": ("a.mp3", b"x", "audio/mpeg")})
    assert r.status_code == 503


def test_same_filename_recordings_keep_their_own_audio_and_transcript(client, monkeypatch):
    monkeypatch.setattr("app.api.transcribe.transcription_available", lambda _: True)
    client.app.state.transcriber = FakeTranscriber()
    original = _wav_bytes()
    second = original + b"second"

    document_ids = []
    for recording in (original, second):
        response = client.post(
            "/api/transcribe", files={"file": ("sunday.wav", recording, "audio/wav")}
        )
        job_id = response.raise_for_status().json()["job_id"]
        media = client.get(f"/api/transcription-jobs/{job_id}/audio", headers={"Range": "bytes=-6"})
        assert media.status_code == 206
        assert media.content == recording[-6:]
        job = _wait(client, job_id)
        assert job["context"]["name"] == "sunday.wav"
        assert job["status"] == "done", job["error"]
        document_ids.append(job["result"]["document_id"])

    first, latest = (client.get(f"/api/transcripts/{doc_id}").json() for doc_id in document_ids)
    assert first["title"] == latest["title"] == "sunday"
    assert first["text"].startswith("Welcome everyone.")
    assert latest["text"].startswith("Welcome back.")
    assert Path(first["meta"]["audio_path"]).read_bytes() == original
    assert Path(latest["meta"]["audio_path"]).read_bytes() == second
    assert first["meta"]["segments_path"] != latest["meta"]["segments_path"]


def test_scripture_check_endpoint(client):
    client.app.state.bible = Bible({"John": {"3": {"16": "For God so loved the world."}}})
    r = client.post("/api/scripture/check", json={"text": "See John 3:16 and John 9:99."}).json()
    assert r["verified_against"] == "WEB"
    assert [x["status"] for x in r["refs"]] == ["verified", "not_found"]
