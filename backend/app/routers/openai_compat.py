import time
import uuid
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
import httpx

from ..auth import require_bearer_key
from ..config import settings
from ..agents.graph import graph

router = APIRouter(prefix="/v1", tags=["openai-compat"])


def _last_user_content(messages: list[dict]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            return m.get("content", "")
    return ""


def _wrap_openai(content: str, model: str, agent_used: str) -> dict:
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": content},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "x_agent_used": agent_used,
    }


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
    messages = body.get("messages", [])
    query = _last_user_content(messages)
    model = body.get("model", "chat")

    result = graph.invoke({
        "messages": [HumanMessage(content=query)],
        "agent_used": "",
    })

    ai_msgs = [m for m in result["messages"] if m.__class__.__name__ == "AIMessage"]
    content = ai_msgs[-1].content if ai_msgs else "Sin respuesta"
    agent_used = result.get("agent_used", "unknown")

    if body.get("stream", False):
        async def _fake_stream():
            import json
            chunk = {
                "id": f"chatcmpl-{uuid.uuid4().hex}",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model,
                "choices": [{"index": 0, "delta": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            }
            yield f"data: {json.dumps(chunk)}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(_fake_stream(), media_type="text/event-stream")

    return _wrap_openai(content, model, agent_used)


@router.get("/models")
async def list_models(_: str = Depends(require_bearer_key)):
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{settings.litellm_base_url}/v1/models",
            headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
        )
        resp.raise_for_status()
    return resp.json()
