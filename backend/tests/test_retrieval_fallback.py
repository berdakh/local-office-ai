import httpx
import pytest

from app.ingest import Page
from app.rag import add_document, embed_document, hybrid_search, remove_document


async def test_semantic_search_accepts_legacy_tag_and_skips_incompatible_vectors(conn):
    models = [
        ("Intended", "models/vector", [1.0, 0.0]),
        ("Old dimension", "models/vector:latest", [1.0, 0.0, 0.0]),
        ("Other model", "models/vector:v2", [1.0, 0.0]),
        ("Negative match", "models/vector:latest", [-1.0, 0.0]),
    ]
    for title, model, vector in models:
        doc_id = add_document(conn, title, f"/{title}.md", "md", [Page("Policy excerpt.")])

        async def embed(texts, vector=vector):
            return [vector] * len(texts)

        await embed_document(conn, doc_id, embed, model)

    async def query_embed(_):
        return [[1.0, 0.0]]

    hits = await hybrid_search(
        conn, "Reservations?", query_embed, embedding_model="models/vector:latest"
    )
    assert [hit.title for hit in hits] == ["Intended"]


async def test_embedding_service_failure_keeps_lexical_search_available(conn):
    doc_id = add_document(
        conn, "Parking", "/parking.md", "md", [Page("Use the north lot for parking.")]
    )

    async def index_embed(_):
        return [[1.0, 0.0]]

    await embed_document(conn, doc_id, index_embed, "vector:latest")

    async def unreachable(_):
        raise httpx.ConnectError("Embedding service offline")

    hits = await hybrid_search(
        conn, "Which lot is for parking?", unreachable, embedding_model="vector"
    )
    assert [hit.document_id for hit in hits] == [doc_id]
    assert not await hybrid_search(
        conn, "What is the software for reservations?", unreachable, embedding_model="vector"
    )


async def test_failed_embedding_batch_cannot_leak_partial_writes(conn):
    doc_id = add_document(
        conn, "Policy", "/policy.md", "md", [Page("First page."), Page("Second page.")]
    )
    calls = 0

    async def fail_on_second_batch(_):
        nonlocal calls
        calls += 1
        assert not conn.in_transaction
        if calls == 2:
            conn.commit()  # A different request may commit while an embedding is in flight.
            raise httpx.ConnectError("Embedding service offline")
        return [[1.0, 0.0]]

    with pytest.raises(httpx.ConnectError):
        await embed_document(conn, doc_id, fail_on_second_batch, "vector", batch=1)
    assert conn.execute("SELECT COUNT(*) FROM chunk_embeddings").fetchone()[0] == 0


async def test_embedding_discarded_if_document_id_is_reused(conn):
    doc_id = add_document(conn, "Policy", "/policy.md", "md", [Page("First version.")])

    async def replace_while_embedding(_):
        remove_document(conn, doc_id)
        replacement = add_document(
            conn, "Policy", "/replacement.md", "md", [Page("Revised version.")]
        )
        assert replacement == doc_id
        return [[1.0, 0.0]]

    assert await embed_document(conn, doc_id, replace_while_embedding, "vector") == 0
    assert conn.execute("SELECT COUNT(*) FROM chunk_embeddings").fetchone()[0] == 0
