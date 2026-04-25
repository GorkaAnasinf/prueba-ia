from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
import httpx

from ..auth import require_bearer_key
from ..config import settings
from .rag import _qdrant, _embed, _ensure_collection

router = APIRouter(prefix="/v1", tags=["openai-compat"])


def _rag_context(query: str) -> str:
    try:
        client = _qdrant()
        _ensure_collection(client)
        hits = client.search(
            collection_name=settings.rag_collection,
            query_vector=_embed(query),
            limit=3,
        )
        if not hits:
            return ""
        chunks = "\n\n---\n\n".join(
            f"[{h.payload['file']}]\n{h.payload['content']}" for h in hits
        )
        return f"Contexto relevante de la base de conocimiento:\n\n{chunks}"
    except Exception:
        return ""


def _inject_rag(messages: list[dict]) -> list[dict]:
    last_user = next(
        (m["content"] for m in reversed(messages) if m["role"] == "user"),
        None,
    )
    if not last_user:
        return messages

    context = _rag_context(last_user)
    if not context:
        return messages

    messages = list(messages)
    if messages and messages[0]["role"] == "system":
        messages[0] = {**messages[0], "content": context + "\n\n" + messages[0]["content"]}
    else:
        messages.insert(0, {"role": "system", "content": context})
    return messages


async def _stream_from_litellm(payload: dict):
    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream(
            "POST",
            f"{settings.litellm_base_url}/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
            json={**payload, "stream": True},
        ) as resp:
            async for chunk in resp.aiter_text():
                yield chunk


@router.post("/chat/completions")
async def chat_completions(request: Request, _: str = Depends(require_bearer_key)):
    body = await request.json()
    body["messages"] = _inject_rag(body.get("messages", []))

    if body.get("stream", False):
        return StreamingResponse(
            _stream_from_litellm(body),
            media_type="text/event-stream",
        )

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{settings.litellm_base_url}/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
            json=body,
        )
        resp.raise_for_status()
    return resp.json()


@router.get("/models")
async def list_models(_: str = Depends(require_bearer_key)):
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{settings.litellm_base_url}/v1/models",
            headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
        )
        resp.raise_for_status()
    return resp.json()
