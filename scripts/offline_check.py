"""Exercise a running pilot from a recording to exports after blocking outbound networking."""

from __future__ import annotations

import argparse
import time
from io import BytesIO
from pathlib import Path

import docx
import httpx

SERMON_OUTPUTS = {
    "summary",
    "key_points",
    "discussion_guide",
    "blog_post",
    "social_posts",
    "bulletin_blurb",
}


def request(client: httpx.Client, method: str, path: str, **kwargs) -> httpx.Response:
    response = client.request(method, path, **kwargs)
    if response.is_error:
        raise RuntimeError(f"{method} {path} failed ({response.status_code}): {response.text}")
    return response


def transcribe(client: httpx.Client, recording: Path, deadline: float) -> dict:
    with recording.open("rb") as audio:
        data = request(
            client, "POST", "/api/transcribe", files={"file": (recording.name, audio)}
        ).json()
    last_progress = -1
    while time.monotonic() < deadline:
        job = request(client, "GET", f"/api/jobs/{data['job_id']}").json()
        if job["status"] == "done":
            return job["result"]
        if job["status"] == "error":
            raise RuntimeError(job["error"])
        progress = int(job["progress"] * 10) * 10
        if progress != last_progress:
            print(f"Transcription {progress}%", flush=True)
            last_progress = progress
        time.sleep(2)
    raise RuntimeError("Transcription did not finish by the deadline.")


def run(args: argparse.Namespace) -> None:
    start = time.monotonic()
    with httpx.Client(
        base_url=f"http://127.0.0.1:{args.port}", timeout=args.timeout, trust_env=False
    ) as client:
        request(client, "GET", "/sermon")
        health = request(client, "GET", "/api/health").json()
        for key in (
            "chat_model_installed",
            "embed_model_installed",
            "transcription_available",
            "bible_installed",
            "letterhead_installed",
        ):
            if not health[key]:
                raise RuntimeError(f"Failed readiness check: {key}")
        result = transcribe(client, args.recording, start + args.timeout)
        recovered = request(client, "GET", f"/api/transcripts/{result['document_id']}").json()
        if (
            not result["embedded"]
            or result["duration"] < args.min_minutes * 60
            or not result["text"].strip()
            or recovered["text"] != result["text"]
        ):
            raise RuntimeError(
                "Expected an indexed, nonempty transcript for the complete recording."
            )
        verified = {item["ref"] for item in result["scripture"] if item["status"] == "verified"}
        missing_refs = set(args.expect_reference) - verified
        if missing_refs:
            raise RuntimeError(
                f"Expected verified references {sorted(missing_refs)}, found {sorted(verified)}."
            )
        print(
            f"Saved and indexed {result['duration'] / 60:.1f} minutes of audio "
            f"with {result['segments']} segments and {len(verified)} verified references.",
            flush=True,
        )
        for phrase in args.expect_transcript:
            if phrase.casefold() not in result["text"].casefold():
                raise RuntimeError(f"Transcript is missing the expected phrase {phrase!r}.")

        drafts = request(
            client,
            "POST",
            "/api/workflows/sermon_studio/run",
            json={"inputs": {"transcript": recovered["text"]}},
        ).json()
        if set(drafts["outputs"]) != SERMON_OUTPUTS or not all(
            text and text.strip() for text in drafts["outputs"].values()
        ):
            raise RuntimeError("Expected all six nonempty Sermon Studio drafts.")

        path = "/api/workflows/sermon_studio/outputs/discussion_guide/export"
        edited = drafts["outputs"]["discussion_guide"] + "\n\nReviewed for the offline pilot."
        markdown = request(client, "POST", path, json={"format": "md", "text": edited})
        word = request(client, "POST", path, json={"format": "docx", "text": edited})
        doc = docx.Document(BytesIO(word.content))
        if markdown.text != edited or doc.paragraphs[-1].text != "Reviewed for the offline pilot.":
            raise RuntimeError("Export did not preserve the edited draft.")
        print(
            f"Verified six drafts and both edited exports in {(time.monotonic() - start) / 60:.1f} "
            "minutes.",
            flush=True,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording", type=Path)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--min-minutes", type=float, default=0.0)
    parser.add_argument("--expect-reference", action="append", default=[])
    parser.add_argument("--expect-transcript", action="append", default=[])
    parser.add_argument("--timeout", type=float, default=3600)
    args = parser.parse_args()
    try:
        run(args)
    except (OSError, RuntimeError, httpx.HTTPError) as error:
        parser.exit(1, f"Offline sermon check: {error}\n")


if __name__ == "__main__":
    main()
