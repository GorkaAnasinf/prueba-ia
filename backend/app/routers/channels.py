import json
import logging
import re
import redis as redis_lib
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, AIMessage

from ..auth import require_api_key
from ..config import settings
from ..agents.graph import graph, router_node

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/channels", tags=["channels"])

_CONV_TTL = 86400   # 24h per user session
_MAX_HISTORY = 20
_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)
_BADGE_RE = re.compile(r"\n\n---\n> 🤖 `agente: \w+`\s*$")


def _r():
    return redis_lib.from_url(settings.redis_url, decode_responses=True)


def _load_history(channel: str, user_id: str) -> list[dict]:
    try:
        data = _r().get(f"conv:{channel}:{user_id}")
        return json.loads(data) if data else []
    except Exception:
        return []


def _save_history(channel: str, user_id: str, history: list[dict]):
    try:
        _r().setex(f"conv:{channel}:{user_id}", _CONV_TTL, json.dumps(history[-_MAX_HISTORY:]))
    except Exception:
        pass


def _clean(text: str) -> str:
    text = _THINK_RE.sub("", text)
    text = _BADGE_RE.sub("", text)
    return text.strip()


class ChannelMessage(BaseModel):
    channel: str        # telegram | whatsapp | slack | discord | email
    user_id: str        # phone number, telegram id, etc.
    message: str
    username: str = ""


class ChannelResponse(BaseModel):
    response: str
    agent_used: str


@router.post("/message", response_model=ChannelResponse)
def channel_message(req: ChannelMessage, _: str = Depends(require_api_key)):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Empty message")

    history = _load_history(req.channel, req.user_id)
    history.append({"role": "user", "content": req.message})

    lc_messages = [
        HumanMessage(content=m["content"]) if m["role"] == "user"
        else AIMessage(content=m["content"])
        for m in history[-_MAX_HISTORY:]
    ]

    state = {"messages": lc_messages, "agent_used": ""}
    agent = router_node(state)["agent_used"]

    result = graph.invoke({"messages": lc_messages, "agent_used": agent})
    ai_msgs = [m for m in result["messages"] if isinstance(m, AIMessage)]
    raw = ai_msgs[-1].content if ai_msgs else "Sin respuesta"
    agent_used = result.get("agent_used", agent)

    response = _clean(raw)
    history.append({"role": "assistant", "content": response})
    _save_history(req.channel, req.user_id, history)

    logger.info(f"Channel {req.channel} | user {req.user_id} | agent {agent_used}")
    return ChannelResponse(response=response, agent_used=agent_used)


@router.delete("/history/{channel}/{user_id}")
def clear_history(channel: str, user_id: str, _: str = Depends(require_api_key)):
    try:
        _r().delete(f"conv:{channel}:{user_id}")
        return {"status": "cleared"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
