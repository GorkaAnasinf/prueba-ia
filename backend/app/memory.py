import logging
import redis as redis_lib
from datetime import datetime
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from .config import settings

logger = logging.getLogger(__name__)

_MAX_SUMMARIES = 20
_MIN_MESSAGES = 4


def _r():
    return redis_lib.from_url(settings.redis_url, decode_responses=True)


def load_memory() -> str:
    try:
        summaries = _r().lrange("memory:summaries", 0, 4)
        if not summaries:
            return ""
        return "Contexto de conversaciones previas:\n" + "\n---\n".join(summaries)
    except Exception:
        return ""


def save_memory(messages: list[BaseMessage], last_response: str):
    if len(messages) < _MIN_MESSAGES:
        return
    try:
        from .agents.graph import _get_llm
        lines = []
        for m in messages[-6:]:
            if isinstance(m, HumanMessage):
                lines.append(f"Usuario: {m.content[:300]}")
            elif isinstance(m, AIMessage):
                lines.append(f"Asistente: {m.content[:200]}")
        if not lines:
            return

        llm = _get_llm("chat")
        resp = llm.invoke([
            HumanMessage(content=(
                "Resume en 1-2 frases esta conversación destacando info clave, acuerdos o tareas:\n\n"
                + "\n".join(lines)
            ))
        ])
        summary = f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M')}] {resp.content.strip()}"
        r = _r()
        r.lpush("memory:summaries", summary)
        r.ltrim("memory:summaries", 0, _MAX_SUMMARIES - 1)
        logger.info("Memory summary saved")
    except Exception as e:
        logger.warning(f"Memory save failed: {e}")
