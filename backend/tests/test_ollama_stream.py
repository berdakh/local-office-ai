import httpx
import pytest

from app.llm import OllamaClient


@pytest.mark.asyncio
@pytest.mark.parametrize("finished", [True, False])
async def test_ollama_requires_done_marker(finished):
    def respond(request):
        body = '{"message":{"content":"A reply"},"done":false}\n'
        if finished:
            body += '{"done":true}\n'
        return httpx.Response(200, text=body)

    llm = OllamaClient("http://127.0.0.1:11434", "example", "example")
    await llm.aclose()
    llm._client = httpx.AsyncClient(base_url=llm.base_url, transport=httpx.MockTransport(respond))
    try:
        if finished:
            assert await llm.generate("Example prompt") == "A reply"
        else:
            with pytest.raises(ValueError, match="before confirming"):
                await llm.generate("Example prompt")
    finally:
        await llm.aclose()
